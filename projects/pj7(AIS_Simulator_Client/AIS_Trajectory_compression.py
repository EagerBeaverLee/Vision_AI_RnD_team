import sqlite3, asyncio, duckdb, json, shapely, requests, io, base64
from PyQt6.QtCore import pyqtSignal, QThread

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

import numpy as np
import pandas as pd
import geopandas as gpd
import movingpandas as mpd
import holoviews as hv
import shapely as shp
import hvplot.pandas
import matplotlib.pyplot as plt

from geopandas import GeoDataFrame, read_file
from geopy.distance import great_circle
from shapely.geometry import Point, LineString, Polygon, MultiPoint, box
from datetime import datetime, timedelta

from bokeh.resources import INLINE
from bokeh.embed import file_html
from holoviews import opts, dim, Layout


class GenerateAISReport(QThread):
    report_chunk_fin = pyqtSignal(str)
    report_finished = pyqtSignal()
    report_error = pyqtSignal(str)

    def __init__(self, flag: bool, local_llm, question, data: pd.DataFrame, mmsi_list, startTime, currTime):
        super().__init__()
        self.flag = flag    #True: 전체항적 report, False: 개별항적 report
        self.llm = local_llm
        self.chain = None
        self.weather_df = data
        self.start_server_time = startTime
        self.curr_server_time = currTime
        self.question = question

        # ---geo values---
        self.zones_gdf = None
        self.ports_gdf = None
        self.geo_dict = {}
        self.mmsi_list = mmsi_list
        self.ship_input_data = None
        self.weather_json = []
        
        # movingpandas전처리 결과 저장
        self.ais_gdf = None
        self.aggregator = None
        self.trips = None
        self.clusters_data_json = None
        # ------------

        # 렌더러 설정
        self.renderer = hv.renderer('bokeh')
        

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

    # 항만 입출항 판정 함수: 출항 선박은 반드시 해당 항구에서 출발하여, 항구 경계선 밖으로 나가야만 출항으로 판정
    # 입항 선박은 항구 경계선 밖에서 시작하여 항구경계 안으로로 들어오 것만 인정
    def is_leaving(self, traj, poly):
        #시작은 안에서, 끝은 밖에서
        return traj.get_start_location().intersects(poly) and not traj.get_end_location().intersects(poly)

    def is_entering(self, traj, poly):
        #시작은 안에서, 끝은 밖에서
        return not traj.get_start_location().intersects(poly) and  traj.get_end_location().intersects(poly)

    def geo_init_ports_gdf(self):
        # 주요 항만 데이터
        self.ports_gdf = gpd.read_file('./data/major_ports.shp')
        self.ports_gdf = self.ports_gdf.to_crs("EPSG:4326")

    def geo_init_zone_gdf(self):
        zone_configs = {
            # --- [Layer 1: 북부 연안 및 울산] Lat: 34.70 ~ 36.00 (일부 34.40 시작) ---
            'Zone_16':   [125.00, 34.40, 125.50, 36.00, '서해 남부 외해'],
            'Zone_5':    [125.50, 34.40, 126.60, 36.00, '목포-신안 해역'],
            'Zone_12':   [126.60, 34.40, 127.60, 36.00, '고흥-완도 연안'],
            'Zone_3':    [127.60, 34.70, 128.00, 36.00, '광양-여수 해역'],
            'Zone_4':    [128.00, 34.70, 128.30, 36.00, '남해 중앙 연안'],
            'Zone_2':    [128.30, 34.70, 128.70, 36.00, '거제-통영 해역'],
            'Zone_1':    [128.70, 34.70, 129.30, 36.00, '부산-가덕 해역'],
            'Zone_18':   [129.30, 34.70, 130.50, 36.00, '부산외항-울산남부'], # 부산 동쪽 빈틈 메움
            'Zone_14':   [130.50, 35.15, 132.50, 36.00, '울산-포항 해역'],
            
            # --- [Layer 2: 중단 외해 및 대한해협] Lat: 33.80 ~ 34.70 ---
            'Zone_7':    [125.00, 33.00, 126.20, 34.40, '서남해 외해'],
            'Zone_8':    [126.20, 33.80, 127.60, 34.40, '제주-육지 교차로 해역'],
            'Zone_9_1':  [127.60, 33.80, 128.30, 34.70, '여수-통영 외해'],
            'Zone_9_2':  [128.30, 33.80, 128.70, 34.70, '거제-가덕 외해'],
            'Zone_9_3':  [128.70, 33.80, 129.30, 34.70, '부산-대마도 입구 해역'], # 부산 하단 빈틈 메움
            'Zone_15_1': [129.30, 33.80, 130.50, 34.70, '대마도 남서 해역'],
            'Zone_17':   [130.50, 33.80, 131.50, 34.25, '시모노세키-기타큐슈 해역'],
            'Zone_15_2': [130.50, 34.25, 131.50, 35.15, '대마도 북동 해역'],
            
            # --- [Layer 3: 제주 및 일본 연안] Lat: 33.00 ~ 33.80 ---
            'Zone_6':    [126.20, 33.40, 126.90, 33.80, '제주 북부 연안'],
            'Zone_13':   [126.20, 33.00, 126.90, 33.40, '제주 남부 연안'],
            'Zone_11':   [126.90, 33.00, 129.50, 33.80, '제주 남동부 해역'],
            'Zone_15_3': [129.50, 33.00, 131.00, 33.80, '이키-후쿠오카 연안'],
            'Zone_15_4': [131.00, 33.00, 132.50, 35.15, '일본 가이요 외해'],
            
            # --- [Layer 4: 최남단 원거리] Lat: 31.00 ~ 33.00 ---
            'Zone_10':   [125.00, 31.00, 132.50, 33.00, '원거리 국제공해']
        }

        polygons = []
        ids = []
        names = []

        for zid, val in zone_configs.items():
            polygons.append(box(val[0], val[1], val[2], val[3]))
            ids.append(zid)
            names.append(val[4])

        self.zones_gdf = gpd.GeoDataFrame({'zone_id': ids, 'name': names}, 
                                    geometry=polygons, crs="EPSG:4326")

    def geo_common_preprocessing(self, start_time, end_time):
        # 1. DuckDB 파일 연결 및 공간 확장 로드
        db_path = "ships.db"
        con = duckdb.connect(database=db_path)
        con.execute("INSTALL spatial; LOAD spatial;")

        table_name = "ship_logs"

        # 2. 초기 데이터 필터링 (DuckDB)
        # CSV를 읽으면서 위경도/시간/속도를 즉시 필터링
        min_lon, max_lon, max_lat = 125.678, 131.229, 36.001

        # 쿼리 실행 (DB 내부에서 직접 필터링)
        query = f"""
            SELECT *, ST_AsWKB(ST_Point(longitude, latitude)) as geom_wkb, CAST(timestamp AS TIMESTAMP) as t
            FROM {table_name}
            WHERE longitude >= {min_lon} AND longitude <= {max_lon}
            AND latitude <= {max_lat}
            AND timestamp >= '{start_time}' 
            AND timestamp <= '{end_time}'
            AND speed > 0
            ORDER BY MMSI, t ASC  -- 이 줄이 필수입니다!
        """

        # 3. DuckDB 결과를 Pandas로 가져오기
        df = con.execute(query).df()

        # 4. WKB 컬럼을 이용해 즉시 GeoDataFrame 생성
        # 이 방식은 points_from_xy보다 대용량 처리 시 훨씬 빠릅니다.
        self.ais_gdf = gpd.GeoDataFrame(
            df, 
            geometry=shapely.from_wkb(df['geom_wkb'].apply(bytes)),
            crs="EPSG:4326"
        ).set_index('t')

        # 3. MovingPandas 집계 (클러스터 추출)
        traj_collection = mpd.TrajectoryCollection(self.ais_gdf, 'mmsi', min_length=1000)
        n_traj_collection = mpd.DouglasPeuckerGeneralizer(traj_collection).generalize(tolerance=0.001) #가장 빠름
        # 전처리 추가(실험 필요)
        self.trips = mpd.ObservationGapSplitter(n_traj_collection).split(gap=timedelta(minutes=120))
        self.aggregator = mpd.TrajectoryCollectionAggregator(
            self.trips, max_distance=100000, min_distance=2000, min_stop_duration=timedelta(minutes=120)
        )
    
    def geo_cluster_data_processing(self):
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        clusters_gdf = self.aggregator.get_clusters_gdf()

        # 4. DuckDB 공간 조인 및 최종 통계 처리
        # Geometry를 DuckDB가 이해할 수 있는 WKB로 변환하여 등록
        clusters_gdf['geom_wkb'] = clusters_gdf['geometry'].to_wkb()
        self.zones_gdf['geom_wkb'] = self.zones_gdf['geometry'].to_wkb()

        con.register('v_clusters', clusters_gdf[['n', 'geom_wkb']])
        con.register('v_zones', self.zones_gdf[['name', 'geom_wkb']])

        # [공간 조인 + 그룹화 + 정렬]을 한 번의 SQL로 처리
        # ST_GeomFromWKB를 사용하여 바이너리를 공간 객체로 복원 후 연산
        final_query = """
            SELECT z.name, COUNT(*) as stop_count, SUM(CAST(c.n AS DOUBLE)) as total_stay_index
            FROM v_clusters c, v_zones z
            WHERE ST_Intersects(ST_GeomFromWKB(c.geom_wkb), ST_GeomFromWKB(z.geom_wkb))
            GROUP BY z.name
            ORDER BY total_stay_index DESC
        """

        # 5. 결과 추출 및 JSON 변환
        final_summary_df = con.execute(final_query).df()

        clusters_data_json = json.dumps(
            final_summary_df.to_dict(orient="records"), 
            ensure_ascii=False, 
            indent=4
        )
        return clusters_data_json

    def geo_speed_processed_duckdb(self, start_time, end_time):
        db_path = "ships.db"
        con = duckdb.connect(database=db_path)
        con.execute("INSTALL spatial; LOAD spatial;")

        # 2. 기준 구역(zones_gdf)을 DuckDB에 등록
        # 공간 조인을 위해 zones_gdf를 WKB로 변환하여 임시 테이블로 등록합니다.
        self.zones_gdf['geom_wkb'] = self.zones_gdf['geometry'].to_wkb()
        con.register('v_zones', self.zones_gdf[['name', 'geom_wkb']])

        # 3. DuckDB 통합 쿼리 (필터링 + 공간 조인 + 통계 요약)
        # 포인트 생성부터 구역 매칭, 평균/최대 속도 계산까지 SQL 한 번에 처리합니다.
        min_lon, max_lon, max_lat = 125.678, 131.229, 36.001

        integrated_query = f"""
            WITH filtered_ais AS (
                -- [단계 1] 기본 필터링 및 포인트 생성
                SELECT 
                    speed,
                    ST_Point(longitude, latitude) as point_geom
                FROM ship_logs
                WHERE longitude BETWEEN {min_lon} AND {max_lon}
                AND latitude <= {max_lat}
                AND timestamp >= '{start_time}' 
                AND timestamp <= '{end_time}'
                AND speed > 0
            ),
            joined_data AS (
                -- [단계 2] 구역 테이블(v_zones)과 공간 조인 (ST_Within)
                -- INNER JOIN을 통해 구역에 속하지 않은(NaN이 될) 데이터는 자동 필터링됩니다.
                SELECT 
                    z.name,
                    a.speed
                FROM filtered_ais a
                JOIN v_zones z ON ST_Within(a.point_geom, ST_GeomFromWKB(z.geom_wkb))
            )
            -- [단계 3] 구역별 속도 통계 산출
            SELECT 
                name,
                AVG(speed) as mean,
                MAX(speed) as max,
                COUNT(*) as count
            FROM joined_data
            GROUP BY name
            ORDER BY name ASC
        """

        # 4. 결과 실행 및 JSON 변환
        # 데이터 요약본만 파이썬으로 넘어오므로 매우 가볍습니다.
        speed_stats_df = con.execute(integrated_query).df()

        return speed_stats_df
    
    def geo_speed_data_processing(self, start_time, end_time):
        speed_stats_df = self.geo_speed_processed_duckdb(start_time, end_time)
        speed_data = json.dumps(
            speed_stats_df.to_dict(orient="records"), 
            ensure_ascii=False, 
            indent=4
        )
        return speed_data

    def geo_direction_flow_data_processing(self):
        db_path = "ships.db"
        comp_ship_data = self.compress_ship_data_duckdb_further(db_path=db_path, table_name="ship_logs")

        # 1. DuckDB 연결 (메모리 모드) 및 공간 확장 로드
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        # 2. Pandas DataFrame을 DuckDB 테이블로 등록
        # 이렇게 하면 SQL 쿼리에서 'v_ais_data'라는 이름으로 df를 참조할 수 있습니다.
        con.register('v_ais_data', comp_ship_data)

        # 3. DuckDB SQL 연산 통합 (Binning + Vector Mean)
        query = """
            WITH filtered_moving AS (
                -- [단계 1] '정박/대기'를 제외하고 MMSI별 마지막 경로와 평균 속도 추출
                SELECT 
                    mmsi,
                    -- 가장 최근의 경로를 가져오기 위해 start_time(또는 end_time) 기준 arg_max 사용
                    arg_max(first_course, start_time) as last_course,
                    AVG(avg_speed) as mean_speed
                FROM v_ais_data
                WHERE status != '정박/대기'
                GROUP BY mmsi
            ),
            binned_directions AS (
                -- [단계 2] 8방위 분류 (Binning)
                SELECT 
                    *,
                    CASE 
                        WHEN last_course >= 337.5 OR last_course < 22.5 THEN '북'
                        WHEN last_course >= 22.5 AND last_course < 67.5 THEN '북동'
                        WHEN last_course >= 67.5 AND last_course < 112.5 THEN '동'
                        WHEN last_course >= 112.5 AND last_course < 157.5 THEN '남동'
                        WHEN last_course >= 157.5 AND last_course < 202.5 THEN '남'
                        WHEN last_course >= 202.5 AND last_course < 247.5 THEN '남서'
                        WHEN last_course >= 247.5 AND last_course < 292.5 THEN '서'
                        WHEN last_course >= 292.5 AND last_course < 337.5 THEN '북서'
                    END AS direction_group
                FROM filtered_moving
            ),
            vector_agg AS (
                -- [단계 3] 방향 그룹별 통계 및 벡터 평균 연산
                SELECT 
                    direction_group,
                    COUNT(*) as ship_count,
                    AVG(mean_speed) as average_speed_knot,
                    AVG(sin(radians(last_course))) as mean_sin,
                    AVG(cos(radians(last_course))) as mean_cos
                FROM binned_directions
                GROUP BY direction_group
            )
            -- [단계 4] 최종 결과 포맷팅
            SELECT 
                direction_group || '진' as direction,
                ship_count,
                ROUND(average_speed_knot, 1) as average_speed_knot,
                ROUND((degrees(atan2(mean_sin, mean_cos)) + 360) % 360, 1) as vector_course_deg
            FROM vector_agg
            ORDER BY 
                CASE direction_group 
                    WHEN '북' THEN 1 WHEN '북동' THEN 2 WHEN '동' THEN 3 WHEN '남동' THEN 4 
                    WHEN '남' THEN 5 WHEN '남서' THEN 6 WHEN '서' THEN 7 WHEN '북서' THEN 8 
                END
        """
        
        # 4. 결과 실행 및 JSON 변환
        result_df = con.execute(query).df()
        
        if result_df.empty:
            return json.dumps([{"message": "현재 이동 중인 주요 선박 흐름 없음"}], ensure_ascii=False)
            
        direction_flow_data = json.dumps(result_df.to_dict(orient="records"), ensure_ascii=False, indent=4)
        
        return direction_flow_data

    def geo_trajs_flow_data_processing(self):
        # 1. DuckDB 연결 및 공간 확장 로드
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        flows = self.aggregator.get_flows_gdf()

        # 2. 데이터 등록을 위한 WKB 변환
        # flows는 LineString geometry를 가짐
        flows['geom_wkb'] = flows.geometry.to_wkb()
        self.zones_gdf['geom_wkb'] = self.zones_gdf['geometry'].to_wkb()

        con.register('v_flows', flows[['weight', 'geom_wkb']])
        con.register('v_zones', self.zones_gdf[['name', 'geom_wkb']])

        # 3. 통합 SQL 쿼리
        # ST_StartPoint, ST_EndPoint 함수를 사용하여 좌표 추출 및 조인
        query = """
            WITH flow_base AS (
                SELECT 
                    weight,
                    ST_StartPoint(ST_GeomFromWKB(geom_wkb)) as start_pt,
                    ST_EndPoint(ST_GeomFromWKB(geom_wkb)) as end_pt,
                    row_number() OVER() as flow_id -- 각 항로에 고유 ID 부여
                FROM v_flows
            ),
            start_zones AS (
                -- 시작점당 구역 1개만 매칭 (기존 duplicated 제거 로직 재현)
                SELECT flow_id, name as origin_zone
                FROM (
                    SELECT f.flow_id, z.name,
                        row_number() OVER(PARTITION BY f.flow_id ORDER BY z.name) as rn
                    FROM flow_base f
                    JOIN v_zones z ON ST_Intersects(f.start_pt, ST_GeomFromWKB(z.geom_wkb))
                ) WHERE rn = 1
            ),
            end_zones AS (
                -- 끝점당 구역 1개만 매칭
                SELECT flow_id, name as dest_zone
                FROM (
                    SELECT f.flow_id, z.name,
                        row_number() OVER(PARTITION BY f.flow_id ORDER BY z.name) as rn
                    FROM flow_base f
                    JOIN v_zones z ON ST_Intersects(f.end_pt, ST_GeomFromWKB(z.geom_wkb))
                ) WHERE rn = 1
            )
            SELECT 
                s.origin_zone,
                e.dest_zone,
                SUM(f.weight) as weight
            FROM flow_base f
            JOIN start_zones s ON f.flow_id = s.flow_id
            JOIN end_zones e ON f.flow_id = e.flow_id
            GROUP BY s.origin_zone, e.dest_zone
            ORDER BY weight DESC
            LIMIT 13
        """

        # 4. 실행 및 결과 변환
        flow_summary_df = con.execute(query).df()
        
        if flow_summary_df.empty:
            return json.dumps([], ensure_ascii=False)

        trajs_flow_data =  json.dumps(
            flow_summary_df.to_dict(orient='records'), 
            ensure_ascii=False, 
            indent=4
        )
    
        return trajs_flow_data
    
    def geo_shiptype_data_processing(self, start_time, end_time):
        # 1. DuckDB 파일 연결 및 공간 확장 로드
        db_path = "ships.db"
        con = duckdb.connect(database=db_path)
        con.execute("INSTALL spatial; LOAD spatial;")

        table_name = "ship_logs"

        # 2. 초기 데이터 필터링 (DuckDB)
        # CSV를 읽으면서 위경도/시간/속도를 즉시 필터링
        min_lon, max_lon, max_lat = 125.678, 131.229, 36.001

        # 쿼리 실행 (DB 내부에서 직접 필터링)
        integrated_sql = f"""
            -- [단계 1] 조건에 맞는 데이터를 임시 테이블에 먼저 저장 (가장 무거운 연산)
            CREATE OR REPLACE TEMP TABLE t_filtered_ais AS 
            SELECT *, ST_Point(longitude, latitude) as geom_pt
            FROM {table_name}
            WHERE longitude BETWEEN {min_lon} AND {max_lon}
            AND latitude <= {max_lat}
            AND timestamp >= '{start_time}' 
            AND timestamp <= '{end_time}'
            AND speed > 0;

            -- [단계 2] 선종별 고유 선박 수 집계 (LLM 리포트용)
            SELECT 
                ShipType, 
                COUNT(DISTINCT MMSI) as ship_count
            FROM t_filtered_ais
            GROUP BY ShipType
            ORDER BY ship_count DESC;
        """

        shiptype_summary_df = con.execute(integrated_sql).df()

        shiptype_data = json.dumps(
            shiptype_summary_df.to_dict(orient="records"), 
            ensure_ascii=False, 
            indent=4
        )

        return shiptype_data

    def weather_data_processing(self):
        # 1. 평균을 계산할 필드 리스트 정의
        target_columns = [
            "풍속(m/s)", "풍향(deg)", "GUST풍속(m/s)", "현지기압(hPa)", 
            "습도(%)", "기온(°C)", "수온(°C)", "최대파고(m)", 
            "유의파고(m)", "평균파고(m)", "파주기(sec)", "파향(deg)"
        ]

        # 2. DataFrame에서 해당 컬럼만 선택하여 평균 계산
        # numeric_only=True를 설정하면 숫자가 아닌 값이 섞여있을 때 에러를 방지합니다.
        # round(2)로 소수점 둘째 자리까지 제한합니다.
        weather_avg = self.weather_df[target_columns].mean().round(2)
        # print(" === weather data debug ===")
        # print(weather_avg.to_dict())
        weather_json = json.dumps(weather_avg.to_dict(), ensure_ascii=False, indent=4, default=str)
        
        return weather_json
    
    def geo_render_OD_Flow_map(self, start_time, end_time):
        if len(self.aggregator.flows) > 0:
            flows = self.aggregator.get_flows_gdf()
        else:
            print("생성된 항로(Flow)가 없습니다. 파라미터를 조정하세요.")
            return
        
        if len(self.aggregator.clusters) > 0:
            clusters = self.aggregator.get_clusters_gdf()
        else:
            print("생성된 군집(Cluster)이 없습니다. 파라미터를 조정하세요.")
            return
        
        # 1. DuckDB 연결 및 공간 확장 로드 (기존 유지)
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        zone_speed_stats = self.geo_speed_processed_duckdb(start_time, end_time)
        
        # 2. 결과 데이터(zone_speed_stats)를 DuckDB에 등록
        # 이미 계산된 통계치를 다시 DB로 보내 연산의 중심으로 삼습니다.
        con.register('v_speed_stats', zone_speed_stats)

        # [중요] zones_gdf는 이미 v_zones로 등록되어 있다고 가정합니다. 
        # 만약 세션이 끊겼다면 아래 한 줄을 다시 실행하세요.
        self.zones_gdf['geom_wkb'] = self.zones_gdf['geometry'].to_wkb()
        con.register('v_zones', self.zones_gdf[['name', 'geom_wkb']])

        # 3. DuckDB 통합 쿼리: 통계 데이터 + 구역 도형 데이터 병합
        # 이 쿼리는 시각화에 필요한 모든 컬럼을 한 번에 정렬하여 반환합니다.
        final_viz_query = """
            SELECT 
                z.name,
                z.geom_wkb,
                CAST(s.mean AS DOUBLE) as mean,
                s.max,
                s.count
            FROM v_zones z
            INNER JOIN v_speed_stats s ON z.name = s.name
            ORDER BY s.mean DESC
        """

        # 4. 결과 실행 및 GeoDataFrame 복원
        viz_df = con.execute(final_viz_query).df()

        # DuckDB에서 가져온 WKB를 다시 Shapely geometry로 변환 (GeoPandas 최적화)
        zones_plot_data = gpd.GeoDataFrame(
            viz_df,
            geometry=gpd.GeoSeries.from_wkb(viz_df['geom_wkb'].apply(bytes)),   # bytearray 데이터 처리
            crs="EPSG:4326"
        ).drop(columns=['geom_wkb'])

        #################################################
        ## 최적화된 시각화 실행 (전달받은 viz_df 사용)
        #################################################

        # 1. 해상구역 배경 (평균 속도 기반 채색)
        zones_speed = zones_plot_data.hvplot(
            geo=True, tiles="EsriImagery", alpha=0.45, c="mean",
            colorbar=False,
            # clabel="Avg Speed (knots)",
            line_color='black', line_width=1,
            cmap='YlOrRd', 
            hover_cols=['name', 'mean', 'count'], # mean_knots 대신 mean 사용
            frame_height=330, frame_width=430, legend=False,
            responsive=True # 이전의 레이아웃 어긋남 방지
        )

        # 2. 레이어 통합
        flow_cluster_map = (zones_speed * flows.hvplot(geo=True, hover_cols=['weight'], line_width='weight', alpha=0.5, color='#00FFFF') * clusters.hvplot(geo=True, color='red', size='n')
        ).opts(
            # title='Integrated Analysis: OD Flows, Avg Speed & Clusters',
            active_tools=['wheel_zoom'],
            xaxis=None,            # x축 전체 숨기기
            yaxis=None,            # y축 전체 숨기기
            show_legend=False,     # 범례 숨기기
            bgcolor='#0E1117',
            # 에러가 났던 border_fill_color 대신 hooks를 사용하여 Bokeh 모델을 직접 수정
            hooks=[lambda plot, element: (
                setattr(plot.state, 'border_fill_color', '#0E1117'),
                setattr(plot.state.title, 'text_color', 'white')
            )]
        )

        plot_state = self.renderer.get_plot(flow_cluster_map).state
        plot_state.sizing_mode = 'stretch_both' # 레이아웃 최적화

        # 3. Bokeh의 file_html을 사용하여 HTML 문자열 생성
        html_content = file_html(plot_state, INLINE, "Interactive Map")

        self.geo_dict['od_flow_map'] = html_content

    def geo_render_major_ports_map(self):
        anchored_ships_gdf = self.geo_processing_anchored_ships_gdf()
        # 1. 대상 항구 리스트
        target_ports = ['BUSAN HANG', 'ULSAN HANG','GWANGYANG HANG, HADONG HANG', 'MOKPO HANG']

        for i, port_name in enumerate(target_ports):
            # --- A. 해당 항구 폴리곤 및 영역(AOI) 추출 ---
            single_port_gdf = self.ports_gdf[self.ports_gdf['objnam'] == port_name]
            if single_port_gdf.empty: continue
            
            # 500m 버퍼 적용 (입출항 판정)
            port_projected = single_port_gdf.to_crs(epsg=5179)
            port_projected['geometry'] = port_projected.geometry.buffer(500)
            port_aoi = port_projected.to_crs(epsg=4326).geometry.iloc[0]

            # --- B. 해당 항구 범위 계산 (줌인용) ---
            bounds = single_port_gdf.geometry.total_bounds
            margin = 0.05  # 개별 항구 줌인이므로 마진을 작게 설정
            p_xlim = (bounds[0] - margin, bounds[2] + margin)
            p_ylim = (bounds[1] - margin, bounds[3] + margin)

            # --- C. 해당 항구 전용 데이터 필터링 ---
            # 출발/도착 항적 필터링
            p_departures = [t for t in self.trips if self.is_leaving(t, port_aoi)]
            p_arrivals = [t for t in self.trips if self.is_entering(t, port_aoi)]
            
            # 정박 선박 필터링 (해당 항구 폴리곤 안에 있는 것만)
            p_anchored = anchored_ships_gdf[anchored_ships_gdf.geometry.within(port_aoi)]

            # --- D. 개별 항구 레이어 생성 ---
            layers = []
            
            # 1. 배경 지도 및 항구 폴리곤 (가장 아래)
            layers.append(single_port_gdf.hvplot(
                # title=f"{port_name} 현황",
                color='red',
                alpha=0.2,
                geo=True,
                tiles='EsriImagery',
                xlim=p_xlim,
                ylim=p_ylim, 
                # frame_width=200,
                frame_width=450,
                frame_height=300
            ))
            
            # 2. 출발 항적
            if p_departures:
                layers.append(mpd.TrajectoryCollection(p_departures).hvplot(color="blue", label="출발", line_width=2, tiles='EsriImagery'))
            
            # 3. 도착 항적
            if p_arrivals:
                layers.append(mpd.TrajectoryCollection(p_arrivals).hvplot(color="orange", label="도착", line_width=2, tiles='EsriImagery'))
            
            # 4. 정박 포인트
            if not p_anchored.empty:
                layers.append(p_anchored.hvplot.points(color='red', label="정박/대기", geo=True, size=5))

            res_plot = hv.Overlay(layers).opts(
                xaxis=None, 
                yaxis=None, 
                show_legend=False,
                bgcolor='#0E1117',
                # 에러가 났던 border_fill_color 대신 hooks를 사용하여 Bokeh 모델을 직접 수정
                hooks=[lambda plot, element: (
                    setattr(plot.state, 'border_fill_color', '#0E1117'),
                    setattr(plot.state.title, 'text_color', 'white')
                )]
            )

            plot_state = self.renderer.get_plot(res_plot).state

            # 레이아웃 최적화
            plot_state.sizing_mode = 'stretch_both'

            # 3. Bokeh의 file_html을 사용하여 HTML 문자열 생성
            html_content = file_html(plot_state, INLINE, "Interactive Map")

            # --- E. 항구별 오버레이 합체 후 리스트에 저장 ---
            self.geo_dict[f'port_map_{i}'] = html_content

    def geo_render_shiptype_count_map(self):
        shiptype_count_summary = self.ais_gdf.groupby('ShipType')['mmsi'].nunique().sort_values(ascending=False)

        # 데이터 Dashboard 시각화
        # fig, ax = plt.figure(figsize=(2, 4))
        fig, ax = plt.subplots(figsize=(2.2, 3.5))
        fig.patch.set_alpha(0) # 배경 투명
        ax.set_aspect('auto')

        # colors = plt.cm.tab20.colors
        colors = ['#FFF264'] * len(shiptype_count_summary)

        shiptype_count_summary.plot(
            kind="barh",
            color=colors,
            ax=ax
        ) 

        ax.invert_yaxis()
        ax.set_ylabel('')

        ax.tick_params(axis='x', colors='#FFF264', labelsize=8)
        ax.tick_params(axis='y', colors='#FFF264', labelsize=8)
        ax.set_facecolor('#282828') # 배경색

        #테두리를 테마색으로 적용
        for spine in ax.spines.values():
            spine.set_color('#FFF264')
            spine.set_linewidth(0.7)

        # [추가] 불필요한 테두리 및 눈금 숨기기 (대시보드용으로 깔끔하게)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        # ax.spines['bottom'].set_visible(False)
        # ax.set_xticks([]) # x축 숫자 숨기기

        # [핵심] 여백 최소화 (이게 없으면 이미지가 잘리거나 여백이 너무 큽니다)
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)

        # 2. 이미지를 Base64 문자열로 인코딩
        img_str = base64.b64encode(buf.read()).decode('utf-8')

        # 3. HTML <img> 태그 생성
        html_content = f'<img src="data:image/png;base64,{img_str}">'

        self.geo_dict['shiptype'] = html_content

    def geo_send_visualization_data(self):
        if self.geo_dict:
            print(f"DEBUG: geo_dict 현재 내용 = {self.geo_dict.keys()}")
            url = "http://localhost:8601/update"
            try:
                r = requests.post(url, json=self.geo_dict) # Form Data로 전송
                print(f"상태 코드: {r.status_code}")

                text_data = r.text
                print(f"서버에러내용: {text_data}")

                print("딕셔너리 정상전송")

            except Exception as e:
                print(f"연결 에러: {e}")
        else:
            print("딕셔너리 비어있음")

    def geo_processing_anchored_ships_gdf(self):
        db_path = "ships.db"
        stop_temp_df = self.compress_ship_data_duckdb_further(db_path=db_path, table_name="ship_logs")

        # 1. DuckDB 연결 (메모리 모드) 및 공간 확장 로드
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        # 2. Pandas DataFrame을 DuckDB 메모리에 등록
        con.register('v_ais_data', stop_temp_df)

        # 3. DuckDB 통합 쿼리 수행
        # - ROW_NUMBER()로 mmsi별 최신 데이터(end_time 기준) 식별
        # - 시간 차이 계산 및 '정박/대기' 상태 필터링을 한 번에 처리
        query = f"""
            WITH latest_status AS (
                SELECT *,
                    ROW_NUMBER() OVER(PARTITION BY mmsi ORDER BY end_time DESC) as rn
                FROM stop_temp_df
            )
            SELECT *
            FROM latest_status
            WHERE rn = 1  -- 각 mmsi별 가장 최신 행만 선택
            AND status LIKE '%정박/대기%'
            AND CAST(end_time AS TIMESTAMP) <= CAST('{self.curr_server_time}' AS TIMESTAMP)
            AND CAST(end_time AS TIMESTAMP) >= CAST('{self.curr_server_time}' AS TIMESTAMP) - INTERVAL 1 HOUR
        """

        # 4. 결과 실행 (Pandas DataFrame으로 반환)
        anchored_ships = con.execute(query).df()

        # 5. GeoDataFrame 변환 (공간 조인 등을 위해)
        geometry = gpd.points_from_xy(anchored_ships['lon'], anchored_ships['lat'])
        anchored_ships_gdf = gpd.GeoDataFrame(anchored_ships, geometry=geometry, crs="EPSG:4326")

        return anchored_ships_gdf
    
    def geo_major_ports_processing(self, start_time, end_time):
        anchored_ships_gdf = self.geo_processing_anchored_ships_gdf()
        # 분석할 항구 리스트 (시각화와 동일하게 설정)
        target_ports = ['BUSAN HANG', 'ULSAN HANG', 'GWANGYANG HANG, HADONG HANG', 'MOKPO HANG']

        # 결과를 담을 메인 딕셔너리
        report_data = {
            "report_info": {
                "analysis_period": {
                    "start": str(start_time),
                    "end": str(end_time)
                },
                "generated_at": datetime.now().isoformat(),
                "target_ports": target_ports
            },
            "ports_analysis": []
        }

        for port_name in target_ports:
            # 1. 데이터 필터링 (기존 로직 동일)
            single_port_gdf = self.ports_gdf[self.ports_gdf['objnam'] == port_name]
            if single_port_gdf.empty: continue
            
            port_projected = single_port_gdf.to_crs(epsg=5179)
            port_projected['geometry'] = port_projected.geometry.buffer(500)
            port_aoi = port_projected.to_crs(epsg=4326).geometry.iloc[0]

            p_departures = [t for t in self.trips if self.is_leaving(t, port_aoi)]
            p_arrivals = [t for t in self.trips if self.is_entering(t, port_aoi)]
            p_anchored = anchored_ships_gdf[anchored_ships_gdf.geometry.within(port_aoi)]

            # 2. 항구별 JSON 구조 생성
            port_entry = {
                "port_name": port_name,
                "summary": {
                    "anchored_count": len(p_anchored),
                    "departure_count": len(p_departures),
                    "arrival_count": len(p_arrivals)
                },
                "details": {
                    "anchored_ships": [
                        {
                            "name": row['ShipName'],
                            "mmsi": int(row['mmsi']),
                            "anchored_since": str(row['start_time'].strftime('%Y-%m-%d %H:%M:%S'))
                        } for _, row in p_anchored.iterrows()
                    ],
                    "departures": [
                        {
                            "name": t.df['ShipName'].iloc[0],
                            "type": t.df['ShipType'].iloc[0],
                            "mmsi": int(str(t.id).split('_')[0]),
                            "event_time": str(t.get_start_time())
                        } for t in p_departures
                    ],
                    "arrivals": [
                        {
                            "name": t.df['ShipName'].iloc[0],
                            "type": t.df['ShipType'].iloc[0],
                            "mmsi": int(str(t.id).split('_')[0]),
                            "event_time": str(t.get_end_time())
                        } for t in p_arrivals
                    ]
                }
            }
            report_data["ports_analysis"].append(port_entry)
            
        major_ports_sum = json.dumps(report_data, indent=4, ensure_ascii=False)

        return major_ports_sum

    def geo_ship_status_extraction_processing(self, end_time):
        db_path = "ships.db"
        stop_temp_df = self.compress_ship_data_duckdb_further(db_path=db_path, table_name="ship_logs")

        # 1. DuckDB 연결 (메모리 모드) 및 공간 확장 로드
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        # 2. Pandas DataFrame을 DuckDB 메모리에 등록
        con.register('v_stop_data', stop_temp_df)

        # 2. 통합 쿼리 수행
        # - ShipName별 최신 행 추출 (tail(1) 대체)
        # - 시간 필터링 및 상태별 카테고리 분류
        query = f"""
            WITH latest_ships AS (
                SELECT 
                    ShipName, mmsi, status, end_time,
                    ROW_NUMBER() OVER(PARTITION BY ShipName ORDER BY end_time DESC, mmsi DESC) as rn
                FROM v_stop_data
            ),
            filtered_ships AS (
                SELECT ShipName, mmsi, status
                FROM latest_ships
                WHERE rn = 1
                AND CAST(end_time AS TIMESTAMP) <= CAST('{end_time}' AS TIMESTAMP)
                AND CAST(end_time AS TIMESTAMP) >= CAST('{end_time}' AS TIMESTAMP) - INTERVAL 1 HOUR
            )
            SELECT 
                ShipName, mmsi, status,
                CASE 
                    WHEN status LIKE '%이동/통과%' THEN 'moving'
                    WHEN status LIKE '%정박/대기%' THEN 'stop'
                    WHEN status LIKE '%저속 운항%' THEN 'slow'
                    ELSE 'others'
                END as category
            FROM filtered_ships
        """
        
        # 3. 데이터 가져오기 및 분류
        result_df = con.execute(query).df()
        
        def to_json_custom(target_df, category_name):
            # 중복 제거 후 리스트 딕셔너리 변환
            subset = target_df[target_df['category'] == category_name][['ShipName', 'mmsi', 'status']].drop_duplicates()
            records = subset.to_dict(orient='records')
            self.geo_dict[category_name] = records
            return json.dumps(records, ensure_ascii=False, indent=4)
        
        # 4. 각 카테고리별 JSON 생성
        moving_ships_json = to_json_custom(result_df, 'moving')
        stop_ships_json = to_json_custom(result_df, 'stop')
        slow_ships_json = to_json_custom(result_df, 'slow')
        
        return moving_ships_json, stop_ships_json, slow_ships_json

    def geo_unusal_ships_extraction_processing(self):
        db_path = "ships.db"
        df = self.compress_ship_data_duckdb_further(db_path=db_path, table_name="ship_logs")

        # 1) 분석 키워드 정의
        turn_keywords = ['우선회', '좌선회']
        speed_keywords = ['가속', '감속']

        # 2) 각 행별로 특이 기동여부 체크
        df['is_turning'] = df['status'].str.contains('|'.join(turn_keywords))
        df['is_speed_changing'] = df['status'].str.contains('|'.join(speed_keywords))

        # 3) ShipName별로 그룹화하여 특이 기동 횟수 집계
        behavior_summary = df.groupby('ShipName').agg(
            turn_count = ('is_turning', 'sum'),
            speed_change_count = ('is_speed_changing', 'sum'),
            total_records = ('status', 'count'),
            status_list=('status', lambda x: list(x.unique()))
        ).reset_index()

        unusual_ships_df = behavior_summary[
            (behavior_summary['turn_count'] >= 4) | 
            (behavior_summary['speed_change_count'] >= 4)
            ].sort_values(by='turn_count', ascending=False)

        unusual_ships_json = unusual_ships_df[['ShipName','turn_count','speed_change_count', 'status_list']].to_dict(orient='records')
        unusual_final_report_json = json.dumps(unusual_ships_json, ensure_ascii=False, indent=4)
        
        return unusual_final_report_json
    
    def create_dynamic_route_prompt(self, num_ships):
        # 배의 개수만큼 프롬프트 안에 들어갈 변수 리스트를 동적으로 생성
        # 예: "선박 1: {ship1}\n선박 2: {ship2}"
        # trajectory_data = "\n".join([f"선박{i+1} 데이터: {{ship{i+1}}}" for i in range(num_ships)])
        trajectory_data = "\n".join([f"선박{i+1} 데이터: {{ship{i+1}}}" for i in range(num_ships)])
        
        system_template = f"""
        # Role
        당신은 대한민국 주변 선박운행을 관제하는 베테랑 해상 관제사(VTS Operator)이자 선박 항적 분석 전문가 입니다. 
        아래 제공된 {num_ships}척의 요약된 항적 데이터(Summarized Trajectory)와 날씨데이터(weather_data) 바탕으로 선박의 이동 패턴과 주요 이벤트를 전문적인 자연어로 묘사해주세요.
        
        #Input Data (Summarized Trajectory)
        1. [선박별 항해 패턴]:
        {trajectory_data}
        2. [현재 날씨 요약]:
        {{weather_data}}

        # Context & Rules (필독)
            - **[데이터 근거]**: 모든 분석은 수치에만 근거하며, 상상이나 추측은 엄격히 금지합니다.
            - markdown 구조를 정확하게 지켜서 출력하세요
        
        # Mission: 리포트 구성 가이드라인
        1. **[선박별 항해 패턴]**:
            - 제공된 1번 데이터를 활용하여 선박별 전체적인 항해패턴을 누락되는 배 없이 간단히 요약
            - "status"필드를 기준으로 하되 start_time과 end_time을 참고하여 특징적인 항목(좌·우선회, 급 감·가속)위주로 요약, 배끼리 데이터가 혼용되지 않도록 주의
            - 관제사가 관심을 가져야 할 특이사항 위주로 간단하게 언급
        2. **[현재 날씨 요약]**:
            - 1번 데이터와 2번 데이터가 ship1 - spot1, ship2 - spot2 ... 이렇게 일대일 대응하므로, 지점명 앞에 선박 이름 명시
            - 현재 날씨에 대해 지점 누락 없이 순서를 그대로 유지하며 지점끼리 데이터가 바뀌지 않도록 유의하여 간단히 요약
            - 관제사가 관심을 가져야 할 날씨의 특이사항(풍향, 풍속 유의파고 등)이 있을 시 간단하게 언급
        3. **[종합 결론]**:  
            - 현재 데이터상에서 나타나는 가장 두드러진 해상 교통 특징 및 관제 주의사항 간략하게 요약하여 기술
        """

        return ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", "{question}")
        ])

    def final_report_chain(self):

        start_time = self.start_server_time[:19]
        end_time = self.curr_server_time[:19]

        print(start_time)
        print(end_time)

        time_diff = pd.to_datetime(end_time) - pd.to_datetime(start_time)

        # 초기작업
        self.geo_init_ports_gdf()
        self.geo_init_zone_gdf()
        self.geo_common_preprocessing(start_time, end_time)
        
        # 대시보드 생성
        self.geo_render_OD_Flow_map(start_time, end_time)
        self.geo_render_major_ports_map()
        self.geo_render_shiptype_count_map()

        clusters_data = self.geo_cluster_data_processing()
        speed_data = self.geo_speed_data_processing(start_time, end_time)
        direction_flow_data = self.geo_direction_flow_data_processing()
        trajs_flow_data = self.geo_trajs_flow_data_processing()
        shiptype_data = self.geo_shiptype_data_processing(start_time, end_time)
        weather_data = self.weather_data_processing()
        major_ports_sum = self.geo_major_ports_processing(start_time, end_time)
        moving_result, stopping_result, slow_result = self.geo_ship_status_extraction_processing(end_time)
        unusual_behavior = self.geo_unusal_ships_extraction_processing()

        # geo_dict 디버깅
        print(self.geo_dict.keys())

        # 대시보드에 정보 전송
        self.geo_send_visualization_data()

        final_report_template = """
            # Role
            당신은 대한민국 해양수산부 소속의 '해상교통관제(VTS) 데이터 분석 전문가' 입니다.
            제공된 통계 데이터를 바탕으로 해상 교통 흐름의 전체적인 패턴을 분석하고 현재 선박 운항 현황을 묘사해 주세요.  

            #Input Data (Summarized Statistics)
            1. [분석 대상 시간]:
            - 시작 시점: {start_time}
            - 종료 시점: {end_time}
            - (약 {time_diff} 동안의 데이터 집계 결과)
            2. [구역별 밀집 현황]: 
            {clusters_data}
            3. [구역별 선박 이동 속도 요약]:
            {speed_data}
            4. [주요 교통 흐름 (방향별 이동 현황)]:
            {direction_flow_data}
            5. [구역 간 주요 유동성(OD Flow) 현황]: 
            {trajs_flow_data}
            6. [선박 유형별 요약]:
            {shiptype_data}
            7. [주요 항만별 선박 입출항 현황]:
            {major_ports_sum}
            8. [선박 상태별 현황 요약]:
            - 순항 중인 선박 리스트: {moving_result}  
            - 정박/대기 중인 선박 리스트: {stopping_result}
            - 저속 운항 중인 선박 리스트: {slow_result}

            9. [특이 기동 선박]:
            {unusual_behavior}

            10. [현재 날씨 요약]:
            {weather_data}
            

            # Context & Rules (필독)
            - **[데이터 근거]**: 모든 분석은 수치에만 근거하며, 상상이나 추측은 엄격히 금지합니다.  
            - **[전문성]**: 병목 구간, 간선 항로, 트래픽 밀도 등 필요에 따라 전문 용어를 적절히 배치하십시오.

            # Mission: 리포트 구성 가이드라인
            1. **[분석 대상 시간]**: 1번 데이터를 자연스러운 문장으로 묘사.  
            2. **[구역별 밀집 현황]**: 
                - 2번 'clusters_data'에서 'total_stay_index'가 높을수록 해당 구역에 더 많은 항적이 밀집되어 있음을 의미합니다.  
                - 이를 기준으로 상위 3개 핵심 해역을 선정하여 테이블로 만들어주고, 테이블 아래 해당 지역의 항적 밀집 패턴을 간단하게 요약하세요.  
            3. **[구역별 선박 이동 속도 현황]**: 
                - 2번 'speed_data'에서 'mean'은 해상구역별 평균속도를 의미합니다.
                - 2번 'speed_data'를 활용하여 각 구역별 선박의 평균 속도 분포를 비교하고, 대한민국 남해안 해역에서 연안과 외해, 그리고 주요 항만 주변 간의 전반적인 핵심 패턴을 설명하세요.   
            4. **[주요 교통 흐름 요약]**: 
                -4번 'direction_flow_data'데이터를 바탕으로 현재 가장 지배적인 이동 방향을 식별하세요. 
                -해당 흐름의 규모 및 이동 속도의 특성을 간략하게 요약하여 기술하세요.  
            5. **[구역 간 주요 항로(OD Flow) 현황]**: 
                - 5번 'trajs_flow_data'에서 'weight'값이 높을수록 해당 경로(origin_zone -> dest_zone)는 주 간선 항로(Main Route)임을 의미합니다.
                - 'trajs_flow_data'를 활용하여 'weight' 기준 상위 5개 항로를 분석하여 대한민국 남해안의 주요 항로 패턴이 어떻게 형성되어 있는지 설명하세요. 
            6. **[선박 유형별 통계]**: 
                - 6번 '선박 유형별 통계'는 반드시 Markdown테이블 형식을 사용하십시오.
                - 6번 'shiptype_data'를 활용하여 선박 유형별 카운트 테이블에 대해 가장 높은 비중을 차지하는 상위 3개 함종이 무엇인지 간단하게 설명하세요. 
            7. **[주요 항만별 선박 입출항 현황]**: 
                - 7번 'major_ports_sum'데이터를 활용하여 주요 항만별 선박 입출항 현황을 다음 예시와 같이 기술해주세요. 
                    예시 1:
                    ▶ 정박/대기 중인 선박: 총 4척
                - PKG-722 임병래 (273331810): 2022-12-01 00:00:06부터 정박 중
                - MHC-565 김포 (352403000): 2022-12-01 00:04:18부터 정박 중
                - MHC-563 고령 (477024700): 2022-12-01 00:01:07부터 정박 중
                - MHC-567 금화 (667002156): 2022-12-01 00:01:24부터 정박 중
                    ▶ 출발/기동 선박: 총 5척
                - ATS 'ATS- 평택': 2022-12-01 12:06:01 에 출발
                - LST 'LST-681 고준봉': 2022-12-01 12:22:20 에 출발
                - LST 'LST-672 덕봉': 2022-12-01 08:20:09 에 출발
                - PKG 'PKG-718 현시학': 2022-12-01 23:00:47 에 출발
                - LST 'LST-673 비봉': 2022-12-01 09:58:31 에 출발
                    ▶ 도착/진입 선박: 총 2척
                - ATS 'ATS- 평택': 2022-12-01 08:54:02 에 도착
                - SS 'SS-061 장보고': 2022-12-02 11:55:04 에 도착
                    
                    위 예시의 "부터 정박 중", " 에 출발", " 에 도착"이라는 조사와 서술어를 하나도 빠짐없이 포함해서 답변해줘.  
            8. **[선박 상태별 현황 요약]**: 
                - 아래 예제와 같이 각 카테고리 별로 'ShipName', 'mmsi' 리스트만 정리해줘. 테이블로 전시하지 마. 
                    ▶ 순항 중인 선박 리스트
                    - AST-688 일천봉(256011000)
                    - DDG-992 율곡이이(431400833)
                    ▶ 정박 중인 선박 리스트
                    - AST-688 일천봉(256011000)
                    - DDG-992 율곡이이(431400833)
                    ▶ 저속 운항 중인 선박 리스트
                    - AST-688 일천봉(256011000)
                    - DDG-992 율곡이이(431400833)

            9. **[주요 선박 특이 기동 상세 분석]**: 
                - 제공된 9번 데이터 'unusual_bahavior'를 바탕으로 답변해줘.
                - 특히 좌선회 및 우선회등 선회가 빈번하거나 가속 감속 등 속도 변화가 잦은 선박을 우선적으로 기술해줘. 
                - 다음 제공된 예시와 같이 작성해줘. 
                    ▶ 특이 기동 식별 보고
                - [선박명]: 'turn_count'회의 변침과 'speed_change_count'회의 속도 변화 포착.
                - 분석 내용: 'status_list'의 상태를 인용하여 기동의 특이점 간략하게 요약.

            10. **[현재 날씨 요약]**: 10번 데이터를 활용하여 현재 기상날씨에 대해 요약하여 설명하고 현재 항해중인 선박들에게 어떤 영향을 줄 수 있는지 설명하세요.
            11. **[종합 결론]**:  
                - 현재 데이터상에서 나타나는 가장 두드러진 해상 교통 특징 및 관제 주의사항 간략하게 요약하여 기술하세요. 

            # Tone & Manner
            - 전문가용 관제 보고서 스타일 (명조체 중심의 정중하고 명확한 문체)
            - 수치와 제공된 데이터 기반 팩트 위주의 서술
        """

        final_report_prompt = ChatPromptTemplate.from_template(final_report_template)

        self.chain = (
            RunnablePassthrough.assign(
                start_time = lambda x: start_time,
                end_time = lambda x: end_time,
                time_diff = lambda x: time_diff,
                clusters_data = lambda x: clusters_data,
                speed_data = lambda x: speed_data,
                direction_flow_data = lambda x: direction_flow_data,
                trajs_flow_data = lambda x: trajs_flow_data,
                shiptype_data = lambda x: shiptype_data,
                weather_data = lambda x: weather_data,
                major_ports_sum = lambda x: major_ports_sum,
                moving_result = lambda x: moving_result,
                stopping_result = lambda x: stopping_result,
                slow_result = lambda x: slow_result,
                unusual_behavior = lambda x: unusual_behavior
            )
            | final_report_prompt
            | self.llm
        )

    def individual_track_chain(self):
        full_path = "ships.db"

        #mmsi로 배 선택
        target_mmsi = self.mmsi_list
        compress_twice = self.compress_ship_data_duckdb_further(db_path=full_path, table_name="ship_logs")

        filtered_mmsi = compress_twice[compress_twice['mmsi'].isin(target_mmsi)].copy()

        self.ship_input_data = {
            f"ship{i+1}": json.dumps(df.to_dict(orient='records'), ensure_ascii=False, default=str, indent=4)
            for i, (_, df) in enumerate(filtered_mmsi.groupby('ShipName', sort=False))
        }

        # mmsi 두개 이상일 때 각각의 최단거리 위치 ---
        last_df = filtered_mmsi.groupby('mmsi').tail(1)
        coords = self.weather_df[['latitude', 'longitude']].values
        
        i = 0

        for _, ship_row in last_df.iterrows():
            # 1. 선박 현재 위치 및 기본 정보 추출
            # mmsi = ship_row['mmsi']
            curr_pos = np.array([ship_row['lat'], ship_row['lon']])
            
            # 2. 거리 계산 및 가장 가까운 지점 인덱스 추출
            dist_seq = np.sum((coords - curr_pos)**2, axis=1)
            closest_i = np.argmin(dist_seq)
            
            # 3. 가장 가까운 지점의 정보를 가져와서 선박 정보와 합치기
            closest_node = self.weather_df.iloc[closest_i].to_dict()
            self.weather_json.append({f'spot{i+1}':closest_node})
            i = i+1

        # 디버깅 로그
        # print("개별항적 날씨데이터 디버깅" + "*" * 10)
        # print(self.weather_json)
        # print("*" * 55)
        # --------------------------------------
        
        # 1. 현재 배의 개수 파악
        num_ships = len(self.ship_input_data)

        # 현재 필터링된 선박 수
        print(num_ships)
        print("*" * 55)

        # 2. 개수에 맞는 템플릿 생성
        dynamic_prompt = self.create_dynamic_route_prompt(num_ships)

        # 4. 실행
        self.chain = dynamic_prompt | self.llm
        
    def run(self):
        print(f"[{QThread.currentThreadId()}] LLM작업 시작 {datetime.now()}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._stream())

    async def _stream(self):
        inputs = {"question": self.question}

        if self.flag:
            self.final_report_chain()
        else :
            self.individual_track_chain()
            inputs["weather_data"] = self.weather_json
            inputs.update(self.ship_input_data) # ship1, ship2 데이터들이 inputs에 합쳐짐

        try:
            buffer = []
            async for chunk in self.chain.astream(inputs):
                if chunk:
                    buffer.append(chunk.content)

                if len(buffer) >= 10:
                    self.report_chunk_fin.emit("".join(buffer))
                    buffer.clear()

            if buffer:
                self.report_chunk_fin.emit("".join(buffer))

            self.report_chunk_fin.emit("".join("\n\n"))

        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.report_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.report_finished.emit()