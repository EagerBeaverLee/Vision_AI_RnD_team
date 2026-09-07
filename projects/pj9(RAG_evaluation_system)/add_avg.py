import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import platform

# 1. 데이터프레임 로드
df = pd.read_csv("rag_performance_benchmark_142.csv")

def save_boxplot_img():
    save_path = "adaptive_rag_boxplot.png"

    # 2. '점수'라는 단어가 포함된 모든 컬럼 이름을 자동으로 추출
    score_columns = [col for col in df.columns if '점수' in col]

    # 3. 한글 폰트 및 마이너스 기호 깨짐 방지 설정
    if platform.system() == 'Windows':
        plt.rc('font', family='Malgun Gothic')
    elif platform.system() == 'Darwin':
        plt.rc('font', family='AppleGothic')
    else:
        plt.rc('font', family='NanumGothic')
    plt.rcParams['axes.unicode_minus'] = False 

    # 4. 그래프 사이즈 설정 (컬럼 개수가 많을수록 가로 길이를 늘려주면 좋습니다)
    plt.figure(figsize=(10, 6))

    # 5. Seaborn을 이용한 Boxplot 시각화
    # 추출한 score_columns만 data로 넘겨줍니다.
    sns.boxplot(
        data=df[score_columns], 
        palette="Set3",   # 파스텔 톤의 부드러운 색상 테마
        width=0.5         # 박스 두께
    )

    # 6. 그래프 꾸미기
    plt.title("다중 RAG 파이프라인 평가 점수 분포", fontsize=16, pad=15)
    plt.ylabel("점수 (Score)", fontsize=12)

    # 이름이 길어서 겹치는 것을 방지하기 위해 x축 라벨 45도 회전
    plt.xticks(rotation=45, ha='right') 

    plt.grid(axis='y', linestyle='--', alpha=0.7) # y축 가이드라인 추가

    # 7. 고화질 PNG 파일로 저장
    # bbox_inches='tight': 45도 기울인 글자가 이미지 밖으로 잘리지 않도록 여백을 자동 조정해줍니다.
    
    plt.savefig(save_path, dpi=300, bbox_inches='tight')

    # 메모리 누수 방지를 위해 figure 닫기 (여러 번 반복 실행할 때 필수)
    plt.close()

    print(f"✨ 여러 모델의 평가 결과가 담긴 Boxplot이 '{save_path}'에 성공적으로 저장되었습니다!")


def add_avg():
    # 2. '점수'라는 단어가 포함된 모든 컬럼 이름을 자동으로 추출
    score_columns = [col for col in df.columns if '점수' in col]

    # 3. 평균과 표준편차를 담을 딕셔너리 준비 (비고란 포함)
    mean_data = {"비고": "평균 (Mean)"}
    std_data = {"비고": "표준편차 (Std)"}

    # 4. 추출한 점수 컬럼들을 순회하며 계산
    for col in score_columns:
        mean_data[col] = df[col].mean()
        std_data[col] = df[col].std()

    # 5. 계산된 통계를 데이터프레임으로 변환 후 기존 df에 이어붙이기
    summary_rows = pd.DataFrame([mean_data, std_data])
    df_final = pd.concat([df, summary_rows], ignore_index=True)

    # 6. 보기 좋게 정리 ('비고' 컬럼의 빈칸 처리 및 맨 앞으로 이동)
    df_final["비고"] = df_final["비고"].fillna("")
    cols = ["비고"] + [c for c in df_final.columns if c != "비고"]
    df_final = df_final[cols]

    # 7. 결과 확인 및 CSV 저장
    print("📊 [자동 계산된 통계 결과]")
    print(summary_rows)

    csv_save_path = "adaptive_benchmark_report.csv"
    df_final.to_csv(csv_save_path, index=False, encoding='utf-8-sig')

    print(f"\n✨ 통계가 포함된 파일이 '{csv_save_path}'에 저장되었습니다!")

add_avg()
save_boxplot_img()