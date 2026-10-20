import os, base64, io, shapely, textwrap
import asyncio, html
import chainlit as cl
from crewai import Agent, Task, Crew, Process, LLM
from dotenv import load_dotenv
import json
from datetime import timedelta
import movingpandas as mpd
import geopandas as gpd
import duckdb
import os
import uuid
import folium
import re
import pandas as pd
import matplotlib.pyplot as plt
import holoviews as hv
from shapely.geometry import box
from bokeh.embed import file_html
from bokeh.resources import INLINE, CDN
import hvplot.pandas
from chainlit.server import app
from fastapi.responses import HTMLResponse

load_dotenv()

import crewai.llms.cache as _crewai_cache

# CrewAI가 메시지에 cache_breakpoint 필드를 집어넣는 동작을 무력화
_crewai_cache.mark_cache_breakpoint = lambda msg: msg

# =====================================================================
# 1. [군 폐쇄망/보안] 메모리 전용 맵 저장소 및 FastAPI 엔드포인트
# =====================================================================
# 디스크에 파일을 쓰지 않고 서버 RAM에만 HTML을 유지합니다.
INMEMORY_MAP_STORE: dict[str, str] = {}


@app.get("/api/inmemory-map/{map_id}", response_class=HTMLResponse)
async def serve_inmemory_map(map_id: str):
    """브라우저가 iframe을 통해 요청 시 메모리(RAM)에서 HTML을 직접 반환합니다."""
    html_content = INMEMORY_MAP_STORE.get(map_id)
    if html_content:
        return HTMLResponse(content=html_content)
    return HTMLResponse(
        "<h3>지도를 불러올 수 없습니다 (만료됨).</h3>", status_code=404
    )

app.router.routes.insert(0, app.router.routes.pop())

@cl.on_chat_start
async def start():
    await cl.Message(
        content="👋 안녕하세요! 조사하고 싶은 주제를 입력하시면 AI 크루가 실시간으로 협업을 시작합니다."
    ).send()


