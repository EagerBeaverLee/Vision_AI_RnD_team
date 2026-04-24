#folium import
import folium
from streamlit_folium import st_folium

from windrose import WindroseAxes
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Polygon, Circle

import plotly.express as px
import plotly.graph_objects as go

import altair as alt

import numpy as np
import streamlit as st
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import pydeck as pdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
from streamlit.runtime import Runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx
import streamlit.components.v1 as components

class WeatherChartProcessor:
    """무거운 시각화 작업을 처리하는 프로세서"""
    def __init__(self):
        # 최대 4개의 차트를 병렬로 생성하기 위한 스레드 풀
        self.executor = ThreadPoolExecutor(max_workers=4)

    def generate_all_charts(self, s):
        """클릭된 station 데이터를 바탕으로 모든 차트를 비동기적으로 생성"""
        # 1. 풍향/풍속
        ws = [float(s.get('풍속(m/s)', 0))]
        wd = [float(s.get('풍향(deg)', 0))]
        future_wind = self.executor.submit(render_wind_chart, wd, ws, 2, 2)

        # 2. 습도
        hum_val = float(s.get('습도(%)', 0))
        future_hum = self.executor.submit(render_humidity_gauge, hum_val, 158)

        # 3. 기압
        hpa_val = float(s.get('현지기압(hPa)', 0))
        future_hpa = self.executor.submit(render_custom_gauge, hpa_val, 2, 2)

        # 4. 파향
        wvd = [float(s.get('파향(deg)', 0))]
        future_wave = self.executor.submit(render_wave_chart, wvd, 2, 2)
        
        # 5. 파고 (이것도 무겁다면 포함)
        max_wh = float(s.get('최대파고(m)', 0))
        high_max_wh = float(s.get('유의파고(m)', 0))
        avg_wh = float(s.get('평균파고(m)', 0))
        future_wh = self.executor.submit(render_wave_height, max_wh, high_max_wh, avg_wh, 4, 1.6)

        return {
            "wind": future_wind.result(),
            "humidity": future_hum.result(),
            "pressure": future_hpa.result(),
            "wave_dir": future_wave.result(),
            "wave_height": future_wh.result()
        }

