import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import datetime

# --- 한글 폰트 설정 (이 부분을 추가) ---
import matplotlib.font_manager as fm
# 시스템에 설치된 나눔고딕 폰트 경로를 찾아서 설정
font_path = 'C:/Windows/Fonts/malgun.ttf'  # Windows 기준
# 만약 Linux/macOS 환경이라면 다음 경로를 시도해 보세요.
# font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'  # Linux
# font_path = '/Library/Fonts/AppleGothic.ttf'  # macOS
font_name = fm.FontProperties(fname=font_path, size=10).get_name()
plt.rc('font', family=font_name)
plt.rcParams['axes.unicode_minus'] = False # 마이너스 기호 깨짐 방지
# ----------------------------------------

# --- 1. 데이터베이스(DataFrame) 초기 설정 ---
# 시나리오 3 (복합 통합 공격 대응) 기반 데이터

# 기준 시간 설정 (T0)
BASE_TIME = datetime.datetime(2025, 10, 13, 10, 0, 0)

# 시뮬레이션 이벤트 목록 (시간 순서대로)
events = [
    # T0: 임무 시작
    (0, "SYSTEM", "작전 시작", "주요 항만 방어 임무 개시. 교리: 방어 심층화, 통합."),
    
    # T1: 1분 30초: 공격 개시 (SRBM, CM, UAS) 및 EW 영향
    (90, "THREAT", "복합 통합 공격 개시", "SRBM(고고도), CM(중고도), UAS(저고도) 동시 탐지."),
    (90, "THREAT", "EW 공격 감지", "CM, UAS 위협과 동반. Sentinel 레이더 부분 성능 저하."),
    (90, "DEFENSE", "Patriot", "SRBM에 대한 HIMAD(고고도 방어) 교전 준비 완료."),
    (90, "DEFENSE", "Avenger", "CM, UAS에 대한 SHORAD(최종 방어) 대기."),

    # T2: 2분 45초: Patriot SRBM 교전
    (165, "ENGAGEMENT", "Patriot SRBM 교전", "Patriot, SRBM 요격 성공. (방어 심층화 1단계 성공)"),
    (165, "THREAT", "CM, UAS 위협 유지", "CM이 방어 계층을 통과하여 최종 방어선 접근 중."),
    (165, "DEFENSE", "Patriot", "탄약 2발 소모, 재장전/대기 상태."),

    # T3: 3분 30초: Avenger CM/UAS 교전 시작
    (210, "ENGAGEMENT", "Avenger CM 교전 시작", "Avenger, CM 요격 시작. (SHORAD 임무 인계)"),
    (210, "ENGAGEMENT", "Avenger UAS 교전 시작", "Avenger, 근접 UAS 요격 시작. (복합 공격 대응)"),
    (210, "DEFENSE", "Avenger", "탄약 소모 시작. 상호 지원 및 회복 탄력성 점검 필요."),

    # T4: 4분 30초: UAS 1기 격파, CM 요격 실패 (가정)
    (270, "ENGAGEMENT", "UAS 격파 성공", "Avenger, UAS 1기 격파. CM 요격은 실패. (방책 조정 필요)"),
    (270, "THREAT", "CM 잔존", "CM이 목표에 근접, 피해 발생 위험 증가."),
    
    # T5: 5분 00초: 최종 방책 적용 및 상황 종료
    (300, "SYSTEM", "방책 적용/상황 종료", "교범 검색 기반 방책: 인접 SHORAD 자산의 상호 지원 재배치 완료.")
]

# DataFrame으로 변환
df_events = pd.DataFrame(events, columns=['time_offset', 'category', 'event', 'details'])
df_events['time_stamp'] = df_events['time_offset'].apply(lambda x: (BASE_TIME + datetime.timedelta(seconds=x)).strftime('%H:%M:%S'))

# --- 2. 시각화 함수 ---