@cl.on_message
async def run_crew(message: cl.Message):
    topic = message.content
    
    current_step = None
    logs_history = []  # 상세 작업 내역을 누적할 버퍼 리스트

    # Agent 실행 단계별 Callback
    def agent_step_callback(agent_output):
        nonlocal current_step
        if not current_step:
            return
        
        log_text = getattr(agent_output, 'log', str(agent_output))
        tool_name = getattr(agent_output, 'tool', None)
        log_lower = log_text.lower()

        # 기본값 설정 (일반 실행)
        step_type = "run"
        step_icon = "brain"
        action_desc = "생각을 정리하고 있습니다..."

        # 1. Tool 실행 단계 감지
        if tool_name or "action:" in log_lower or "tool:" in log_lower:
            step_type = "tool"
            step_icon = "wrench"  # Lucide 아이콘: 스패너
            name_str = tool_name if tool_name else "외부 도구"
            action_desc = f"도구 사용 중: {name_str}"

        # 2. 벡터 검색 / 임베딩 / DB 조회 감지
        elif any(k in log_lower for k in ["search", "vector", "embed", "retriev", "rag", "database"]):
            step_type = "retrieval"  # 필요 시 "embedding"으로 지정 가능
            step_icon = "database"   # Lucide 아이콘: 데이터베이스
            action_desc = "지식 베이스 검색 및 정보 수집 중..."

        # 3. LLM 프롬프트 추론 및 답변 생성 단계 감지
        elif "thought:" in log_lower or "final answer:" in log_lower:
            step_type = "llm"
            step_icon = "sparkles"  # Lucide 아이콘: 반짝임/AI
            # Thought 문구 파싱
            for line in log_text.split("\n"):
                line = line.strip()
                if line.startswith("Thought:"):
                    action_desc = line.replace("Thought:", "").strip()
                    break

        # 4. Step 상태 동적 적용 및 UI 업데이트 (Fade 효과)
        current_step.type = step_type
        current_step.icon = step_icon
        current_step.name = f"[{step_type.upper()}] {action_desc}"

        # Chainlit UI에 동기적으로 변경사항 반영
        cl.run_sync(current_step.update())

    # Task 완료 시 Callback
    def task_callback(task_output):
        nonlocal current_step
        task_desc = getattr(task_output, 'description', '태스크 완료')
        logs_history.append(f"📌 **[Task Complete]** {task_desc}\n")
        
        if current_step:
            current_step.name = f"📌 [태스크 완료] {task_desc[:30]}..."
            cl.run_sync(current_step.update())

    def geo_speed_processed_duckdb():
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

        zones_gdf = gpd.GeoDataFrame({'zone_id': ids, 'name': names}, 
                                    geometry=polygons, crs="EPSG:4326")
        
        db_path = "../../pj7(AIS_Simulator_Client/ships.db"
        con = duckdb.connect(database=db_path)
        con.execute("INSTALL spatial; LOAD spatial;")

        # 2. 기준 구역(zones_gdf)을 DuckDB에 등록
        # 공간 조인을 위해 zones_gdf를 WKB로 변환하여 임시 테이블로 등록합니다.
        zones_gdf['geom_wkb'] = zones_gdf['geometry'].to_wkb()
        con.register('v_zones', zones_gdf[['name', 'geom_wkb']])

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

        return speed_stats_df, zones_gdf
    
    def render_od_flow():
        renderer = hv.renderer('bokeh')

        _, _, aggregator = processing()
        if len(aggregator.flows) > 0:
            flows = aggregator.get_flows_gdf()
        else:
            print("생성된 항로(Flow)가 없습니다. 파라미터를 조정하세요.")
            return
        
        if len(aggregator.clusters) > 0:
            clusters = aggregator.get_clusters_gdf()
        else:
            print("생성된 군집(Cluster)이 없습니다. 파라미터를 조정하세요.")
            return
        
        # 1. DuckDB 연결 및 공간 확장 로드 (기존 유지)
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL spatial; LOAD spatial;")

        zone_speed_stats, zones_gdf = geo_speed_processed_duckdb()
        
        # 2. 결과 데이터(zone_speed_stats)를 DuckDB에 등록
        # 이미 계산된 통계치를 다시 DB로 보내 연산의 중심으로 삼습니다.
        con.register('v_speed_stats', zone_speed_stats)

        # [중요] zones_gdf는 이미 v_zones로 등록되어 있다고 가정합니다. 
        # 만약 세션이 끊겼다면 아래 한 줄을 다시 실행하세요.
        zones_gdf['geom_wkb'] = zones_gdf['geometry'].to_wkb()
        con.register('v_zones', zones_gdf[['name', 'geom_wkb']])

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

        plot_state = renderer.get_plot(flow_cluster_map).state
        plot_state.sizing_mode = 'stretch_both' # 레이아웃 최적화

        # 3. Bokeh의 file_html을 사용하여 HTML 문자열 생성
        html_content = file_html(plot_state, INLINE, "Interactive Map")

        # 2) 파일 저장 없이 고유 ID를 부여하여 메모리(RAM) 딕셔너리에 저장
        map_id = str(uuid.uuid4())
        INMEMORY_MAP_STORE[map_id] = html_content

        return f"/api/inmemory-map/{map_id}"

    def compress_ship_data_duckdb_further(db_path, table_name,min_lon=125.678, max_lon=131.229, max_lat=36.001):
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

    def make_ship_data_dict():
        db_path = "../../pj7(AIS_Simulator_Client/ships.db"
        stop_temp_df = compress_ship_data_duckdb_further(db_path=db_path, table_name="ship_logs")

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

        subset = result_df[result_df['category'] == 'moving'][['ShipName', 'mmsi', 'status']].drop_duplicates()
        records = subset.to_dict(orient='records')
        moving_list = records

        subset = result_df[result_df['category'] == 'stop'][['ShipName', 'mmsi', 'status']].drop_duplicates()
        records = subset.to_dict(orient='records')
        stop_list = records

        subset = result_df[result_df['category'] == 'slow'][['ShipName', 'mmsi', 'status']].drop_duplicates()
        records = subset.to_dict(orient='records')
        slow_list = records

        def transform_data(data_list):
            try:
                # 데이터가 [{...}, {...}] 리스트 형태라면 바로 변환됩니다.
                if isinstance(data_list, list):
                    res_list = pd.DataFrame(data_list)
                else:
                    # 데이터가 만약 딕셔너리 형태라면 리스트로 감싸서 변환
                    res_list = pd.DataFrame([data_list])
                return res_list
            except Exception as e:
                # 에러 발생 시 빈 데이터프레임이라도 만들어야 대시보드가 안 터집니다.
                print(f"변환 실패: {e}")
                res_list = pd.DataFrame(columns=['ShipName', 'mmsi'])
                return res_list

        moving_df = transform_data(moving_list)
        stop_df = transform_data(stop_list)
        slow_df = transform_data(slow_list)

        ship_data_dict = {
            "순항": moving_df,
            "정박": stop_df,
            "저속운항": slow_df,
        }
        return ship_data_dict


    def generate_ship_table_widget(ship_data_dict: dict[str, pd.DataFrame]) -> str:
        """ship_data_dict를 받아 순수 HTML/JS로 동작하는 반응형 테이블 위젯을 생성하고

        메모리 라우트 URL을 반환합니다.
        """
        # 1. 각 상태별 데이터프레임을 JSON 직렬화가 가능한 dict 형태로 변환
        serialized_data = {}
        for status, df in ship_data_dict.items():
            # 필요한 주요 컬럼만 추출 (예: ShipName, mmsi, speed, type 등)
            cols = [c for c in ["ShipName", "mmsi", "speed", "type"] if c in df.columns]
            target_df = df[cols] if cols else df
            serialized_data[status] = target_df.to_dict(orient="records")

        json_payload = json.dumps(serialized_data, ensure_ascii=False)

        # 2. 외부 라이브러리(CDN) 전혀 없는 100% 오프라인 다크테마 HTML/JS 조립
        html_content = f"""<!DOCTYPE html>
    <html lang="ko">
    <head>
    <meta charset="UTF-8">
    <style>
        body {{
            margin: 0; padding: 12px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0E1117; color: #E2E8F0; font-size: 13px;
        }}
        .header {{ font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #38BDF8; }}
        .controls {{ display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }}
        .radio-group {{ display: flex; gap: 10px; background: #1E293B; padding: 4px 8px; border-radius: 6px; }}
        .radio-label {{ cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 12px; }}
        .search-input {{
            flex: 1; min-width: 160px; background: #1E293B; border: 1px solid #334155;
            color: #fff; padding: 5px 8px; border-radius: 6px; font-size: 12px; outline: none;
        }}
        .search-input:focus {{ border-color: #38BDF8; }}
        .table-container {{
            max-height: 180px; overflow-y: auto; border: 1px solid #334155; border-radius: 6px;
        }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{ background: #1E293B; padding: 8px; position: sticky; top: 0; font-weight: 600; color: #94A3B8; font-size: 12px; }}
        td {{ padding: 6px 8px; border-bottom: 1px solid #1E293B; font-size: 12px; }}
        tr:hover {{ background-color: #1E293B; }}
        /* 스크롤바 디자인 */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 3px; }}
    </style>
    </head>
    <body>
        <div class="header">📋 함정 상세 목록</div>
        <div class="controls">
            <div class="radio-group">
                <label class="radio-label"><input type="radio" name="status" value="순항" checked onchange="updateTable()"> 순항</label>
                <label class="radio-label"><input type="radio" name="status" value="정박" onchange="updateTable()"> 정박</label>
                <label class="radio-label"><input type="radio" name="status" value="저속운항" onchange="updateTable()"> 저속운항</label>
            </div>
            <input type="text" id="searchInput" class="search-input" placeholder="🔍 함정명 또는 MMSI 검색" oninput="updateTable()">
        </div>
        <div class="table-container">
            <table id="shipTable">
                <thead>
                    <tr id="tableHeader"></tr>
                </thead>
                <tbody id="tableBody"></tbody>
            </table>
        </div>

    <script>
        const rawData = {json_payload};

        function updateTable() {{
            const status = document.querySelector('input[name="status"]:checked').value;
            const query = document.getElementById('searchInput').value.trim().toLowerCase();
            const records = rawData[status] || [];

            // 1. 검색어 필터링 (ShipName or MMSI)
            const filtered = records.filter(row => {{
                const name = String(row.ShipName || '').toLowerCase();
                const mmsi = String(row.mmsi || '').toLowerCase();
                return name.includes(query) || mmsi.includes(query);
            }});

            // 2. 헤더 구성
            const headerTr = document.getElementById('tableHeader');
            headerTr.innerHTML = '';
            if (records.length > 0) {{
                Object.keys(records[0]).forEach(key => {{
                    const th = document.createElement('th');
                    th.textContent = key;
                    headerTr.appendChild(th);
                }});
            }}

            // 3. 본문 렌더링
            const tbody = document.getElementById('tableBody');
            tbody.innerHTML = '';
            if (filtered.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:#64748B; padding:16px;">조회된 데이터가 없습니다.</td></tr>';
                return;
            }}

            filtered.forEach(row => {{
                const tr = document.createElement('tr');
                Object.values(row).forEach(val => {{
                    const td = document.createElement('td');
                    td.textContent = (val !== null && val !== undefined) ? val : '-';
                    tr.appendChild(td);
                }});
                tbody.appendChild(tr);
            }});
        }}

        // 초기 실행
        updateTable();
    </script>
    </body>
    </html>"""

        # 3. 디스크 저장 없이 RAM 딕셔너리에 저장 후 엔드포인트 URL 발급
        widget_id = str(uuid.uuid4())
        INMEMORY_MAP_STORE[widget_id] = html_content
        return f"/api/inmemory-map/{widget_id}"

    def generate_maritime_map() -> str:
        """인터랙티브 맵을 생성하여 public 폴더에 저장하고 웹 경로를 반환합니다."""
        # 1. 맵 객체 생성 (예시: 부산 해역 중심)
        m = folium.Map(
            location=[35.05, 129.0],
            zoom_start=10,
            tiles="CartoDB positron",  # 깔끔한 테마
        )

        # 2. 마커 및 데이터 추가
        folium.Marker(
            [35.05, 129.0],
            popup="<b>부산-가덕 해역</b><br>총 정박 지수: 100.0",
            tooltip="부산-가덕 해역",
            icon=folium.Icon(color="red", icon="info-sign"),
        ).add_to(m)

        # 3. public/maps 디렉터리에 저장
        save_dir = "public/maps"
        os.makedirs(save_dir, exist_ok=True)

        # 브라우저 캐싱 방지를 위해 고유한 파일명 부여
        filename = f"map_{uuid.uuid4().hex[:8]}.html"
        file_path = os.path.join(save_dir, filename)
        m.save(file_path)

        # 4. Chainlit 웹 서빙 경로 반환
        return f"/public/maps/{filename}"

    def processing():
        # 1. DuckDB 파일 연결 및 공간 확장 로드
        db_path = "../../pj7(AIS_Simulator_Client/ships.db"
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
            AND speed > 0
            ORDER BY MMSI, t ASC  -- 이 줄이 필수입니다!
        """

        # 3. DuckDB 결과를 Pandas로 가져오기
        df = con.execute(query).df()

        # 4. WKB 컬럼을 이용해 즉시 GeoDataFrame 생성
        # 이 방식은 points_from_xy보다 대용량 처리 시 훨씬 빠릅니다.
        ais_gdf = gpd.GeoDataFrame(
            df, 
            geometry=shapely.from_wkb(df['geom_wkb'].apply(bytes)),
            crs="EPSG:4326"
        ).set_index('t')

        # 3. MovingPandas 집계 (클러스터 추출)
        traj_collection = mpd.TrajectoryCollection(ais_gdf, 'mmsi', min_length=1000)
        n_traj_collection = mpd.DouglasPeuckerGeneralizer(traj_collection).generalize(tolerance=0.001) #가장 빠름
        # 전처리 추가(실험 필요)
        trips = mpd.ObservationGapSplitter(n_traj_collection).split(gap=timedelta(minutes=120))
        aggregator = mpd.TrajectoryCollectionAggregator(
            trips, max_distance=100000, min_distance=2000, min_stop_duration=timedelta(minutes=120)
        )

        return ais_gdf, trips, aggregator
    
    def geo_render_test():        
        ais_gdf, _, _ = processing()

        shiptype_count_summary = ais_gdf.groupby('ShipType')['mmsi'].nunique().sort_values(ascending=False)

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
        plt.close(fig)
        return img_str
    # ==========================================
    # CrewAI 구성
    # ==========================================
    # llm = LLM(model="gpt-4o-mini", temperature=0.7)
    # llm = LLM(
    #     api_key="ai",
    #     model="hosted_vllm/openai/gpt-oss-20b",
    #     base_url="http://192.168.0.110:8000/v1"
    # )
    llm = LLM(
            # model="hosted_vllm/openai/gpt-oss-120b",
            # model="hosted_vllm/openai/nvidia/nemotron-3-nano",
            model="hosted_vllm/qwen/qwen3-coder-30b",
            base_url="http://192.168.0.110:9000/v1"
        )
    vllm = LLM(
        model="hosted_vllm/RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic",
        base_url="http://192.168.0.110:8000/v1",
        api_key="ai"
    )
    # llm = LLM(
    #     model="fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    #     # model="fireworks_ai/accounts/fireworks/models/muse-glimmer-30b",
    #     # model="fireworks_ai/accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    #     base_url="https://api.fireworks.ai/inference/v1",
    #     api_key=os.getenv("FIREWORKS_API_KEY"),
    #     max_retries=3,
    #     temperature=0
    # )

    researcher = Agent(
        role="수석 연구원",
        goal=f"'{topic}'에 대한 핵심 정보 조사",
        backstory="기술 및 시장 분석 전문가",
        verbose=True,
        llm=vllm,
        step_callback=agent_step_callback
    )

    writer = Agent(
        role="수석 기술 작가",
        goal="이해하기 쉬운 요약 보고서 작성",
        backstory="전문 기술 작가",
        verbose=True,
        llm=vllm,
        step_callback=agent_step_callback
    )

    research_task = Task(
        description=f"'{topic}'에 대해 상세히 조사하고 가능하면 핵심 3가지를 정리하세요",
        expected_output="3가지 주요 발견 사항",
        agent=researcher,
        callback=task_callback
    )

    write_task = Task(
        description="조사된 내용을 바탕으로 서론/본론/결론이 있는 깔끔한 마크다운 리포트를 작성하세요.",
        expected_output="마크다운 보고서",
        agent=writer,
        callback=task_callback
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential
    )

    # ==========================================
    # 1. Step (실시간 Fade 업데이트 + 접이식 아코디언 상세 내역)
    # ==========================================
    async with cl.Step(name="🚀 [Workflow] CrewAI 실행 준비 중...", type="run") as step:
        current_step = step
        
        step.name = "🔍 [수석 연구원] 정보 수집 및 리서치 진행 중..."
        await step.update()

        # CrewAI 비동기 실행
        # result = await crew.kickoff_async()

        # 작업 완료 후 step.name과 step.output 설정
        step.name = "✅ [Workflow 완료] 에이전트 상세 작업 내역 보기 (클릭)"
        # 누적된 히스토리를 output에 할당하면 아래 화살표를 눌렀을 때 렌더링됩니다.
        step.output = "\n\n".join(logs_history) if logs_history else "상세 실행 로그가 존재하지 않습니다."
        await step.update()

    # ==========================================
    # 2. 결과 리포트 스트리밍 출력
    # ==========================================
    # final_output = getattr(result, 'raw', str(result))


    # 1. 지도 생성 후 웹 경로 획득
    map_url = generate_maritime_map()
    render_url = geo_render_test()
    mp_url = render_od_flow()
    ship_data = make_ship_data_dict()
    table_widget_url = generate_ship_table_widget(ship_data)

    # 2. iframe 블록 생성 (스크롤 가능 높이 280px 지정)
    table_iframe_block = textwrap.dedent(f"""\
