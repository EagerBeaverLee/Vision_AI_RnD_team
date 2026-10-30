# tools/maritime_density.py
import duckdb
import json
import geopandas as gpd
import asyncio
# from shapely.geometry import box
from crewai.tools import tool
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


def _run_maritime_density_analysis(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("밀집도 및 혼잡도", "구역별 정박 밀집도 정보를 통계적 요약 정보를 반환합니다")
    
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")

    clusters_gdf = context.processing_list["aggregator"].get_clusters_gdf()

    # 4. DuckDB 공간 조인 및 최종 통계 처리
    # Geometry를 DuckDB가 이해할 수 있는 WKB로 변환하여 등록
    clusters_gdf['geom_wkb'] = clusters_gdf['geometry'].to_wkb()
    context.processing_list["zone_gdf"]['geom_wkb'] = context.processing_list["zone_gdf"]['geometry'].to_wkb()

    con.register('v_clusters', clusters_gdf[['n', 'geom_wkb']])
    con.register('v_zones', context.processing_list["zone_gdf"][['name', 'geom_wkb']])

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
    cluster_summary = con.execute(final_query).df()

    result = {
        "cluster_density": cluster_summary.to_dict(orient="records")
    }
    if context.ui_handler:
        context.ui_handler.on_tool_complete("밀집도 및 혼잡도")
        context.ui_handler.on_tool_result("밀집도 및 혼잡도")
    
    return json.dumps(result, ensure_ascii=False, indent=4)

def analyze_maritime_density(context: SimulationContext):
    @tool("Maritime Zone Density Analyzer")
    async def _analyze_maritime_density() -> str:
        """
        미리 분석되어 저장된 해상 클러스터(Cluster) 데이터를 로드하고
        지정된 서·남해안 군사 관심 구역(Zone)과 공간 조인(Spatial Join)하여 
        구역별 정박 밀집도 정보를 통계적 요약 JSON 문자열로 반환합니다.
        """
        if context.ui_handler:
            context.ui_handler.on_tool_start("밀집도 및 혼잡도", "구역별 정박 밀집도 정보를 통계적 요약 정보를 반환합니다")
        # 동기 로직을 별도 쓰레드에서 비동기로 실행하여 파이프라인(이벤트 루프) 멈춤을 방지
        output_json = await asyncio.to_thread(_run_maritime_density_analysis, context=context)
        
        print(output_json)
        return output_json
    return _analyze_maritime_density



###################
#original_below
##################

# @tool("Maritime Zone Density Analyzer")
# def analyze_maritime_density() -> str:
#     """
#     미리 분석되어 저장된 해상 클러스터(Cluster) 데이터를 로드하고
#     지정된 서·남해안 군사 관심 구역(Zone)과 공간 조인(Spatial Join)하여 
#     구역별 정박 밀집도 정보를 통계적 요약 JSON 문자열로 반환합니다.
#     """
#     cluster_path = "./cache/clusters.geojson"

#     if not os.path.exists(cluster_path):
#         return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 먼저 돌려주세요."})

#     clusters = gpd.read_file(cluster_path)

#     zones_gdf = get_zones_gdf()

#     # 공간 조인 및 Aggregation 연산
#     named_clusters = gpd.sjoin(clusters, zones_gdf, how="inner", predicate="within")

#     cluster_summary = named_clusters.groupby('name')['n'].agg(['sum']).rename(columns={'sum':'total_stay_index'}).reset_index()
#     cluster_summary = cluster_summary.sort_values(by='total_stay_index', ascending=False)

#     result = {
#         "cluster_density": cluster_summary.to_dict(orient="records")
#     }
    
#     print(json.dumps(result, ensure_ascii=False, indent=4))
    
#     return json.dumps(result, ensure_ascii=False, indent=4)


