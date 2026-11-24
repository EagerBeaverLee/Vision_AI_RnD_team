import duckdb
import asyncio
from crewai.tools import tool
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from my_battlefield_crew.chainlit_app.schemas import SimulationContext
from my_battlefield_crew.engine.preprocessor import compress_ship_data_duckdb_further
from my_battlefield_crew.map.visualizer import generate_ship_table_widget

def _run_ship_status_extraction(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("기동 상태별 현황", "선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류한 정보를 반환합니다")

    ais_gdf = context.processing_list["ais_gdf"]
    shiptype_count_summary = ais_gdf.groupby('ShipType')['mmsi'].nunique().sort_values(ascending=False)
    data_dict_shiptype = shiptype_count_summary.to_dict()    

    stop_temp_df = compress_ship_data_duckdb_further(db_path=context.realtime_db_path, table_name="ship_logs", min_time=context.time.start_time, max_time=context.time.end_time)

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
            AND CAST(end_time AS TIMESTAMP) <= CAST('{context.time.end_time}' AS TIMESTAMP)
            AND CAST(end_time AS TIMESTAMP) >= CAST('{context.time.end_time}' AS TIMESTAMP) - INTERVAL 1 HOUR
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
        return records
    
    # 4. 각 카테고리별 JSON 생성
    moving_ships = to_json_custom(result_df, 'moving')
    stop_ships = to_json_custom(result_df, 'stop')
    slow_ships = to_json_custom(result_df, 'slow')

    render_map_dict = {
        "순항": moving_ships,
        "정박": stop_ships,
        "저속운항": slow_ships,
    }

    html_content = generate_ship_table_widget(render_map_dict)

    # 내부적으로 map_store 저장 + iframe 블록 조립 완료
    context.attach_table_block(key="ship_voyage_status", html_content=html_content, height=450)

    final_report = {
        "ship_types": data_dict_shiptype,
        "moving_ships": moving_ships,
        "stop_ships": stop_ships, 
        "slow_ships": slow_ships
    }
    if context.ui_handler:
        context.ui_handler.on_tool_complete("기동 상태별 현황")
        context.ui_handler.on_tool_result("기동 상태별 현황")

    return json.dumps(final_report, ensure_ascii=False, indent=4)


def ship_status_extraction(context: SimulationContext):
    @tool('Maritime Ships Voyage Status Analyzer')
    async def _ship_status_extraction() -> str:
        """
        현재 시점 기준 선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류하여 분석합니다.
        선박들의 현재 상태를 묻는 질문이나 선박 유형별 통계 관련 질문이 들어올 때 이 도구를 사용하세요.
        """
        if context.ui_handler:
            context.ui_handler.on_tool_start("기동 상태별 현황", "선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류한 정보를 반환합니다")
        # 데이터 처리 및 필터링 연산을 백그라운드 쓰레드에서 비동기 실행
        output_json = await asyncio.to_thread(_run_ship_status_extraction, context=context)
        return output_json
    return _ship_status_extraction