<!-- WIDGET_START -->
<iframe src="{table_widget_url}" width="100%" height="280px" style="border: 1px solid #334155; border-radius: 8px; margin: 14px 0;" scrolling="no"></iframe>
<!-- WIDGET_END -->""")

    # 단일 인터렉티브 맵
    map_iframe = f"""<iframe src="{map_url}" width="50%" height="450px" style="border: 1px solid #e2e8f0; border-radius: 8px; margin: 12px 0;"></iframe>"""

    # 다중 인터렉티브 맵
    dual_map_block = f"""<!-- DUAL_MAP_START -->
<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin: 16px 0;">
    <iframe src="{map_url}" style="width: 49%; min-width: 300px; height: 400px; border: 1px solid #e2e8f0; border-radius: 8px;"></iframe>
    <iframe src="{map_url}" style="width: 49%; min-width: 300px; height: 400px; border: 1px solid #e2e8f0; border-radius: 8px;"></iframe>
</div>
<!-- DUAL_MAP_END -->"""

    # 4. 주석으로 감싼 iframe 블록 생성 (기존 스트리밍 정규식과 완벽 호환)
    shiptype_html = f"""<!-- IMG_START -->
<iframe srcdoc='<body style="margin:0;display:flex;"><img src="data:image/png;base64,{render_url}" style="max-width:100%; border-radius:8px;"></body>' width="100%" height="380px" style="border:none;" scrolling="no"></iframe>
<!-- IMG_END -->"""

    interactive_map = textwrap.dedent(f"""\
