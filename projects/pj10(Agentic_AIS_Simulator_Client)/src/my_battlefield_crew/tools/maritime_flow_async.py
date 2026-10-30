import duckdb
import json
import geopandas as gpd
import asyncio
# from shapely.geometry import box
from crewai.tools import tool
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


def _run_traffic_flow_analysis(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("주요 교통 흐름", "구역간 주요 교통 흐름 정보를 반환합니다")

    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")

    flows = context.processing_list["aggregator"].get_flows_gdf()

    # 2. 데이터 등록을 위한 WKB 변환
    # flows는 LineString geometry를 가짐
    flows['geom_wkb'] = flows.geometry.to_wkb()
    context.processing_list["zone_gdf"]['geom_wkb'] = context.processing_list["zone_gdf"]['geometry'].to_wkb()

    con.register('v_flows', flows[['weight', 'geom_wkb']])
    con.register('v_zones', context.processing_list["zone_gdf"][['name', 'geom_wkb']])

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

    result = {
        "main_routes": flow_summary_df.to_dict(orient="records")
    }
    if context.ui_handler:
        context.ui_handler.on_tool_complete("주요 교통 흐름")
        context.ui_handler.on_tool_result("주요 교통 흐름")
    return json.dumps(result, ensure_ascii=False, indent=4)


def analyze_traffic_flow(context: SimulationContext):
    @tool("Maritime Traffic Flow Analyzer")
    async def _analyze_traffic_flow() -> str:
        """
        미리 분석되어 저장된 해상 주요 선박 흐름(Flow) 데이터를 로드하고
        지정된 서·남해안 군사 관심 구역(Zone)과 공간 조인(Spatial Join)하여 
        구역간 주요 교통 흐름 정보를 통계적 요약 JSON 문자열로 반환합니다.
        """
        if context.ui_handler:
            context.ui_handler.on_tool_start("주요 교통 흐름", "구역간 주요 교통 흐름 정보를 반환합니다")
        # 무거운 공간 조인 연산을 별도 쓰레드로 분리하여 비동기 실행
        output_json = await asyncio.to_thread(_run_traffic_flow_analysis, context=context)
        return output_json
    return _analyze_traffic_flow







######################
## Original_backup
######################

# @tool("Maritime Traffic Flow Analyzer")
# def analyze_traffic_flow() -> str:
#     """
#     미리 분석되어 저장된 해상 주요 선박 흐름(Flow) 데이터를 로드하고
#     지정된 서·남해안 군사 관심 구역(Zone)과 공간 조인(Spatial Join)하여 
#     구역간 주요 교통 흐름 정보를 통계적 요약 JSON 문자열로 반환합니다.
#     """
    
#     flow_path = "./cache/flows.geojson"

#     if not os.path.exists(flow_path):
#         return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 먼저 돌려주세요."})

#     flows = gpd.read_file(flow_path)

#     zones_gdf = get_zones_gdf()

#     # 공간 조인 및 Aggregation 연산
#     flows['start_point'] = flows.geometry.apply(lambda x: x.coords[0])
#     flows['end_point'] = flows.geometry.apply(lambda x: x.coords[-1])

#     start_gdf = gpd.GeoDataFrame(flows, geometry=gpd.points_from_xy([p[0] for p in flows.start_point], [p[1] for p in flows.start_point]), crs=4326)
#     end_gdf = gpd.GeoDataFrame(flows, geometry=gpd.points_from_xy([p[0] for p in flows.end_point], [p[1] for p in flows.end_point]), crs=4326)

#     start_join = gpd.sjoin(start_gdf, zones_gdf, how="left")
#     start_join = start_join[~start_join.index.duplicated(keep='first')]
#     flows['origin_zone'] = start_join['name']

#     end_join = gpd.sjoin(end_gdf, zones_gdf, how="left")
#     end_join = end_join[~end_join.index.duplicated(keep='first')]
#     flows['dest_zone'] = end_join['name']

#     flow_summary = flows.groupby(['origin_zone', 'dest_zone'])['weight'].sum().reset_index()
#     flow_summary = flow_summary.sort_values(by='weight', ascending=False).head(13)

#     result = {
#         "main_routes": flow_summary.to_dict(orient="records")
#     }
    
#     # print(json.dumps(result, ensure_ascii=False, indent=4))
    
#     return json.dumps(result, ensure_ascii=False, indent=4)

