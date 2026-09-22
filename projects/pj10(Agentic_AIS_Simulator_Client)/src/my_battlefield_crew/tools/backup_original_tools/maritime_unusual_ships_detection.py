import os
import json
import pandas as pd
from crewai.tools import tool

@tool('Maritime Unusual Ships Detector')
def unusual_ships_detector() -> str:
    """
    기능:
        수집된 선박 항해 데이터(AIS)를 분석하여 급선회(우선회/좌선회) 또는 급변속(가속/감속)이 
        빈번하게 발생한 '특이/이상 기동 선박' 목록을 추출하고 JSON 리포트로 반환합니다.

    사용 시점 (Trigger Conditions):
        - 사용자가 '이상 기동', '특이 기동', '지그재그 항해', '급선회', '급변속' 선박에 대해 질문할 때
        - 의심스러운 항해 패턴을 보이거나 위험 기동을 수행 중인 선박 현황 요청 시
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_root = os.path.dirname(current_dir)
    preprocessed_path = os.path.join(parent_root, "cache", "ais_compressed_step2.parquet")

    if not os.path.exists(preprocessed_path):
        return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 돌려주세요"})

    # 1. 필요한 컬럼만 I/O 로딩
    df = pd.read_parquet(preprocessed_path, columns=['ShipName', 'status'])

    # 2. C-level 고속 문자열 매칭
    df['turn_count'] = df['status'].str.contains('우선회|좌선회', regex=True, na=False).astype(int)
    df['speed_change_count'] = df['status'].str.contains('가속|감속', regex=True, na=False).astype(int)

    # 3. 100% C-level 수치 고속 집계 (status_list 생성 제거!)
    summary = df.groupby('ShipName', as_index=False)[['turn_count', 'speed_change_count']].sum()

    # 4. 필터링 (선회 또는 변속 4회 이상)
    unusual_ships_df = summary[
        (summary['turn_count'] >= 20) | (summary['speed_change_count'] >= 20)
    ].sort_values(by='turn_count', ascending=False)

    # 5. JSON 변환
    unusual_ships_json = unusual_ships_df.to_dict(orient='records')

    return json.dumps(unusual_ships_json, ensure_ascii=False, indent=4)









### 아래 코드는 status_list, 즉 구체적인 특이 기동 로글르 출력하고 싶을 때 사용한다. 

# import os
# from crewai.tools import tool
# import json
# import pandas as pd
# import geopandas as gpd



# @tool('Maritime Unusual Ships Detector')
# def unusual_ships_detector() -> str:
#     """
#     기능:
#         수집된 선박 항해 데이터(AIS)를 분석하여 급선회(우선회/좌선회) 또는 급변속(가속/감속)이 
#         빈번하게 발생한 '특이/이상 기동 선박' 목록을 추출하고 JSON 리포트로 반환합니다.

#     사용 시점 (Trigger Conditions):
#         - 사용자가 '이상 기동', '특이 기동', '지그재그 항해', '급선회', '급변속' 선박에 대해 질문할 때
#         - 의심스러운 항해 패턴을 보이거나 위험 기동을 수행 중인 선박 현황 요청 시
#     """
#     current_dir = os.path.dirname(os.path.abspath(__file__))
#     parent_root = os.path.dirname(current_dir)

#     preprocessed_path = os.path.join(parent_root, "cache", "ais_compressed_step2.parquet")

#     if not os.path.exists(preprocessed_path):
#         return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 돌려주세요"})

#     df = pd.read_parquet(preprocessed_path)


#     # 1) 분석 키워드 정의
#     # turn_keywords = ['우선회', '좌선회']
#     # speed_keywords = ['가속', '감속']

#     # 2) 각 행별로 특이 기동여부 체크
#     df['is_turning'] = df['status'].str.contains('우선회|좌선회', regex=True)
#     df['is_speed_changing'] = df['status'].str.contains('가속|감속', regex=True)

#     # 3) ShipName별로 그룹화하여 특이 기동 횟수 집계
#     behavior_summary = df.groupby('ShipName').agg(
#         turn_count = ('is_turning', 'sum'),
#         speed_change_count = ('is_speed_changing', 'sum'),
#         total_records = ('status', 'count'),
#         status_list=('status', lambda x: list(x.unique()))
#     ).reset_index()

#     unusual_ships_df = behavior_summary[
#         (behavior_summary['turn_count'] >= 30) | 
#         (behavior_summary['speed_change_count'] >= 30)
#         ].sort_values(by='turn_count', ascending=False)

#     unusual_ships_json = unusual_ships_df[['ShipName','turn_count','speed_change_count', 'status_list']].to_dict(orient='records')
     
#     # print(json.dumps(unusual_ships_json, ensure_ascii=False, indent=4))
    
#     return json.dumps(unusual_ships_json, ensure_ascii=False, indent=4)

# if __name__ == "__main__":
#     unusual_ships_detector()