<!-- BOKEH_MAP_START -->
<iframe sandbox="allow-scripts allow-same-origin" srcdoc="{mp_url}" width="100%" height="400" style="border: 1px solid #334155; border-radius: 8px; margin: 12px 0;"></iframe>
<!-- BOKEH_MAP_END -->""")

    interactive_both = textwrap.dedent(f"""\
<!-- BOKEH_MAP_START -->
<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin: 16px 0;">
    <iframe src="{mp_url}" width="49%" height="400" style="border: 1px solid #334155; border-radius: 8px; margin: 12px 0;"></iframe>
    <iframe src="{mp_url}" width="49%" height="400" style="border: 1px solid #334155; border-radius: 8px; margin: 12px 0;"></iframe>
</div>
<!-- BOKEH_MAP_END -->""")

    test_output = f"""
### 1. [분석 대상 시간]
- 수집된 AIS 데이터 기반 집계 결과입니다.
{table_iframe_block}

### 2. [구역별 밀집 현황]

| 해역명 | 총 정박 지수 | 비고 |
|---|---|---|
| 부산-가덕 해역 | 100.0 | 해상 교통량 및 정박 밀집도가 가장 높은 핵심 작전 구역 |
| 여수-통영 외해 | 99.0 | 높은 밀집도를 보이는 주요 해역 |
| 시모노세키-기타큐슈 해역 | 75.0 | 국제 통로로서의 중요성이 높은 구역 |

