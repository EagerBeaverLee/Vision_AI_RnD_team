# tools/maritime_speed.py
import os
import json
import asyncio
import geopandas as gpd
import duckdb
from crewai.tools import tool
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


def _run_mean_speed_analysis(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("구역별 속도", "해상 작전 통제 구역(Zone)별 선박들의 평균 속도, 최고 속도 및 트래픽 수에 대한 정보를 반환합니다")
    
    # con = duckdb.connect(database=context.db_path)
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")

    con.execute(f"ATTACH '{context.db_path}' AS sqlite_db (TYPE sqlite, READ_ONLY);")
    con.execute("USE sqlite_db;")
    

    # 2. 기준 구역(zones_gdf)을 DuckDB에 등록
    # 공간 조인을 위해 zones_gdf를 WKB로 변환하여 임시 테이블로 등록합니다.
    context.processing_list["zone_gdf"]['geom_wkb'] = context.processing_list["zone_gdf"]['geometry'].to_wkb()
    con.register('v_zones', context.processing_list["zone_gdf"][['name', 'geom_wkb']])

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
            AND timestamp >= '{context.start_time}' 
            AND timestamp <= '{context.end_time}'
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
    data_dict_speed = speed_stats_df.to_dict(orient="records")

    if context.ui_handler:
        context.ui_handler.on_tool_complete("구역별 속도")
        context.ui_handler.on_tool_result("구역별 속도")
    return json.dumps(data_dict_speed, ensure_ascii=False, indent=4)


def analyze_mean_speed(context: SimulationContext):
    @tool("Maritime Zone Mean Speed Analyzer")
    async def _analyze_mean_speed() -> str:
        """해상 작전 통제 구역(Zone)별 선박들의 평균 속도, 최고 속도 및 트래픽 수를 분석합니다. 
        구역별 속도 통계나 속도 요약 관련 질문이 들어왔을 때 반드시 이 도구를 사용해야 합니다."""
        if context.ui_handler:
            context.ui_handler.on_tool_start("구역별 속도", "해상 작전 통제 구역(Zone)별 선박들의 평균 속도, 최고 속도 및 트래픽 수에 대한 정보를 반환합니다")
        # 공간 조인 및 속도 통계 연산을 백그라운드 쓰레드에서 비동기 실행
        output_json = await asyncio.to_thread(_run_mean_speed_analysis, context=context)
        return output_json
    return _analyze_mean_speed




#######################
###Original Backup ###
#######################

# @tool("Maritime Zone Mean Speed Analyzer")
# def analyze_mean_speed() -> str:
#     """해상 작전 통제 구역(Zone)별 선박들의 평균 속도, 최고 속도 및 트래픽 수를 분석합니다. 
#     구역별 속도 통계나 속도 요약 관련 질문이 들어왔을 때 반드시 이 도구를 사용해야 합니다."""
#     # 안전한 절대 경로 추적 (loader와 동일 메커니즘)
#     current_dir = os.path.dirname(os.path.abspath(__file__))
#     parent_root = os.path.dirname(current_dir)
    
#     cache_path = os.path.join(parent_root, "cache", "filtered_ais.parquet")
                              
#     ais = gpd.read_parquet(cache_path)

#     zones_gdf = get_zones_gdf()
    
#     # 2. 좌표계 통일 및 공간 조인 (sjoin)
#     if ais.crs != zones_gdf.crs:
#         ais = ais.to_crs(zones_gdf.crs)
        
#     joined_gdf = gpd.sjoin(ais, zones_gdf, how='left', predicate='within')
#     joined_gdf = joined_gdf.dropna(subset=['name'])
    
#     # 3. 구역별 속도 통계 산출 (주신 핵심 로직)
#     zone_speed_stats = joined_gdf.groupby('name')['speed'].agg(['mean', 'max', 'count'])
#     zone_speed_stats = zone_speed_stats.sort_values(by='mean', ascending=False).reset_index()
    
#     # 4. JSON 변환 및 리턴
#     data_dict_speed = zone_speed_stats.to_dict(orient="records")
#     # print(json.dumps(data_dict_speed, ensure_ascii=False, indent=4))
    
#     return json.dumps(data_dict_speed, ensure_ascii=False, indent=4)


# if __name__ == "__main__":
#     # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
#     analyze_mean_speed()