def plot_defense_status(current_time_offset):
    """특정 시간까지의 방어 시스템 상태 변화를 시각화"""
    st.subheader("방어 심층화: 시스템 활동 추이")
    
    # 특정 시간까지의 교전 및 방어 이벤트 필터링
    filtered_events = df_events[df_events['time_offset'] <= current_time_offset]
    
    # Patriot 및 Avenger의 주요 이벤트 시간점 추출
    patriot_times = filtered_events[filtered_events['event'].str.contains("Patriot")].copy()
    avenger_times = filtered_events[filtered_events['event'].str.contains("Avenger")].copy()
    
    fig, ax = plt.subplots(figsize=(10, 4))
    
    # Patriot 활동 시각화
    ax.scatter(patriot_times['time_stamp'], [1] * len(patriot_times), 
               label='Patriot (HIMAD)', marker='s', color='blue', s=100)
    
    # Avenger 활동 시각화
    ax.scatter(avenger_times['time_stamp'], [0] * len(avenger_times), 
               label='Avenger (SHORAD)', marker='o', color='red', s=100)

    # 이벤트 텍스트 추가
    for index, row in filtered_events.iterrows():
        y_pos = 1 if 'Patriot' in row['event'] else 0
        if row['category'] == 'ENGAGEMENT':
            ax.annotate(row['event'].split(' ')[-1], (row['time_stamp'], y_pos), 
                        textcoords="offset points", xytext=(0,10), ha='center', fontsize=8, color='black')

    ax.set_yticks([0, 1])
    ax.set_yticklabels(['SHORAD (Avenger)', 'HIMAD (Patriot)'])
    ax.set_title(f"시간대별 방어 체계 교전 활동 ({df_events['time_stamp'].iloc[0]} 기준)")
    ax.set_xlabel("시간 (HH:MM:SS)")
    ax.grid(axis='x', linestyle='--')
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig)


# --- 3. Streamlit UI 및 시뮬레이션 로직 ---

st.title("🛡️ SHORAD 작전 시뮬레이터 (시나리오 3)")
st.caption(f"기준 시간: {BASE_TIME.strftime('%Y-%m-%d %H:%M:%S')} | 시나리오: 복합 통합 공격 대응")

# 슬라이더 설정
max_time = df_events['time_offset'].max()
slider_time = st.slider(
    "시간 진행 (초)",
    min_value=0,
    max_value=max_time,
    value=0,
    step=30,
    format="%d초"
)

# 현재 시각 계산
current_time = BASE_TIME + datetime.timedelta(seconds=slider_time)
st.markdown(f"## ⏱️ 현재 시각: **{current_time.strftime('%H:%M:%S')}**")

# --- A. 시각화 플롯 표시 ---
plot_defense_status(slider_time)

st.divider()

# --- B. 실시간 로그 표시 ---
st.subheader("작전 상황 로그")

current_events = df_events[df_events['time_offset'] <= slider_time]

if current_events.empty:
    st.info("아직 이벤트가 발생하지 않았습니다. 시간을 진행해 주세요.")
else:
    # 가장 최근 이벤트를 중심으로 보여주기 위해 역순 정렬
    current_events_sorted = current_events.sort_values(by='time_offset', ascending=False)
    
    # 로그를 테이블로 표시
    st.dataframe(
        current_events_sorted[['time_stamp', 'category', 'event', 'details']],
        hide_index=True,
        column_config={
            "time_stamp": st.column_config.DatetimeColumn("시간", format="HH:mm:ss", width="small"),
            "category": "분류",
            "event": "주요 이벤트",
            "details": "상세 설명 및 교리 적용"
        }
    )

# --- C. 교범/방책 검색 Context 예시 ---
st.divider()
st.subheader("💡 RAG(방책 검색) 필요 시점 분석 (10:03:30)")

if slider_time >= 270:
    st.success("🚨 **CM 요격 실패! 긴급 방책 검색 필요.**")
    st.write("Avenger의 CM 요격 실패로 목표 자산에 대한 위험도가 증가했습니다. 교범 기반의 즉각적인 방책 도출이 필요합니다.")
    
    st.markdown("""
    **✅ RAG 검색 Context Keywords (DB 기반 추출):**
    - `CM 최종 방어 실패`
    - `UAS 근접 침투`
    - `센서 저하`
    - `SHORAD 상호 지원 재배치`
    """)

    st.info("**(LLM/RAG의 방책 생성 예시):** '교범의 [회복 탄력성] 교리에 따라, EW 공격의 영향을 받지 않은 인접 Avenger 포대 2의 사격 구역을 항만 핵심 시설로 긴급 재할당(상호 지원)하고, Sentinel의 수동 보고 체계를 활성화합니다.'")
elif slider_time >= 90:
     st.warning("⚠️ **복합 공격 및 EW 공격 감지.**")
     st.write("Patriot가 고고도 위협에 집중하는 동안, 저고도 위협(CM, UAS)에 대한 SHORAD의 방어 임무 준비가 중요합니다. 교범의 **방어 심층화**가 작동 중입니다.")
else:
    st.info("작전 초기 단계입니다. 모든 시스템이 정상 대기 상태입니다.")