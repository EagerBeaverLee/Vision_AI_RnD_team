# tools/maritime_density.py
import os
import json
import geopandas as gpd
# from shapely.geometry import box
from crewai.tools import tool
from data.spatial_data.zone_config import get_zones_gdf

@tool("Maritime Zone Density Analyzer")
def analyze_maritime_density() -> str:
    """
    미리 분석되어 저장된 해상 클러스터(Cluster) 데이터를 로드하고
    지정된 서·남해안 군사 관심 구역(Zone)과 공간 조인(Spatial Join)하여 
    구역별 정박 밀집도 정보를 통계적 요약 JSON 문자열로 반환합니다.
    """
    cluster_path = "./cache/clusters.geojson"

    if not os.path.exists(cluster_path):
        return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 먼저 돌려주세요."})

    clusters = gpd.read_file(cluster_path)

    zones_gdf = get_zones_gdf()

    # 공간 조인 및 Aggregation 연산
    named_clusters = gpd.sjoin(clusters, zones_gdf, how="inner", predicate="within")

    cluster_summary = named_clusters.groupby('name')['n'].agg(['sum']).rename(columns={'sum':'total_stay_index'}).reset_index()
    cluster_summary = cluster_summary.sort_values(by='total_stay_index', ascending=False)

    result = {
        "cluster_density": cluster_summary.to_dict(orient="records")
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=4))
    
    return json.dumps(result, ensure_ascii=False, indent=4)



# if __name__ == "__main__":
# # #     # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
#     analyze_maritime_density()
