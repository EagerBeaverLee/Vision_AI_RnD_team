import streamlit as st
import pandas as pd
import pydeck as pdk
import time
import os
import json

# 1. 페이지 설정
st.set_page_config(page_title="Naval Wargame Simulator", layout="wide")

# 2. 데이터 로드 및 전처리
@st.cache_data
def load_full_data():
    file_path = 'Sample01_AIS_new_category_final.csv'
    if not os.path.exists(file_path):
        st.error(f"파일을 찾을 수 없습니다: {file_path}")
        st.stop()
        
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    df = df.sort_values('timestamp').reset_index(drop=True)
    return df

df = load_full_data()

# 3. higher_types 기반 색상 정의 (RGB)
# 워게임 느낌을 위해 전술적 색상 배치
TYPE_COLORS = {
    'amphibious': [255, 165, 0],   # 주황
    'frigate': [255, 255, 0],      # 노랑
    'destroyer': [255, 0, 0],      # 빨강 (주요 전투함)
    'patrolship': [0, 255, 0],     # 초록
    'others': [150, 150, 150],     # 회색
    'navalmine': [255, 0, 255],    # 자주 (기뢰전함)
    'auxiliary': [0, 255, 255],    # 하늘 (지원함)
    'default': [255, 255, 255]     # 흰색
}

# 4. 사이드바 컨트롤
st.sidebar.header("🕹️ Simulation Control")
speed = st.sidebar.slider("시뮬레이션 속도", 1, 100, 20)
history_len = st.sidebar.slider("항적 표시 길이", 10, 500, 50)
refresh_rate = st.sidebar.slider("화면 갱신 주기", 1, 10, 2)

# 5. 레이아웃 구성
st.title("🛡️ 실시간 전술 상황도 (Higher Types 구분)")
col_map, col_packet = st.columns([3, 1])

with col_map:
    map_placeholder = st.empty()

with col_packet:
    st.subheader("📡 Outgoing Packets")
    packet_placeholder = st.empty()
    st.subheader("📊 Fleet Status")
    status_placeholder = st.empty()

# 6. 시뮬레이션 초기 설정 (한반도 뷰)
view_state = pdk.ViewState(
    latitude=36.5,
    longitude=127.5,
    zoom=6.5,
    pitch=0
)

# 7. 시뮬레이션 엔진 가동
if st.sidebar.button("시뮬레이션 시작"):
    mmsi_groups = {mmsi: group for mmsi, group in df.groupby('mmsi')}
    unique_times = df['timestamp'].unique()

    for i, current_time in enumerate(unique_times):
        
        current_step_packets = []
        path_layers_data = []
        scatter_data = []

        for mmsi, group in mmsi_groups.items():
            ship_history = group[group['timestamp'] <= current_time]
            if ship_history.empty:
                continue
                
            now_row = ship_history.iloc[-1]
            current_step_packets.append(now_row.to_dict())
            
            # higher_types 기반 색상 할당
            h_type = now_row.get('higher_types', 'others')
            s_color = TYPE_COLORS.get(h_type, TYPE_COLORS['others'])
            
            # (1) 마커용 데이터
            scatter_data.append({
                "longitude": now_row['longitude'],
                "latitude": now_row['latitude'],
                "name": now_row['ShipName'],
                "type": h_type,
                "color": s_color
            })
            
            # (2) 항적용 데이터
            recent_path = ship_history.tail(history_len)
            path_coords = recent_path[['longitude', 'latitude']].values.tolist()
            if len(path_coords) > 1:
                path_layers_data.append({
                    "path": path_coords,
                    "color": s_color
                })

        # --- 화면 업데이트 ---
        if i % refresh_rate == 0:
            # A. 지도 레이어 설정
            layers = [
                pdk.Layer(
                    "PathLayer",
                    path_layers_data,
                    get_path="path",
                    get_color="color",
                    width_min_pixels=2,
                    opacity=0.6
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    scatter_data,
                    get_position="[longitude, latitude]",
                    get_color="color",
                    get_radius=2000,
                    pickable=True
                )
            ]
            
            # [수정] 백그라운드 맵 문제를 해결하기 위해 map_provider를 명시
            # CartoDB 스타일은 API 키 없이도 안정적으로 작동합니다.
            map_placeholder.pydeck_chart(pdk.Deck(
                layers=layers,
                initial_view_state=view_state,
                map_style="light", # 'dark', 'light', 'road', 'satellite' 중 선택
                map_provider="carto", # Mapbox 대신 Carto 지도를 사용하여 하얀 화면 방지
                tooltip={"text": "Name: {name}\nType: {type}"}
            ))

            # B. 패킷 정보 업데이트
            if current_step_packets:
                latest_packet = current_step_packets[-1]
                packet_json = json.dumps(latest_packet, indent=2, ensure_ascii=False, default=str)
                packet_placeholder.code(packet_json, language='json')
                
                # C. 상태 요약창 업데이트
                with status_placeholder.container():
                    st.write(f"**Current Time:** {current_time}")
                    st.write(f"**Active Vessels:** {len(current_step_packets)}")
                    st.info(f"Monitor: {latest_packet['ShipName']} [{h_type}]")

        time.sleep(1/speed)