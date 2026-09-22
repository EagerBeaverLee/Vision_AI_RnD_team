import os
from crewai.tools import tool
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point


@tool('Maritime Ships Voyage Status Analyzer')
def ship_status_extraction() -> str:
    """
    현재 시점 기준 선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류하여 분석합니다.
    선박들의 현재 상태를 묻는 질문이나 선반 유형별 통계 관련 질문이 들어올 때 이 도구를 사용하세요.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_root = os.path.dirname(current_dir)

    ais_path = os.path.join(parent_root, "cache","filtered_ais.parquet")
    preprocessed_path = os.path.join(parent_root, "cache", "ais_compressed_step2.parquet")

    if not os.path.exists(ais_path) or not os.path.exists(preprocessed_path):
        return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 돌려주세요"})

    ais = gpd.read_parquet(ais_path)
    df = pd.read_parquet(preprocessed_path)

    # if not isinstance(df, gpd.GeoDataFrame):
    #     geometry = [Point(xy) for xy in zip(df['lon'], df['lat'])]
    #     df = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    
    #선박 유형별 통계 데이터 추출
    shiptype_count_summary = ais.groupby('ShipType')['mmsi'].nunique().sort_values(ascending=False)
    data_dict_shiptype = shiptype_count_summary.to_dict()
    
    # 선박 이동 상태별 요약을 위한 전처리
    df['end_time'] = pd.to_datetime(df['end_time'], utc=True)
    end_time = df['end_time'].max()
    end_time = pd.to_datetime(end_time, utc=True) 
    df = df.sort_values(['ShipName','mmsi'])
    df = df.groupby('ShipName').tail(1)

    #이동 통과 filtering
    moving_condition = (
        ((end_time - df['end_time']) <= pd.Timedelta(hours=1)) &
        (df['status'].str.contains("이동/통과"))
    )

    #정박/대기  filtering
    stop_condition = (
        ((end_time - df['end_time']) <= pd.Timedelta(hours=1)) &
        (df['status'].str.contains("정박/대기"))
    )

    #저속운항 filtering 
    slow_moving_condition = (
        ((end_time - df['end_time']) <= pd.Timedelta(hours=1)) &
        (df['status'].str.contains("저속 운항"))
    )
    #선박 유형별 통계 데이터 json 변환 
    # shiptype_json = json.dumps(data_dict_shiptype, ensure_ascii=False, indent=4)
    
    #이동/통과 중인 선박 리스트 추출 및 json변환
    moving_df = df[moving_condition]
    moving_ships = moving_df[['ShipName','mmsi','status']].drop_duplicates().to_dict(orient='records')
    # moving_ships_json = json.dumps(moving_ships, ensure_ascii=False, indent=4)

    #정박/대기 중인 선박 리스트 추출 및 json변환
    stop_df = df[stop_condition]
    stop_ships = stop_df[['ShipName','mmsi','status']].drop_duplicates().to_dict(orient='records')
    # stop_ships_json = json.dumps(stop_ships, ensure_ascii=False, indent=4)

    #정박/대기 중인 선박 리스트 추출 및 json변환
    slow_df = df[slow_moving_condition]
    slow_ships = slow_df[['ShipName','mmsi','status']].drop_duplicates().to_dict(orient='records')
    # slow_ships_json = json.dumps(slow_ships, ensure_ascii=False, indent=4)
    
    final_report = {
        "ship_types": data_dict_shiptype,
        "moving_ships": moving_ships,
        "stop_ships": stop_ships, 
        "slow_ships": slow_ships
    }
    # print(json.dumps(final_report, ensure_ascii=False, indent=4) ) #temp

    return json.dumps(final_report, ensure_ascii=False, indent=4)

# if __name__ == "__main__":
    # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
    # ship_status_extraction()