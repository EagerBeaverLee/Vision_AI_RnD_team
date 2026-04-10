import sqlite3, asyncio, duckdb, json
from PyQt6.QtCore import pyqtSignal, QThread

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

import numpy as np
import pandas as pd
import geopandas as gpd
import movingpandas as mpd
import shapely as shp
import hvplot.pandas
import matplotlib.pyplot as plt
from geopandas import GeoDataFrame, read_file
from shapely.geometry import Point, LineString, Polygon
from datetime import datetime, timedelta
from holoviews import opts, dim


class GenerateAISReport(QThread):
    report_chunk_fin = pyqtSignal(str)
    report_finished = pyqtSignal()
    report_error = pyqtSignal(str)

    def __init__(self, local_llm, data: pd.DataFrame):
        super().__init__()
        self.llm = local_llm
        self.chain = None
        self.weather_df = data

    def compress_ship_data_duckdb(self, db_path, table_name, min_lon=125.678, max_lon=131.229, max_lat=36.001):
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL sqlite; LOAD sqlite;")
        con.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE SQLITE);")

        query = f"""
        WITH raw_data AS (
            -- 1. 데이터 로드 및 초기 필터링
            SELECT 
                *,
                CAST(timestamp AS TIMESTAMP) as ts,
                CAST(longitude AS DOUBLE) as lon_val,
                CAST(latitude AS DOUBLE) as lat_val,
                CAST(course AS DOUBLE) as c_course,
                CAST(speed AS DOUBLE) as s_speed,
                row_number() OVER () as temp_row_idx
            FROM sqlite_db.{table_name}
            WHERE longitude >= {min_lon} 
            AND longitude <= {max_lon} 
            AND latitude <= {max_lat}
        ),
        ordered_data AS (
            -- 2. 이전 값 계산 (정렬 안정성 확보)
            SELECT *,
                LAG(lon_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lon,
                LAG(lat_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lat,
                LAG(c_course) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_course,
                LAG(s_speed) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_speed
            FROM raw_data
        ),
        diff_calc AS (
            -- 3. 변화량 계산 (부동소수점 오차 방지를 위해 정수로 변환하여 비교)
            SELECT *,
                -- ROUND(3) 대신 1000을 곱해 정수로 만들어 비교 (Pandas와의 미세한 오차 제거)
                CASE WHEN CAST(lon_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lon, lon_val) * 1000 AS BIGINT) 
                    OR CAST(lat_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lat, lat_val) * 1000 AS BIGINT) 
                    THEN 1 ELSE 0 END as pos_change,
                
                CASE 
                    WHEN (c_course - COALESCE(prev_course, c_course)) > 180 THEN (c_course - COALESCE(prev_course, c_course)) - 360
                    WHEN (c_course - COALESCE(prev_course, c_course)) < -180 THEN (c_course - COALESCE(prev_course, c_course)) + 360
                    ELSE (c_course - COALESCE(prev_course, c_course))
                END as course_diff,
                
                (s_speed - COALESCE(prev_speed, s_speed)) as speed_diff
            FROM ordered_data
        ),
        event_logic AS (
            -- 4. 이벤트 트리거 (>= 20 또는 >= 1.0 처럼 경계값에 미세 오차 고려 시도 가능하나 일단 정확히 일치 시도)
            SELECT *,
                CASE 
                    WHEN pos_change = 1 
                    OR (ABS(course_diff) >= 20.0 AND s_speed >= 1.0)
                    OR ABS(speed_diff) >= 2.0 
                    THEN 1 ELSE 0 
                END as event_trigger
            FROM diff_calc
        ),
        grouping AS (
            -- 5. 그룹 ID 생성 (Pandas cumsum과 동일)
            SELECT *,
                SUM(event_trigger) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id
            FROM event_logic
        ),
        summarized AS (
            -- 6. 그룹별 요약 (15개 컬럼 구성 시작)
            SELECT 
                ShipName,
                group_id,
                ANY_VALUE(mmsi) as mmsi, -- FIRST 대신 ANY_VALUE가 성능상 유리하나 의미는 같음
                ANY_VALUE(higher_types) as higher_types,
                ANY_VALUE(radius) as radius,
                MIN(ts) as start_time,
                MAX(ts) as end_time,
                ANY_VALUE(lon_val) as lon,
                ANY_VALUE(lat_val) as lat,
                ANY_VALUE(c_course) as first_course,
                AVG(s_speed) as avg_speed,
                ANY_VALUE(course_diff) as turn_val,
                ANY_VALUE(speed_diff) as accel_val
            FROM grouping
            GROUP BY ShipName, group_id
        ),
        final_stats AS (
            -- 7. 이전 그룹과의 속도 차이 계산
            SELECT *,
                avg_speed - COALESCE(LAG(avg_speed) OVER (PARTITION BY ShipName ORDER BY start_time), avg_speed) as group_speed_diff
            FROM summarized
        )
        -- 8. 최종 15개 컬럼 및 상태값 생성
        SELECT 
            ShipName, group_id, mmsi, higher_types, radius, start_time, end_time, 
            lon, lat, first_course, avg_speed, turn_val, accel_val, group_speed_diff,
            CASE 
                WHEN avg_speed < 1.0 THEN '정박/대기'
                ELSE 
                    TRIM(
                        CONCAT_WS(' ',
                            CASE WHEN ABS(turn_val) >= 20.0 AND avg_speed >= 1.0 
                                THEN (CASE WHEN turn_val > 0 THEN '우선회' ELSE '좌선회' END) || '(' || ROUND(ABS(turn_val), 1) || '°)'
                                ELSE '' END,
                            CASE WHEN group_speed_diff >= 2.0 THEN '가속'
                                WHEN group_speed_diff <= -2.0 THEN '감속' -- < -2 대신 <= -2로 더 정확히
                                ELSE '' END,
                            CASE WHEN avg_speed >= 5.0 THEN '이동/통과' ELSE '저속 운항' END
                        )
                    )
            END as status
        FROM final_stats
        ORDER BY ShipName, start_time
        """

        df_result = con.execute(query).df()
        con.execute("DETACH sqlite_db;")
        return df_result
    
    def compress_ship_data_duckdb_further(self, db_path, table_name, min_lon=125.678, max_lon=131.229, max_lat=36.001):
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL sqlite; LOAD sqlite;")
        con.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE SQLITE);")

        query = f"""
        -- [STEP 1] Raw 데이터 로드 및 1차 트리거 (정수 변환 비교로 정밀도 확보)
        WITH raw_data AS (
            SELECT *,
                CAST(timestamp AS TIMESTAMP) as ts,
                CAST(longitude AS DOUBLE) as lon_val,
                CAST(latitude AS DOUBLE) as lat_val,
                CAST(course AS DOUBLE) as c_course,
                CAST(speed AS DOUBLE) as s_speed,
                row_number() OVER () as temp_row_idx
            FROM sqlite_db.{table_name}
            WHERE longitude >= {min_lon} AND longitude <= {max_lon} AND latitude <= {max_lat}
        ),
        ordered_data AS (
            SELECT *,
                LAG(lon_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lon,
                LAG(lat_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lat,
                LAG(c_course) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_course,
                LAG(s_speed) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_speed
            FROM raw_data
        ),
        diff_calc AS (
            SELECT *,
                CASE WHEN CAST(lon_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lon, lon_val) * 1000 AS BIGINT) 
                    OR CAST(lat_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lat, lat_val) * 1000 AS BIGINT) 
                    THEN 1 ELSE 0 END as pos_change,
                CASE 
                    WHEN (c_course - COALESCE(prev_course, c_course)) > 180 THEN (c_course - COALESCE(prev_course, c_course)) - 360
                    WHEN (c_course - COALESCE(prev_course, c_course)) < -180 THEN (c_course - COALESCE(prev_course, c_course)) + 360
                    ELSE (c_course - COALESCE(prev_course, c_course))
                END as course_diff,
                (s_speed - COALESCE(prev_speed, s_speed)) as speed_diff
            FROM ordered_data
        ),
        event_logic AS (
            SELECT *,
                -- 경계값 오차 방지를 위해 0.000001 보정 (Pandas와의 일치성 향상)
                CASE WHEN pos_change = 1 OR (ABS(course_diff) >= 19.999999 AND s_speed >= 0.999999) OR ABS(speed_diff) >= 1.999999 THEN 1 ELSE 0 END as event_trigger
            FROM diff_calc
        ),
        grouping_v1 AS (
            SELECT *,
                SUM(event_trigger) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id_v1
            FROM event_logic
        ),
        summarized_v1 AS (
            -- [1차 압축] ANY_VALUE 대신 FIRST를 사용하여 Pandas .first()와 100% 일치화
            SELECT 
                ShipName, group_id_v1,
                FIRST(mmsi) as mmsi, FIRST(higher_types) as higher_types, FIRST(radius) as radius,
                MIN(ts) as start_time, MAX(ts) as end_time,
                FIRST(lon_val) as lon, FIRST(lat_val) as lat,
                FIRST(c_course) as first_course, AVG(s_speed) as avg_speed,
                FIRST(course_diff) as turn_val, FIRST(speed_diff) as accel_val
            FROM grouping_v1 
            GROUP BY ShipName, group_id_v1
        ),
        -- [STEP 2] 상태 판별 (부동소수점 오차 차단)
        status_calc AS (
            SELECT *,
                avg_speed - COALESCE(LAG(avg_speed) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1), avg_speed) as group_speed_diff
            FROM summarized_v1
        ),
        status_final AS (
            SELECT *,
                CASE 
                    -- 1.0, 20.0 등의 경계값을 소수점 8자리에서 반올림 후 비교하여 Pandas와 일치시킴
                    WHEN ROUND(avg_speed, 8) < 1.0 THEN '정박/대기'
                    ELSE TRIM(CONCAT_WS(' ',
                        CASE WHEN ROUND(ABS(turn_val), 8) >= 20.0 AND ROUND(avg_speed, 8) >= 1.0 
                            THEN (CASE WHEN turn_val > 0 THEN '우선회' ELSE '좌선회' END) || '(' || ROUND(ABS(turn_val), 1) || '°)' ELSE '' END,
                        CASE WHEN ROUND(group_speed_diff, 8) >= 2.0 THEN '가속' 
                            WHEN ROUND(group_speed_diff, 8) < -2.0 THEN '감속' ELSE '' END,
                        CASE WHEN ROUND(avg_speed, 8) >= 5.0 THEN '이동/통과' ELSE '저속 운항' END
                    ))
                END as status
            FROM status_calc
        ),
        -- [STEP 3] 2차 압축
        v2_trigger AS (
            SELECT *,
                CASE WHEN status != COALESCE(LAG(status) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1), status) 
                    THEN 1 ELSE 0 END as status_change
            FROM status_final
        ),
        v2_grouping AS (
            SELECT *,
                SUM(status_change) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id
            FROM v2_trigger
        )
        -- [STEP 4] 최종 요약 (집계 방식 일치)
        SELECT 
            ShipName, group_id,
            FIRST(mmsi) as mmsi, FIRST(higher_types) as higher_types, FIRST(radius) as radius,
            MIN(start_time) as start_time, MAX(end_time) as end_time,
            FIRST(lon) as lon, FIRST(lat) as lat,
            FIRST(first_course) as first_course,
            AVG(avg_speed) as avg_speed,
            FIRST(turn_val) as turn_val,
            FIRST(accel_val) as accel_val,
            FIRST(status) as status
        FROM v2_grouping
        GROUP BY ShipName, group_id
        ORDER BY ShipName, start_time
        """

        df_result = con.execute(query).df()
        con.execute("DETACH sqlite_db;")
        return df_result

    def build_ais_report_chain(self):
        full_path = "ships.db"

        #mmsi로 배 선택
        target_mmsi = [563161700, 352002106]
        compress_twice = self.compress_ship_data_duckdb_further(db_path=full_path, table_name="ship_logs")

        filtered_mmsi = compress_twice[compress_twice['mmsi'].isin(target_mmsi)].copy()

        data_dict = filtered_mmsi.to_dict(orient='records')
        trajectory_json = json.dumps(data_dict, ensure_ascii=False, indent=4, default=str)

        # mmsi로 필터링된 지역의 가장 마지막 location 저장
        last_data = filtered_mmsi.iloc[-1]
        last_lat = last_data['lat']
        last_lon = last_data['lon']

        # --- 최단경로인 지점 계산 알고리즘 ---
        target = np.array([last_lat, last_lon])

        dist_sq = np.sum((self.weather_df[['latitude', 'longitude']].values - target)**2, axis=1)

        closest_idx = np.argmin(dist_sq)

        closest_location = self.weather_df.iloc[closest_idx]

        weather_dict = closest_location.to_dict()
        weather_json = json.dumps(weather_dict, ensure_ascii=False, indent=4, default=str)

        # 디버깅 로그
        print(closest_idx, closest_location['지점명'])
        print(weather_json)
        # --------------------------------------
        
        # 디버깅 로그
        print(trajectory_json)
        ais_prompt_template ="""
            # Role
            당신은 대한민국 주변 선박운행을 관제하는 베테랑 해상 관제사(VTS Operator)이자 선박 항적 분석 전문가 입니다. 
            제공된 요약된 항적 데이터(Summarized Trajectory)를 바탕으로 선박의 이동 패턴과 주요 이벤트를 전문적인 자연어로 묘사해주세요.

            #Input Data
            1. Summarized Trajectory
            {trajectory_data}
            2. Current Weather data
            {weather_data}

            # Guidelines
            1. 시간 순서대로 전체적인 항해 흐름을 요약해주세요.
            2. 요약할 때 기준은 "status"필드를 기준으로 하되 start_time과 end_time을 참고하세요. 
            3. trajectory_data는 ShipName이 같은 데이터끼리 리스트로 한번 더 묶여있으니 서로 ShipName이 서로 다른 배끼리 혼용하지 않도록 유의하세요.
            4. 첫번째 ShipName에 해당하는 현재날씨는 weather_data에서 첫번째 날씨 데이터를, 두번째 Shipnam에 해당하는 현재 날씨는 weather_data에서 두번째 날씨 데이터를 참고하세요.
            5. 전문적인 해상 관제 용어를 사용해도 되지만, 가독성이 좋게 작성하세요.
            6. 날씨데이터에 대해서 관제사가 고려하고 참고해야 할 사항에 대해 설명해주세요

            #Output Format
            1. 전체적인 항해 패턴을 간단하게 요약; 관제사가 관심을 가져야 할 특이 사항이 있을 시 간단하게 언급
            2. 현재 날씨에 대해 간단히 요약; 관제사가 관심을 가져야 할 날씨의 특이사항(풍향, 풍속 유의파고 등)이 있을 시 간단하게 언급 및 조치사항 설명
            3. 1, 2 항목을 종합적으로 정리해서 묘사

            질문:{question}
            """

        each_ship_prompt = ChatPromptTemplate.from_template(ais_prompt_template)

        self.chain = (
            RunnablePassthrough.assign(
                trajectory_data = lambda x: trajectory_json,
                weather_data = lambda x: weather_json,
            )
            | each_ship_prompt
            | self.llm
        )
        
    def run(self):
        print(f"[{QThread.currentThreadId()}] LLM작업 시작 {datetime.now()}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._stream())

    async def _stream(self):
        self.build_ais_report_chain()
        # sorted_data = self.data.sort_values(by=['ShipName', 'start_time'], ascending=True)

        # total_list = [
        #     group[1].to_dict(orient='records')
        #     for group in sorted_data.groupby('ShipName', sort=False)
        # ]

        try:
            buffer = []
            async for chunk in self.chain.astream({'question': "항적에 대해 묘사해줘"}):
                if chunk:
                    buffer.append(chunk.content)

                if len(buffer) >= 10:
                    self.report_chunk_fin.emit("".join(buffer))
                    buffer.clear()

            if buffer:
                self.report_chunk_fin.emit("".join(buffer))

        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.report_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.report_finished.emit()