st.markdown("""
    <style>
    /* 4. 카드 제목 스타일 */
    .card-dashboard {
        height: 30px;
        min-height: 30px !important;
        max-height: 30px !important;
        color: #B8F7B9;
        font-size: 1.1rem;
        font-weight: bold;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        gap: 8px;
        
        overflow: hidden;
    }
    .bar-dashboard {
        height: 30px;
        min-height: 30px !important;
        max-height: 30px !important;
        color: #B8F7B9;
        font-size: 1.1rem;
        font-weight: bold;
        margin-bottom: 0px;
        display: flex;
        align-items: top;
        gap: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# 싱글톤으로 인스턴스 생성
if 'processor' not in st.session_state:
    st.session_state.processor = WeatherChartProcessor()

# 1. 전역 데이터 저장소
@st.cache_resource
def get_global_store():
    return {"df": pd.DataFrame()}

# 데이터 저장소
data_store = get_global_store()

# 2. --- FastAPI 설정 ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/update")
async def update_api(request: Request):
    payload = await request.json()
    data_store["df"] = pd.DataFrame(payload)
    
    try:
        runtime = Runtime.instance()
        for session_info in runtime._session_mgr.list_sessions():
            # 세션에 인자 없이 호출하여 전체 창 새로고침 신호 전송 (프래그먼트 대응)
            session_info.session.request_rerun(None)
        return {"status": "success"}
    except:
        return {"status": "error"}

# API 서버 실행
if 'api_running' not in st.session_state:
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8600, log_level="error"), daemon=True).start()
    st.session_state.api_running = True
# ======================================================================

# --- 3. UI 레이아웃 ---
st.set_page_config(layout="wide", page_title="실시간 해양 관측망")

# 메인 타이틀은 프래그먼트 밖에 두어 고정
# st.title("📡 실시간 해양 기상 관측 시스템")

# --- 4. 통합 프래그먼트 (지도 + 대시보드) ---
@st.fragment

# --- 풍배도(Wind Rose) 렌더링 함수 ---
def render_wind_chart(direction_val, speed_val, x, y):
    #y축 최댓값
    max_scale=25

    # 1. 그래프 생성 (극좌표계 사용)
    fig, ax = plt.subplots(figsize=(x, y), subplot_kw={'projection': 'polar'})
    fig.patch.set_facecolor('none')
    fig.patch.set_alpha(0) # 배경 투명
    ax.set_aspect('auto')
    
    # 2. 방향 설정 (0도=북쪽, 시계방향 진행)
    ax.set_theta_zero_location("N")  # 북쪽이 0도
    ax.set_theta_direction(-1)       # 시계방향으로 각도 증가
    
    # 3. 데이터 변환 (각도를 라디안으로)
    theta = np.deg2rad(direction_val)
    
    # 4. 막대 그리기
    # width=np.deg2rad(20)은 막대의 좌우 너비(두께)입니다.
    ax.bar(theta, speed_val, 
           width=np.deg2rad(20), 
           bottom=0.0, 
           color='#B8F7B9', 
           edgecolor='#B8F7B9')

    # 5. y축(반지름) 범위 및 눈금 고정 (0~23)
    ax.set_ylim(0, max_scale)
    ticks = np.arange(0, max_scale + 1, 5) # 0, 5, 10, 15, 20
    ax.set_rticks(ticks)
    ax.set_yticklabels([f"{t}" for t in ticks], color='#B8F7B9', size=7)

    # 6. 배경색 및 라벨 디자인
    ax.set_facecolor('#282828') # 원형 내부 배경색

    # 3. [해결 방법] 눈금 위치(Ticks)를 먼저 고정합니다.
    # 8방위이므로 0도부터 315도까지 45도 간격으로 설정 (라디안 변환 필요)
    angles = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    ax.set_xticks(angles)
    
    # 방향 라벨 (N, NE, E ...) 설정
    ax.set_xticklabels(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'], 
                       color='#B8F7B9', size=12, fontweight='bold')
    
    # 3. 화살표 끝에 텍스트 추가
    ax.text(theta, float(speed_val[0]) + 6, f"{direction_val[0]}°", 
            color='#B8F7B9', fontweight='bold', ha='center', va='center', size=12)
    # ------------------------------

    # 디자인 디테일 (사진과 유사하게)
    ax.grid(True, linestyle=':', alpha=0.6)

    return fig

def render_wave_chart(direction, x, y):
    speed = [1]
    fig= plt.figure(figsize=(x, y), dpi=100)
    # 배경색을 스트림릿 테마와 맞추기 (투명 또는 하늘색)
    fig.patch.set_alpha(0) 
    
    ax = WindroseAxes.from_ax(fig=fig)
    
    ax.set_aspect('auto')

    # 데이터가 1개뿐일 경우를 대비해 처리
    # 실제 운영 시에는 해당 지점의 최근 24시간 데이터를 넘겨주는 것이 좋습니다.
    ax.bar(direction, speed, normed=True, opening=0.8, color='#B8F7B9', edgecolor='#B8F7B9')

    # 방향 라벨 (N, NE, E ...) 설정
    ax.set_xticklabels(['E', 'NE', 'N', 'NW', 'W', 'SW', 'S', 'SE'], 
                       color='#B8F7B9', size=12, fontweight='bold')
    
    ax.tick_params(axis='y', colors='#B8F7B9', labelsize=7)
        
    ax.set_facecolor('#282828') # 원형 내부 배경색
    
    # 디자인 디테일 (사진과 유사하게)
    ax.grid(True, linestyle=':', alpha=0.6)
    
    return fig

def render_humidity_gauge(humidity, y):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = humidity,
        domain = {'x': [0, 1,], 'y': [0, 1]},
        # title = {'text': "현재 습도 (%)", 'font': {'size': 12}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#B8F7B9"},
            'bar': {'color': "#B8F7B9"},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 30], 'color': "#b4bec0"}, # 건조
                {'range': [30, 70], 'color': "#7a858b"}, # 적정
                {'range': [70, 100], 'color': "#555e5f"} # 습함
            ],
            'threshold': {
                'line': {'color': "black", 'width': 4},
                'thickness': 0.75,
                'value': humidity
            }
        }
    ))
    
    # 차트 크기 및 여백 조정
    fig.update_layout(
        height=y,
        margin=dict(l=30, r=30, t=30, b=20),
        paper_bgcolor='rgba(255,255,255,0)', # 투명 배경
        plot_bgcolor='rgba(0,0,0,0)',  # 내부 배경 투명
        font={'color': "#B8F7B9", 'family': "Arial"}
    )
    return fig

def render_custom_gauge(value, x, y, min_value=950, max_value=1070):
    # --- 1. 값 제한 (범위를 벗어날 경우 고정) ---
    display_val = max(min_value, min(max_value, value))

    # --- 2. 설정값 및 각도 계산 ---
    start_angle = 225  # 왼쪽 아래 (시작)
    end_angle = -45    # 오른쪽 아래 (끝)
    total_span = start_angle - end_angle # 270도
    
    # [핵심 변경] 전체 범위 대비 현재 값의 비율 계산
    # (현재값 - 최소값) / (최대값 - 최소값)
    ratio = (display_val - min_value) / (max_value - min_value)

    # 현재 값에 따른 각도 계산
    current_angle = start_angle - (ratio * total_span)
    angle_rad = np.deg2rad(current_angle)
    
    # 2. 그래프 생성
    fig, ax = plt.subplots(figsize=(x, y))
    fig.patch.set_alpha(0) # 배경 투명
    ax.set_aspect('auto')
    
    # 3. 배경 아크 (연한 회색)
    bg_wedge = Wedge((0, 0), 0.4, end_angle, start_angle, width=0.1, 
                     facecolor='#282828', edgecolor='none', zorder=1)
    ax.add_patch(bg_wedge)
    
    # 4. 진행 상태 아크 (진한 파란색)
    # 현재 값만큼만 색을 채움
    progress_wedge = Wedge((0, 0), 0.4, current_angle, start_angle, width=0.1, 
                           facecolor='#B8F7B9', edgecolor='none', zorder=2)
    ax.add_patch(progress_wedge)
    
    # --- 5. 바늘(Needle) 그리기 ---
    #바늘길이
    needle_length = 0.3

    #바늘두께
    needle_base_width = 0.02
    tip = (needle_length * np.cos(angle_rad), needle_length * np.sin(angle_rad))
    perp_rad = angle_rad + np.pi/2
    base_1 = (needle_base_width * np.cos(perp_rad), needle_base_width * np.sin(perp_rad))
    base_2 = (-needle_base_width * np.cos(perp_rad), -needle_base_width * np.sin(perp_rad))
    
    ax.add_patch(Polygon([base_1, tip, base_2], facecolor='#B8F7B9', zorder=4))
    ax.add_patch(Circle((0,0), 0.015, color='#B8F7B9', zorder=5))
    
    # 6. 텍스트 배치 (0, 3, 퍼센트)
    # 0 라벨
    ax.text(0.35 * np.cos(np.deg2rad(start_angle)), 0.35 * np.sin(np.deg2rad(start_angle)) - 0.12, 
            str("low"), ha='center', va='top', fontsize=12, color='#B8F7B9')
    # max 라벨 (3)
    ax.text(0.35 * np.cos(np.deg2rad(end_angle)), 0.35 * np.sin(np.deg2rad(end_angle)) - 0.12, 
            str("high"), ha='center', va='top', fontsize=12, color='#B8F7B9')
    # ax.text(0.35 * np.cos(np.deg2rad(end_angle)), 0.35 * np.sin(np.deg2rad(end_angle)) - 0.1, 
    #         str(max_value), ha='center', va='top', fontsize=10, color='#B8F7B9')
    
    # 값 표시
    ax.text(0, -0.28, f'{value:.1f}hPa', ha='center', va='center', 
            fontsize=10, fontweight='bold', color='#B8F7B9')

    # 7. 축 숨기기 및 범위 설정
    ax.set_xlim(-0.5, 0.5)
    ax.set_ylim(-0.5, 0.5)
    ax.axis('off')
    
    return fig

def render_wave_height(max_height, high_avg_height, avg_height, x, y):
    fig, ax = plt.subplots(figsize=(x, y))
    fig.patch.set_alpha(0) # 배경 투명
    ax.set_aspect('auto')

    names = ['max', 'high', 'avg']
    counts = [max_height, high_avg_height, avg_height]
    bar_labels = ['max', 'high', 'avg']
    bar_colors = ["#E8A2A2",'#F4CF8D','#8FDDE7']

    ax.tick_params(axis='x', colors='#B8F7B9', labelsize=7)
    ax.tick_params(axis='y', colors='#B8F7B9', labelsize=7)
        
    ax.set_facecolor('#282828') # 배경색

    # ax.set_ylim(0, 5)

    ax.bar(names, counts, label=bar_labels, color=bar_colors, width=0.3, linewidth=1)

    #테두리를 테마색으로 적용
    for spine in ax.spines.values():
        spine.set_color('#B8F7B9')
        spine.set_linewidth(0.7)

    return fig


@st.fragment
def render_folium_map():
    df = data_store["df"] # 전역 저장소에서 데이터 호출

    # --- 1. 세션 상태 초기화 (최상단) ---
    if 'map_center' not in st.session_state:
        st.session_state['map_center'] = [34.6, 127.7]
    if 'map_zoom' not in st.session_state:
        st.session_state['map_zoom'] = 7
    if 'selected_station' not in st.session_state:
        st.session_state['selected_station'] = None
    if 'last_clicked_pos' not in st.session_state:
        st.session_state['last_clicked_pos'] = None
    
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        if not df.empty:
            map_key = "weather_map_v1"

            if map_key in st.session_state and st.session_state[map_key]:
                # 아직 업데이트 로직이 실행 전이라도, 세션에 담긴 최신 브라우저 좌표를 강제로 뺏어옴
                last_ui_state = st.session_state[map_key]
                st.session_state['map_center'] = [last_ui_state["center"]["lat"], last_ui_state["center"]["lng"]]
                st.session_state['map_zoom'] = last_ui_state["zoom"]

            # 저장된 값으로 지도 객체 생성
            m = folium.Map(
                location=st.session_state['map_center'], 
                zoom_start=st.session_state['map_zoom'], 
                tiles='openstreetmap'
            )

            # 대시보드 위치 울산으로 초기화
            if not st.session_state.get("selected_station"):
                st.session_state.selected_station = df.loc[14].to_dict()

            # --- 3. 마커 추가 로직 ---
            for _, row in df.iterrows():
                # 사진과 유사한 스타일의 HTML/CSS 정의
                icon_html = f"""
                <div style="font-size: 9pt; font-weight: bold; color: black; text-shadow: 1px 1px white, -1px -1px white, -1px 1px white, 1px -1px white; text-align: center; margin-bottom: 1px;">{row['지점명']}</div>
                <div style="
                    background-color: white;
                    border: 1px solid #999;
                    border-radius: 4px;
                    padding: 4px;
                    width: 50px;
                    text-align: center;
                    box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
                    font-family: 'Malgun Gothic', sans-serif;
                    line-height: 1.1;
                ">
                    <div style="font-size: 9pt; color: #ff0000;">{row['기온(°C)']}°C</div>
                    <div style="font-size: 9pt; color: #000fff;">{row['습도(%)']}%</div>
                </div>
                """
                
                # 마커 추가
                folium.Marker(
                    location=[row['latitude'], row['longitude']],
                    icon=folium.DivIcon(
                        html=icon_html,
                        icon_size=(50, 45),
                        icon_anchor=(35, 22)
                    ),
                    # 클릭 시 데이터 전달을 위해 지점명 저장
                    # tooltip=row['지점명']
                ).add_to(m)

                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=15, 
                    color="transparent",
                    fill=True,
                    fill_color="transparent",
                    fill_opacity=0,
                    tooltip=row['지점명'], # 여전히 툴팁은 넣어둡니다.
                    popup=row['지점명']
                ).add_to(m)

            # 3. 지도 표시 및 사용자 조작 감지
            map_data = st_folium(
                m,
                width='100%',
                height=600,
                key="weather_map_v1",
                use_container_width='True',
                returned_objects=["last_object_clicked", "center", "zoom"]
            )

            # --- 5. 지도 조작(이동/확대) 감지 및 세션 업데이트 ---
            if map_data and map_data.get("center"):
                new_lat = map_data["center"]["lat"]
                new_lng = map_data["center"]["lng"]
                new_zoom = map_data["zoom"]
                
                old_lat, old_lng = st.session_state['map_center']
                
                # [핵심] 미세한 좌표 변화는 무시하여 튕김 현상 방지 (소수점 4자리)
                if abs(old_lat - new_lat) > 0.0001 or abs(old_lng - new_lng) > 0.0001 or st.session_state['map_zoom'] != new_zoom:
                    st.session_state['map_center'] = [new_lat, new_lng]
                    st.session_state['map_zoom'] = new_zoom
                    
                    #추가
                    # st.rerun()
                    # 이동 시에는 st.rerun()을 호출하지 않아야 부드럽게 움직입니다.

            
            # --- 6. 클릭 로직 (지점 선택) ---
            new_clicked_pos = map_data.get("last_object_clicked")
            
            # 새로운 클릭이 발생했는지 확인
            if new_clicked_pos and new_clicked_pos != st.session_state['last_clicked_pos']:
                st.session_state['last_clicked_pos'] = new_clicked_pos
                
                # 가장 가까운 지점 찾기
                df['dist'] = np.sqrt((df['latitude'] - new_clicked_pos['lat'])**2 + 
                                    (df['longitude'] - new_clicked_pos['lng'])**2)
                
                closest_idx = df['dist'].idxmin()
                print(closest_idx)
                if df.loc[closest_idx, 'dist'] < 0.1: # 유효 거리 내 클릭일 때만
                    new_station = df.loc[closest_idx].to_dict()
                    
                    # 현재 선택된 지점과 다를 때만 갱신 및 Rerun
                    current_station = st.session_state.get("selected_station")
                    if not current_station or current_station['지점명'] != new_station['지점명']:
                        st.session_state.selected_station = new_station
                        st.rerun() # 클릭 시에는 대시보드 갱신을 위해 rerun 필요
        else:
            st.info("데이터 수신 대기 중...")
    with col2:
        station = st.session_state.get('selected_station')
        
        if station:
            s = st.session_state.selected_station

            st.markdown(f"#### {s['지점명']}")
            sub_col1, sub_col2= st.columns(2)

            with sub_col1:

                with st.container(border=True):
                    st.markdown('<div class="card-dashboard">🧭 풍향/풍속</div>', unsafe_allow_html=True)

                    # 풍속/풍향 데이터를 리스트 형태로 전달
                    # (현재 1개 데이터만 있다면 [값] 형태로 전달)
                    ws = [float(s.get('풍속(m/s)', 0))]
                    wd = [float(s.get('풍향(deg)', 0))]
                    
                    if ws and wd:
                        fig = render_wind_chart(wd, ws, 2, 2)
                        st.pyplot(fig, width='stretch')

                with st.container(border=True):
                    # 습도 게이지 카드 시작
                    st.markdown('<div class="card-dashboard">💧 현재 습도</div>', unsafe_allow_html=True)

                    # 3. [신규] 습도 대시보드 (Gauge Chart)
                    hum_val = float(station.get('습도(%)', 0))
                    fig_hum = render_humidity_gauge(hum_val, 158)
                    st.plotly_chart(fig_hum, height='stretch', width='stretch')
                    # st.pyplot(fig_hum, width='stretch')

            with sub_col2:
                with st.container(border=True):
                    st.markdown('<div class="card-dashboard">☁️ 기압</div>', unsafe_allow_html=True)

                    hpa_val = float(station.get('현지기압(hPa)', 0))
                    fig_hpa = render_custom_gauge(hpa_val, 2, 2)
                    st.pyplot(fig_hpa, width='stretch')

                with st.container(border=True):
                    st.markdown('<div class="card-dashboard">🌊 파향</div>', unsafe_allow_html=True)

                    # 풍속/풍향 데이터를 리스트 형태로 전달
                    # (현재 1개 데이터만 있다면 [값] 형태로 전달)
                    wvd = [float(s.get('파향(deg)', 0))]
                    
                    if wvd:
                        fig = render_wave_chart(wvd, 2, 2)
                        st.pyplot(fig, width='stretch')

            with st.container(border=True):
                st.markdown('<div class="bar-dashboard">⛵ 파고</div>', unsafe_allow_html=True)

                max_wh = float(station.get('최대파고(m)', 0))
                high_max_wh = float(station.get('유의파고(m)', 0))
                avg_wh = float(station.get('평균파고(m)', 0))

                fig_wh = render_wave_height(max_wh, high_max_wh, avg_wh, 4, 1.6)
                st.pyplot(fig_wh, width='stretch')

        else:
            st.info("지도에서 마커를 클릭하면 상세 데이터가 표시됩니다.")

# def render_folium_map():
#     df = data_store["df"]

#     # --- 1. 세션 상태 초기화 ---
#     for key, default in {
#         'map_center': [34.6, 127.7],
#         'map_zoom': 7,
#         'selected_station': None,
#         'last_clicked_pos': None,
#         'chart_cache': None # 생성된 차트 객체 저장용
#     }.items():
#         if key not in st.session_state:
#             st.session_state[key] = default

#     col1, col2 = st.columns([1.5, 1])

#     with col1:
#         if not df.empty:
#             map_key = "weather_map_v1"
            
#             # 브라우저의 현재 지도 상태 유지
#             if map_key in st.session_state and st.session_state[map_key]:
#                 last_ui_state = st.session_state[map_key]
#                 st.session_state['map_center'] = [last_ui_state["center"]["lat"], last_ui_state["center"]["lng"]]
#                 st.session_state['map_zoom'] = last_ui_state["zoom"]

#             m = folium.Map(
#                 location=st.session_state['map_center'],
#                 zoom_start=st.session_state['map_zoom'],
#                 tiles='openstreetmap'
#             )

#             # 초기값 설정 (울산)
#             if st.session_state.selected_station is None:
#                 st.session_state.selected_station = df.loc[14].to_dict()
#                 # 초기 차트 생성
#                 st.session_state.chart_cache = st.session_state.processor.generate_all_charts(st.session_state.selected_station)

#             # 마커 그리기 (생략: 기존 코드와 동일하게 icon_html 적용)
#             for _, row in df.iterrows():
#                 # 사진과 유사한 스타일의 HTML/CSS 정의
#                 icon_html = f"""
#                 <div style="font-size: 9pt; font-weight: bold; color: black; text-shadow: 1px 1px white, -1px -1px white, -1px 1px white, 1px -1px white; text-align: center; margin-bottom: 1px;">{row['지점명']}</div>
#                 <div style="
#                     background-color: white;
#                     border: 1px solid #999;
#                     border-radius: 4px;
#                     padding: 4px;
#                     width: 50px;
#                     text-align: center;
#                     box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
#                     font-family: 'Malgun Gothic', sans-serif;
#                     line-height: 1.1;
#                 ">
#                     <div style="font-size: 9pt; color: #ff0000;">{row['기온(°C)']}°C</div>
#                     <div style="font-size: 9pt; color: #000fff;">{row['습도(%)']}%</div>
#                 </div>
#                 """
#                 folium.Marker(
#                     location=[row['latitude'], row['longitude']],
#                     icon=folium.DivIcon(html=icon_html, icon_size=(50, 45), icon_anchor=(35, 22))
#                 ).add_to(m)
                
#                 # 투명 클릭 레이어
#                 folium.CircleMarker(
#                     location=[row['latitude'], row['longitude']],
#                     radius=15, color="transparent", fill=True, popup=row['지점명']
#                 ).add_to(m)

#             # 지도 렌더링
#             map_data = st_folium(
#                 m, width='100%', height=600, key=map_key,
#                 returned_objects=["last_object_clicked", "center", "zoom"]
#             )

#             # --- 지도 조작 업데이트 (rerun 방지) ---
#             if map_data and map_data.get("center"):
#                 st.session_state['map_center'] = [map_data["center"]["lat"], map_data["center"]["lng"]]
#                 st.session_state['map_zoom'] = map_data["zoom"]

#             # --- 클릭 감지 및 차트 업데이트 ---
#             new_clicked_pos = map_data.get("last_object_clicked")
#             if new_clicked_pos and new_clicked_pos != st.session_state['last_clicked_pos']:
#                 st.session_state['last_clicked_pos'] = new_clicked_pos
                
#                 # 거리 계산
#                 df['dist'] = np.sqrt((df['latitude'] - new_clicked_pos['lat'])**2 + (df['longitude'] - new_clicked_pos['lng'])**2)
#                 closest_idx = df['dist'].idxmin()

#                 if df.loc[closest_idx, 'dist'] < 0.1:
#                     new_station = df.loc[closest_idx].to_dict()
#                     if st.session_state.selected_station['지점명'] != new_station['지점명']:
#                         st.session_state.selected_station = new_station
#                         # [핵심] 클릭 시 백그라운드 프로세서 호출하여 차트 미리 생성
#                         st.session_state.chart_cache = st.session_state.processor.generate_all_charts(new_station)
#                         st.rerun()

#     with col2:
#         station = st.session_state.selected_station
#         charts = st.session_state.chart_cache
        
#         if station and charts:
#             st.markdown(f"#### {station['지점명']}")
            
#             sub_col1, sub_col2 = st.columns(2)
#             with sub_col1:
#                 with st.container(border=True):
#                     st.markdown('<div class="card-dashboard">🧭 풍향/풍속</div>', unsafe_allow_html=True)
#                     st.pyplot(charts['wind'])

#                 with st.container(border=True):
#                     st.markdown('<div class="card-dashboard">💧 현재 습도</div>', unsafe_allow_html=True)
#                     # Plotly 객체인 경우 처리
#                     st.plotly_chart(charts['humidity'], use_container_width=True)

#             with sub_col2:
#                 with st.container(border=True):
#                     st.markdown('<div class="card-dashboard">☁️ 기압</div>', unsafe_allow_html=True)
#                     st.pyplot(charts['pressure'])

#                 with st.container(border=True):
#                     st.markdown('<div class="card-dashboard">🌊 파향</div>', unsafe_allow_html=True)
#                     st.pyplot(charts['wave_dir'])
            
#             with st.container(border=True):
#                 st.markdown('<div class="bar-dashboard">⛵ 파고</div>', unsafe_allow_html=True)
#                 st.pyplot(charts['wave_height'])
#         else:
#             st.info("지도에서 마커를 클릭하면 상세 데이터가 표시됩니다.")

@st.fragment
def render_plotly_map():
    df = data_store["df"]
    
    if not df.empty:
        # 1. 데이터 전처리 (에러 방지를 위해 문자열로 확실히 변환)
        df['temp'] = df['temp'].fillna(0).astype(float).round(1)
        df['hum'] = df['hum'].fillna(0).astype(int)
        
        # 지도 위에 상시 노출될 텍스트 (지점명 + 온도)
        # HTML 태그를 사용해 가독성을 높입니다.
        df['map_label'] = df.apply(lambda x: f"<b>{x['지점명']}</b><br>{x['temp']}°C", axis=1)

        fig = go.Figure()

        # 2. [레이어 1] 배경 점 (Marker)
        fig.add_trace(go.Scattermapbox(
            lat=df["latitude"],
            lon=df["longitude"],
            mode='markers',
            marker=dict(size=14, color='rgb(255, 50, 50)', opacity=0.7),
            hoverinfo='none' # 점 자체에는 툴팁 안 뜨게 설정
        ))

        # 3. [레이어 2] 강제 텍스트 (Text) - 이 부분이 핵심입니다!
        fig.add_trace(go.Scattermapbox(
            lat=df["latitude"],
            lon=df["longitude"],
            mode='text', # 오직 텍스트만!
            text=df['map_label'],
            
            # [중요] Plotly가 글자를 숨기지 못하게 강제하는 설정
            texttemplate="%{text}", 
            
            textposition="top center",
            textfont=dict(
                family="Arial Black, Malgun Gothic, sans-serif",
                size=16, # 글자를 아주 크게 설정 (16~20)
                color="black"
            ),
            # 마우스를 올렸을 때만 나오는 상세 정보 (툴팁)
            hoverinfo="text",
            hovertext=df.apply(lambda x: f"<b>📍 {x['지점명']}</b><br>온도: {x['temp']}°C<br>습도: {x['hum']}%", axis=1),
            customdata=df.to_dict('records')
        ))

        # 4. 지도 레이아웃 설정
        fig.update_layout(
            # 'carto-positron' 대신 'open-street-map'이 라벨 표시가 더 잘 될 때가 있습니다.
            mapbox=dict(
                style="open-street-map", 
                center=go.layout.mapbox.Center(lat=34.6, lon=127.7),
                zoom=7 # 줌 레벨을 조금 높여서 시작
            ),
            margin={"r":0,"t":0,"l":0,"b":0},
            height=700,
            showlegend=False,
            # [실시간 갱신 핵심] uirevision을 고정하면 데이터가 바뀌어도 지도가 튀지 않음
            uirevision='constant' 
        )

        # 5. 출력 및 클릭 이벤트 연동
        # config 설정을 통해 Plotly 툴바를 숨기거나 조정할 수 있습니다.
        selected = st.plotly_chart(
            fig, 
            use_container_width=True, 
            on_select="rerun", 
            key="plotly_final_fix",
            config={'displayModeBar': False} 
        )
        
        # 지점 클릭 시 상세정보 업데이트
        if selected and "selection" in selected and selected["selection"]["points"]:
            # 클릭된 객체가 텍스트 레이어(Trace 1)일 경우에만 데이터 추출
            points = selected["selection"]["points"]
            if points[0].get("customdata"):
                st.session_state.selected_station = points[0]["customdata"]
                st.rerun()

    # with col2:
        # render_details()


# 프래그먼트 실행
render_folium_map()
# render_plotly_map()
# new_folium_map()