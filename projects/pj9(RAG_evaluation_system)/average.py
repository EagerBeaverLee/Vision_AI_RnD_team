import pandas as pd

def json_to_csv_pandas(json_file, csv_file):
    # 1. JSON 파일 읽어오기
    df = pd.read_json(json_file, encoding='utf-8')
    
    # 2. CSV 파일로 저장 
    # (index=False: 의미 없는 숫자 인덱스 열 방지, utf-8-sig: 엑셀 한글 깨짐 방지)
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    
    print(f"✨ 성공적으로 변환되었습니다! 저장된 파일: {csv_file}")

# 실행 예시
input_json = "rag_performance_benchmark_142.json"
output_csv = "rag_performance_benchmark_142.csv"

json_to_csv_pandas(input_json, output_csv)