{interactive_both}

### 9. [주요 선박 특이 기동 상세 분석]
* **[FF-959 부산]**: 81회의 변침과 11회의 속도 변화 포착.
* **[SS-078 유관순]**: 49회의 변침과 22회의 속도 변화 포착.
* **[LST-683 향로봉]**: 29회의 변침과 17회의 속도 변화 포착.
* **[DDG-992 율곡이이]**: 27회의 변침과 4회의 속도 변화 포착.
* **[SS-062 이천]**: 21회의 변침과 9회의 속도 변화 포착.

{shiptype_html}

### 10. [종합 결론]

현재 해상 전장 상황에 대한 종합 분석 결과입니다.

1. **해역 밀집도 및 속도 현황**: 부산-가덕 해역이 정박 지수 100으로 가장 높은 밀집도를 보이고 있으며, 여수-통영 외해(99)와 시모노세키-기타큐슈 해역(75)이 그 뒤를 잇고 있습니다. 속도 측면에서는 부산-가덕 해역의 평균 속도가 1.13노트로 매우 낮게 나타나 정박 및 저속 기동이 집중되고 있음을 알 수 있으며, 반면 서남해 외해는 평균 16.16노트, 최대 23.3노트로 활발한 기동이 이루어지고 있습니다.

2. **교통 흐름 및 이동 방향**: 주요 항로로는 부산-가덕 해역에서 거제-가덕 외해로 향하는 흐름(Weight 15)이 가장 강력하며, 거제-가덕 외해에서 여수-통영 외해로 이어지는 흐름(Weight 9)이 관찰됩니다. 선박들의 주요 이동 방향은 남서진(15척, 평균 10.3노트)이 가장 빈번하며, 서진(9척, 평균 8.1노트) 순으로 나타나 전반적인 흐름이 서남향을 향하고 있습니다.

