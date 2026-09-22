# engine/loader.py
import os
import pandas as pd
import geopandas as gpd
from engine.preprocessor import compress_ship_data_py, compress_ship_data_py_further

def load_and_filter_ais(csv_path="./src/my_battlefield_crew/data/AIS_data/Sample01_AIS_new_category_final.csv", 
                        start_time="2022-12-01 00:00:00", 
                        end_time="2022-12-02 23:00:00"):
    print("📍 [1단계] 원본 데이터 로드 및 시공간 필터링 시작...")
    
    if not os.path.isabs(csv_path):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_root = os.path.dirname(current_dir)

    csv_path = os.path.join(parent_root, "data", "AIS_data", "Sample01_AIS_new_category_final.csv")
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"원본 CSV 파일을 찾을 수 없습니다: {csv_path}")

    ais_df = pd.read_csv(csv_path) 
    
    # 한반도 남해 지역 공간 필터링 경계
    min_lon, max_lon = 125.678, 131.229
    max_lat = 36.001
    
    filtered_df = ais_df[
        (ais_df['longitude'] >= min_lon) & 
        (ais_df['longitude'] <= max_lon) & 
        (ais_df['latitude'] <= max_lat)
    ]

    # GeoDataFrame 변환
    ais_gdf = gpd.GeoDataFrame(
        filtered_df, 
        geometry=gpd.points_from_xy(filtered_df.longitude, filtered_df.latitude), 
        crs="EPSG:4326"
    )
    
    # 시간 필터링
    ais_gdf['t'] = pd.to_datetime(ais_gdf['timestamp'], format='mixed', utc=True).dt.tz_localize(None)
    ais_gdf = ais_gdf.set_index('t')
    ais_gdf = ais_gdf[(ais_gdf['timestamp'] >= start_time) & (ais_gdf['timestamp'] <= end_time)]
    
    # 캐시 디렉토리 생성 및 고속 Parquet 저장
    os.makedirs("./cache", exist_ok=True)
    output_path = "./cache/filtered_ais.parquet"
    ais_gdf.to_parquet(output_path)
    print(f"분석 시간 from{start_time} to {end_time}")
    print(f"✅ [1단계] 필터링 완료. 데이터 개수: {len(ais_gdf)}개 -> {output_path} 저장됨.")

    print("⚙️ 1차 항적 데이터 압축 진행 중...")
    df_compressed_1 = compress_ship_data_py(ais_gdf)
    cache_step_1 = "./cache/ais_compressed_step1.parquet"
    df_compressed_1.to_parquet(cache_step_1)

    print("⚙️ 2차 항적 데이터 압축 진행 중...")
    df_compressed_2 = compress_ship_data_py_further(df_compressed_1)
    cache_step_2 = "./cache/ais_compressed_step2.parquet"
    df_compressed_2.to_parquet(cache_step_2)

    print(f"✅ 데이터 전처리 완료 후 'df_compressed_1' {len(df_compressed_1)}개 'df_compressed_2' {len(df_compressed_2)}개 & Cache 폴더 저장 완료")

    return True

# if __name__ == "__main__":
#     # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
#     load_and_filter_ais()

def load_shp_file() -> gpd.GeoDataFrame:
    """프로젝트 내 저장된 주요 항만 (.shp)파일은 로드"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_root = os.path.dirname(current_dir)

    shp_path = os.path.join(parent_root, "data","spatial_data","major_ports.shp")

    print(f"🗺️ Shapefile 로드 시도 경로: {shp_path}")
    if not os.path.exists(shp_path):
        raise FileNotFoundError(f"저장한 위치에서 Shapefile 세트를 찾을 수 없습니다: {shp_path}")
    
    ports_gdf = gpd.read_file(shp_path)

    if ports_gdf.crs is None:
        ports_gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    else:
        ports_gdf = ports_gdf.to_crs("EPSG:4326")

    return ports_gdf

# if __name__ == "__main__":
#     # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
#     gdf=load_shp_file()

#     print(f"로딩 성공! 총 {len(gdf)}개의 공간 객체(행)이 발견되었습니다.")
#     print(f" 현재 정의된 좌표계(CRS):{gdf.crs}")
#     print("\n [컬럼 구성목록]")
#     print(list(gdf.columns))

#     print("\n [상위 5개 데이터 미리보기]")

#     pd.set_option('display.max_columns', None)
#     pd.set_option('display.width', 1000)

#     print(gdf.head(5))