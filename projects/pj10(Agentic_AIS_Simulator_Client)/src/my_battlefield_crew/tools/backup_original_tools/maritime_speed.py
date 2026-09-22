# tools/maritime_speed.py
import os
import json
import geopandas as gpd
from crewai.tools import tool
from data.spatial_data.zone_config import get_zones_gdf

@tool("Maritime Zone Mean Speed Analyzer")
def analyze_mean_speed() -> str:
    """해상 작전 통제 구역(Zone)별 선박들의 평균 속도, 최고 속도 및 트래픽 수를 분석합니다. 
    구역별 속도 통계나 속도 요약 관련 질문이 들어왔을 때 반드시 이 도구를 사용해야 합니다."""
    # 안전한 절대 경로 추적 (loader와 동일 메커니즘)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_root = os.path.dirname(current_dir)
    
    cache_path = os.path.join(parent_root, "cache", "filtered_ais.parquet")
                              
    ais = gpd.read_parquet(cache_path)

    zones_gdf = get_zones_gdf()
    
    # 2. 좌표계 통일 및 공간 조인 (sjoin)
    if ais.crs != zones_gdf.crs:
        ais = ais.to_crs(zones_gdf.crs)
        
    joined_gdf = gpd.sjoin(ais, zones_gdf, how='left', predicate='within')
    joined_gdf = joined_gdf.dropna(subset=['name'])
    
    # 3. 구역별 속도 통계 산출 (주신 핵심 로직)
    zone_speed_stats = joined_gdf.groupby('name')['speed'].agg(['mean', 'max', 'count'])
    zone_speed_stats = zone_speed_stats.sort_values(by='mean', ascending=False).reset_index()
    
    # 4. JSON 변환 및 리턴
    data_dict_speed = zone_speed_stats.to_dict(orient="records")
    # print(json.dumps(data_dict_speed, ensure_ascii=False, indent=4))
    
    return json.dumps(data_dict_speed, ensure_ascii=False, indent=4)


# if __name__ == "__main__":
#     # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
#     analyze_mean_speed()