3. **항만 및 선박 운항 상태**: 부산항(BUSAN HANG)은 4척이 정박 중이며, LST-681 고준봉 등 다수의 상륙함과 함정들이 입출항을 반복하고 있습니다. 광양-여수 인근 항만(GWANGYANG HANG 등)에서는 독도함(LPH-6111)이 정박 중인 것이 확인됩니다. 현재 이동 중인 선박은 AGS-신천지, AOE-59 화천 등 13척이며, 정박/대기 중인 선박은 DDH-981 최영, FF-959 부산 등 15척입니다. 또한 LST-676 위봉 등 3척은 저속 운항 중입니다.
"""

    # final_msg = cl.Message(content="", elements=[image_element])
    # await final_msg.send()

    # # 단어 단위 실시간 스트리밍
    # words = test_output.split(" ")
    # for word in words:
    #     await final_msg.stream_token(word + " ")
    #     await asyncio.sleep(0.005)

    final_msg = cl.Message(content="")
    await final_msg.send()

    # BOKEH_MAP, BOKEH, DUAL_MAP, IMG 등 어떤 주석이든 _START ~ _END 구간을 통째로 분리
    pattern = (
        r"(<!--\s*[A-Z_]+_START\s*-->.*?<!--\s*[A-Z_]+_END\s*-->|"
        r"<iframe[\s\S]*?</iframe>)"
    )
    
    # 텍스트와 미디어 블록을 분리 (DOTALL 플래그로 줄바꿈 포함 매칭)
    tokens = re.split(pattern, test_output, flags=re.DOTALL | re.IGNORECASE)

    for token in tokens:
        if not token:
            continue

        token_stripped = token.strip()

        # 미디어 블록(iframe 또는 주석으로 감싼 이미지/지도) 판별
        is_media_block = (
            token_stripped.startswith("<!--") and "_START" in token_stripped
        ) or token_stripped.lower().startswith("<iframe")

        if is_media_block:
            # HTML 코드는 띄어쓰기로 쪼개지 않고 통째로 출력 (앞뒤 빈 줄로 마크다운 충돌 방지)
            await final_msg.stream_token("\n\n" + token + "\n\n")
            await asyncio.sleep(0.05)  # 브라우저 DOM 렌더링 안정화를 위한 짧은 대기
        else:
            # 일반 마크다운 텍스트는 기존처럼 단어 단위 타이핑 효과
            words = token.split(" ")
            for word in words:
                if word:
                    await final_msg.stream_token(word + " ")
                    await asyncio.sleep(0.005)

    # for char in final_output:
    #     await final_msg.stream_token(char)
    #     await asyncio.sleep(0.002)

    await final_msg.update()