import os
import numpy as np
import json
from crewai.tools import tool
import pandas as pd
import geopandas as gpd

@tool("Maritime Traffic Direction Analyzer")
def get_direction_analysis() -> str:
    """
    미리 분석되어 저장된 해상 주요 선박 향(Direction) 데이터를 로드하고
    관심 해역에서 선박들의 주요 이동향 정보를 요약하여 JSON문자열로 반환합니다.
    """
    
    preprocessed_path = "./cache/ais_compressed_step2.parquet"

    if not os.path.exists(preprocessed_path):
        return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 먼저 돌려주세요."})

    df = pd.read_parquet(preprocessed_path)
    
    # '이동' 중인 선박만 추출
    cruising_raw = df[df['status'] != '정박/대기'].copy()
    
    cruising = cruising_raw.groupby('mmsi').agg({
        'first_course': 'last',
        'avg_speed': 'mean'}).reset_index()
    
    if cruising.empty:
        return "현재 이동 중인 주요 선박 흐름 없음"

    # --- 1. 방향 그룹화 (Binning) ---
    # 0~360도를 8방위로 나누기 
    # 북쪽(North)은 337.5~22.5도 사이이므로, 계산 편의를 위해 범위 조절.
    bins = [-0.1, 22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5, 360.1]
    labels = ['북', '북동', '동', '남동', '남', '남서', '서', '북서', '북'] 

    cruising['direction_group'] = pd.cut(cruising['first_course'], bins=bins, labels=labels, ordered=False)
    
    # --- 2. 통계 계산 ---
    # 각 방향별 선박 수 계산 및 0인 항목 제거
    flow_counts = cruising['direction_group'].value_counts()
    flow_counts = flow_counts[flow_counts > 0]

    unique_labels = []
    for l in labels:
        if l not in unique_labels:
            unique_labels.append(l)
    
    cruising['sin'] = np.sin(np.radians(cruising['first_course']))
    cruising['cos'] = np.cos(np.radians(cruising['first_course']))
    
    agg_flow = cruising.groupby('direction_group', observed=True).agg({
        'mmsi': 'count',
        'avg_speed': 'mean',
        'sin': 'mean',
        'cos': 'mean'
    })
    
    # 텍스 요약 생성
    flow_reports = []
    
    for direction in unique_labels: 
        if direction in agg_flow.index:
            data = agg_flow.loc[direction]
            count = int(data['mmsi'])
    
            if count == 0: continue
    
            curr_avg_speed = float(data['avg_speed'])
            vec_avg = float(np.degrees(np.arctan2(data['sin'], data['cos'])) % 360)
            
            flow_reports.append({
                "direction":f"{direction}진",
                "ship_count": count,
                "average_speed_knot": round(curr_avg_speed, 1),
                "vector_course_deg": round(vec_avg, 1)
            })
            
    # print(json.dumps(flow_reports, ensure_ascii=False, indent=4))

    return json.dumps(flow_reports, ensure_ascii=False, indent=4)

# if __name__ == "__main__":
    # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
    # get_direction_analysis()

