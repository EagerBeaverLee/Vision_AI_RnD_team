import duckdb
import numpy as np
import json
import asyncio
from crewai.tools import tool
import pandas as pd
import geopandas as gpd
from my_battlefield_crew.chainlit_app.schemas import SimulationContext
from my_battlefield_crew.engine.preprocessor import compress_ship_data_duckdb_further


def _run_direction_analysis(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("주요 방향 분석", "관심 해역에서 선박들의 주요 이동향 정보를 반환합니다")
    
    comp_ship_data = compress_ship_data_duckdb_further(db_path=context.db_path, table_name="ship_logs", min_time=context.start_time, max_time=context.end_time)
    
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
    result_df = con.execute(query).df().to_dict(orient="records")
    
    if context.ui_handler:
        context.ui_handler.on_tool_complete("주요 방향 분석")
        context.ui_handler.on_tool_result("주요 방향 분석")

    return json.dumps(result_df, ensure_ascii=False, indent=4)


def get_direction_analysis(context: SimulationContext):
    @tool("Maritime Traffic Direction Analyzer")
    async def _get_direction_analysis() -> str:
        """
        미리 분석되어 저장된 해상 주요 선박 향(Direction) 데이터를 로드하고
        관심 해역에서 선박들의 주요 이동향 정보를 요약하여 JSON문자열로 반환합니다.
        """
        if context.ui_handler:
            context.ui_handler.on_tool_start("주요 방향 분석", "관심 해역에서 선박들의 주요 이동향 정보를 반환합니다")
        # 동기식 파이썬 연산을 쓰레드풀로 넘겨 비동기 이벤트 루프 멈춤 현상 방지
        output_json = await asyncio.to_thread(_run_direction_analysis, context=context)
        return output_json
    return _get_direction_analysis













######################
## original_backup ###
######################

# @tool("Maritime Traffic Direction Analyzer")
# def get_direction_analysis() -> str:
#     """
#     미리 분석되어 저장된 해상 주요 선박 향(Direction) 데이터를 로드하고
#     관심 해역에서 선박들의 주요 이동향 정보를 요약하여 JSON문자열로 반환합니다.
#     """
    
#     preprocessed_path = "./cache/ais_compressed_step2.parquet"

#     if not os.path.exists(preprocessed_path):
#         return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 먼저 돌려주세요."})

#     df = pd.read_parquet(preprocessed_path)
    
#     # '이동' 중인 선박만 추출
#     cruising_raw = df[df['status'] != '정박/대기'].copy()
    
#     cruising = cruising_raw.groupby('mmsi').agg({
#         'first_course': 'last',
#         'avg_speed': 'mean'}).reset_index()
    
#     if cruising.empty:
#         return "현재 이동 중인 주요 선박 흐름 없음"

#     # --- 1. 방향 그룹화 (Binning) ---
#     # 0~360도를 8방위로 나누기 
#     # 북쪽(North)은 337.5~22.5도 사이이므로, 계산 편의를 위해 범위 조절.
#     bins = [-0.1, 22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5, 360.1]
#     labels = ['북', '북동', '동', '남동', '남', '남서', '서', '북서', '북'] 

#     cruising['direction_group'] = pd.cut(cruising['first_course'], bins=bins, labels=labels, ordered=False)
    
#     # --- 2. 통계 계산 ---
#     # 각 방향별 선박 수 계산 및 0인 항목 제거
#     flow_counts = cruising['direction_group'].value_counts()
#     flow_counts = flow_counts[flow_counts > 0]

#     unique_labels = []
#     for l in labels:
#         if l not in unique_labels:
#             unique_labels.append(l)
    
#     cruising['sin'] = np.sin(np.radians(cruising['first_course']))
#     cruising['cos'] = np.cos(np.radians(cruising['first_course']))
    
#     agg_flow = cruising.groupby('direction_group', observed=True).agg({
#         'mmsi': 'count',
#         'avg_speed': 'mean',
#         'sin': 'mean',
#         'cos': 'mean'
#     })
    
#     # 텍스 요약 생성
#     flow_reports = []
    
#     for direction in unique_labels: 
#         if direction in agg_flow.index:
#             data = agg_flow.loc[direction]
#             count = int(data['mmsi'])
    
#             if count == 0: continue
    
#             curr_avg_speed = float(data['avg_speed'])
#             vec_avg = float(np.degrees(np.arctan2(data['sin'], data['cos'])) % 360)
            
#             flow_reports.append({
#                 "direction":f"{direction}진",
#                 "ship_count": count,
#                 "average_speed_knot": round(curr_avg_speed, 1),
#                 "vector_course_deg": round(vec_avg, 1)
#             })
            
#     # print(json.dumps(flow_reports, ensure_ascii=False, indent=4))

#     return json.dumps(flow_reports, ensure_ascii=False, indent=4)


