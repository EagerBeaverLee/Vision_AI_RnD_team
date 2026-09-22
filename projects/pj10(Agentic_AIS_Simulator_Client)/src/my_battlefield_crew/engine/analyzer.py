# engine/analyzer.py
import os
from datetime import timedelta
import geopandas as gpd
import movingpandas as mpd
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="movingpandas")


def run_cluster_analysis(input_parquet="./cache/filtered_ais.parquet"):
    print("🔮 [2단계] MovingPandas & DBSCAN 클러스터 분석 시작...")
    
    if not os.path.exists(input_parquet):
        raise FileNotFoundError(f"필터링된 데이터 파일이 없습니다. 1단계를 먼저 실행하세요: {input_parquet}")
        
    # 1단계 결과물 고속 로드
    ais = gpd.read_parquet(input_parquet)

    # 궤적 추출 및 단순화
    MIN_LENGTH = 1000 
    TRIP_ID = 'mmsi'
    
    traj_collection = mpd.TrajectoryCollection(ais, TRIP_ID, min_length=MIN_LENGTH)
    traj_collection = mpd.DouglasPeuckerGeneralizer(traj_collection).generalize(tolerance=0.001)
    trips = mpd.ObservationGapSplitter(traj_collection).split(gap=timedelta(minutes=120))

    print(f"- 생성된 궤적 수: {len(traj_collection)}")
    print(f"- 추출된 개별 트립 수: {len(trips)}")

    # 항적 통합 및 정박 클러스터링 집계
    aggregator = mpd.TrajectoryCollectionAggregator(
        trips, max_distance=100000, min_distance=2000, min_stop_duration=timedelta(minutes=120)
    )

    flows = aggregator.get_flows_gdf()
    clusters = aggregator.get_clusters_gdf()

    # GeoJSON 저장 에러 유발 컬럼 제거
    if 'start_point' in flows.columns: 
        flows = flows.drop(columns=['start_point', 'end_point'])

    # 최종 분석 데이터 로컬 파일로 저장(캐싱)
    flows.to_file("./cache/flows.geojson", driver="GeoJSON")
    clusters.to_file("./cache/clusters.geojson", driver="GeoJSON")
    
    print("✅ [2단계] 분석 및 최종 파일 캐싱 완료! (./cache/flows.geojson, ./cache/clusters.geojson)")
    return flows, clusters





# if __name__ == "__main__":

#     run_cluster_analysis()