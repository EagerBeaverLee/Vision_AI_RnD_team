import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Arrow
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import datetime
import numpy as np

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

st.markdown(
    """
    <style>
    /* 전체 메인 컨테이너의 최대 너비를 1200px로 설정 (원하는 크기로 조절) */
    .stApp .main .block-container {
        max-width: 1200px; 
        padding-left: 2rem;
        padding-right: 2rem;
    }
    /* 또는 더 최신 버전의 클래스명을 사용할 수 있습니다 (브라우저 개발자 도구로 확인 권장) */
    section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"] {
        max-width: 1200px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- 1. 데이터베이스(DataFrame) 초기 설정 ---
# 시나리오 3 (복합 통합 공격 대응) 기반 데이터


def hard_code_image(current_time_offset):
    st.cache_data.clear()
    st.cache_resource.clear()

    images = [
        "image/scene2/0.png",
        "image/scene2/1.png",
        "image/scene2/2.png",
        "image/scene2/3.png",
        "image/scene2/4.png",
        "image/scene2/5.png",
        "image/scene2/6.png",
        "image/scene2/7.png",
        "image/scene2/8.png",
        "image/scene2/9.png",
        "image/scene2/10.png",
        "image/scene2/11.png",
        "image/scene2/12.png",
        "image/scene2/13.png",
        "image/scene2/14.png",
        "image/scene2/15.png",
        "image/scene2/16.png",
        "image/scene2/17.png",
        "image/scene2/18.png",
        "image/scene2/19.png",
    ]
    # 세션 상태 초기화
    if "index" not in st.session_state:
        st.session_state.index = 0

    # 현재 프레임 표시
    st.image(images[st.session_state.index], width='stretch')

    # 슬라이더 값이 바뀌면 인덱스 업데이트
    if (current_time_offset - 5) != st.session_state.index:
        st.session_state.index = current_time_offset - 5
        try:
            with open("time_offset.txt", "a", encoding="utf-8") as f:
                f.write(str(current_time_offset) + "\n")
        except IOError as e:
            print(f"파일 쓰기 오류: {e}")
        st.rerun()  # 화면 즉시 갱신



# 슬라이더 설정
max_time = 24
slider_time = st.slider(
    "시간 진행 (시)",
    min_value=5,
    max_value=max_time,
    value=5,
    step=1,
    format="%d시"
)

hard_code_image(slider_time)

st.divider()
