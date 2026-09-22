import os
import json
import geopandas as gpd
import asyncio
# from shapely.geometry import box
from crewai.tools import tool
from data.spatial_data.zone_config import get_zones_gdf


def _run_traffic_flow_analysis() -> str:
    flow_path = "./cache/flows.geojson"

    if not os.path.exists(flow_path):
        return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 먼저 돌려주세요."}, ensure_ascii=False)

    flows = gpd.read_file(flow_path)
    zones_gdf = get_zones_gdf()

    # 공간 조인 및 Aggregation 연산
    flows['start_point'] = flows.geometry.apply(lambda x: x.coords[0])
    flows['end_point'] = flows.geometry.apply(lambda x: x.coords[-1])

    start_gdf = gpd.GeoDataFrame(
        flows, 
        geometry=gpd.points_from_xy([p[0] for p in flows.start_point], [p[1] for p in flows.start_point]), 
        crs=4326
    )
    end_gdf = gpd.GeoDataFrame(
        flows, 
        geometry=gpd.points_from_xy([p[0] for p in flows.end_point], [p[1] for p in flows.end_point]), 
        crs=4326
    )

    start_join = gpd.sjoin(start_gdf, zones_gdf, how="left")
    start_join = start_join[~start_join.index.duplicated(keep='first')]
    flows['origin_zone'] = start_join['name']

    end_join = gpd.sjoin(end_gdf, zones_gdf, how="left")
    end_join = end_join[~end_join.index.duplicated(keep='first')]
    flows['dest_zone'] = end_join['name']

    flow_summary = flows.groupby(['origin_zone', 'dest_zone'])['weight'].sum().reset_index()
    flow_summary = flow_summary.sort_values(by='weight', ascending=False).head(13)

    result = {
        "main_routes": flow_summary.to_dict(orient="records")
    }

    return json.dumps(result, ensure_ascii=False, indent=4)



@tool("Maritime Traffic Flow Analyzer")
async def analyze_traffic_flow() -> str:
    """
    미리 분석되어 저장된 해상 주요 선박 흐름(Flow) 데이터를 로드하고
    지정된 서·남해안 군사 관심 구역(Zone)과 공간 조인(Spatial Join)하여 
    구역간 주요 교통 흐름 정보를 통계적 요약 JSON 문자열로 반환합니다.
    """
    # 무거운 공간 조인 연산을 별도 쓰레드로 분리하여 비동기 실행
    output_json = await asyncio.to_thread(_run_traffic_flow_analysis)
    return output_json







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

