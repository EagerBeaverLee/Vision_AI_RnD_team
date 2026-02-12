import streamlit as st
import pandas as pd
import pydeck as pdk
import socket
import struct
import json
import threading
import queue
import time
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Naval Real-time Wargame", layout="wide", initial_sidebar_state="expanded")

# 2. 전술 색상 정의 (Higher Types)
TYPE_COLORS = {
    'amphibious': [255, 165, 0],   # 주황
    'frigate': [255, 255, 0],      # 노랑
    'destroyer': [255, 0, 0],      # 빨강
    'patrolship': [0, 255, 0],     # 초록
    'others': [150, 150, 150],     # 회색
    'navalmine': [255, 0, 255],    # 자주
    'auxiliary': [0, 255, 255],    # 하늘
    'default': [255, 255, 255]     # 흰색
}
BIG_DATA_TYPE_COLORS = {
    '1':	[31, 119, 180],    # 진한 파랑	
    '2':	[255, 127, 14],    # 주황	    
    '3':	[44, 160, 44],    # 초록	    
    '4':	[214, 39, 40],    # 빨강	    
    '5':	[148, 103, 189],    # 보라	    
    '6':	[140, 86, 75],    # 갈색	    
    '7':	[227, 119, 194],    # 분홍	    
    '8':	[127, 127, 127],    # 회색	    
    '9':	[188, 189, 34],    # 황토색	    
}

# 3. 세션 상태 초기화 (데이터 누적용)
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = queue.Queue()
if 'accumulated_df' not in st.session_state:
    # 빈 데이터프레임 생성 (컬럼은 실제 데이터에 맞춰 자동 확장됨)
    st.session_state.accumulated_df = pd.DataFrame()
if 'is_connected' not in st.session_state:
    st.session_state.is_connected = False

# 4. 소켓 수신 스레드 함수
def socket_client_thread(host, port, data_queue):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((host, port))
        st.toast(f"✅ 서버 연결 성공 ({host}:{port})")
    except Exception as e:
        st.error(f"서버 연결 실패: {e}")
        return

    while True:
        try:
            # 헤더 읽기 (Type 1B + Length 4B)
            header = b""
            while len(header) < 5:
                packet = client_socket.recv(5 - len(header))
                if not packet: return
                header += packet
            
            _, msg_len = struct.unpack('>BI', header)
            
            # 바디 읽기
            body = b""
            while len(body) < msg_len:
                packet = client_socket.recv(msg_len - len(body))
                if not packet: return
                body += packet
            
            # JSON 파싱 및 큐 삽입
            data = json.loads(body.decode('utf-8'))
            data_queue.put(data)
            
        except Exception as e:
            break
    client_socket.close()

# 5. 사이드바 컨트롤
st.sidebar.header("🕹️ Real-time Control")
host_ip = st.sidebar.text_input("Server IP", "127.0.0.1")
port_num = st.sidebar.number_input("Port", value=9999)
history_len = st.sidebar.slider("항적 표시 길이 (Trails)", 5, 100, 20)

# 연결 버튼
if not st.session_state.is_connected:
    if st.sidebar.button("📡 서버 연결 시작"):
        t = threading.Thread(target=socket_client_thread, args=(host_ip, port_num, st.session_state.data_queue))
        t.daemon = True
        t.start()
        st.session_state.is_connected = True
        st.rerun()
else:
    if st.sidebar.button("🛑 연결 종료 (새로고침)"):
        st.session_state.is_connected = False
        st.session_state.accumulated_df = pd.DataFrame() # 데이터 초기화
        st.rerun()

# 6. 메인 레이아웃
st.title("🛡️ 실시간 전술 상황도 (Live Stream)")
col_map, col_packet = st.columns([3, 1])

with col_map:
    map_placeholder = st.empty()

with col_packet:
    st.subheader("📡 Live Packet Stream")
    packet_placeholder = st.empty()
    st.subheader("📊 Fleet Status")
    status_placeholder = st.empty()

# 7. 뷰 스테이트 (초기값)
view_state = pdk.ViewState(
    latitude=36.5, 
    longitude=127.5, 
    zoom=6.5, 
    pitch=0
)

# ==========================================
# 8. 메인 루프 (데이터 수신 및 화면 갱신)
# ==========================================
if st.session_state.is_connected:
    while True:
        # A. 큐에서 데이터 가져오기 (쌓인거 몽땅 가져오기)
        new_packets = []
        try:
            while not st.session_state.data_queue.empty():
                packet = st.session_state.data_queue.get_nowait()
                if isinstance(packet, list):
                    new_packets.extend(packet)
                else:
                    new_packets.append(packet)
        except queue.Empty:
            pass

        # B. 데이터가 있을 때만 처리
        if new_packets:
            new_df = pd.DataFrame(new_packets)
            
            # 타임스탬프 변환 (문자열 -> datetime)
            if 'timestamp' in new_df.columns:
                 # UTC 제거 처리 등은 데이터 형식에 맞춰 조정 필요
                try:
                    new_df['timestamp'] = pd.to_datetime(new_df['timestamp'].astype(str).str.replace(' UTC', ''), errors='coerce')
                except:
                    pass

            # 누적 데이터프레임 업데이트
            st.session_state.accumulated_df = pd.concat([st.session_state.accumulated_df, new_df], ignore_index=True)
            
            # --- 시각화 데이터 준비 ---
            path_layers_data = []
            scatter_data = []
            
            # MMSI별로 그룹화하여 최신 위치와 궤적 계산
            if not st.session_state.accumulated_df.empty:
                # 성능 최적화를 위해 너무 오래된 데이터는 삭제 (선택 사항)
                # st.session_state.accumulated_df = st.session_state.accumulated_df.tail(5000)

                grouped = st.session_state.accumulated_df.groupby('mmsi')
                
                for mmsi, group in grouped:
                    # (1) 현재 위치 (가장 최근 데이터)
                    last_row = group.iloc[-1]
                    # h_type = last_row.get('higher_types', 'others')
                    # s_color = TYPE_COLORS.get(h_type, TYPE_COLORS['others'])
                    raw_type = last_row.get('unique_type', '9')
                    h_type_str = str(int(raw_type)) if pd.notna(raw_type) else '9'
                    # 2. 색상 가져오기
                    s_color = BIG_DATA_TYPE_COLORS.get(h_type_str, BIG_DATA_TYPE_COLORS['9'])

                    ship_name = last_row.get('name')
                    if pd.isna(ship_name) or str(ship_name).strip() == "":
                        ship_name = "Unknown"
                    
                    scatter_data.append({
                        "longitude": last_row['longitude'],
                        "latitude": last_row['latitude'],
                        "name": ship_name,
                        "type": h_type_str,
                        "color": s_color
                    })

                    # (2) 항적 (최근 N개 좌표)
                    if len(group) > 1:
                        # 사용자가 설정한 history_len 만큼만 자르기
                        recent_path = group.tail(history_len)
                        path_coords = recent_path[['longitude', 'latitude']].values.tolist()
                        
                        path_layers_data.append({
                            "path": path_coords,
                            "color": s_color
                        })

                # --- Pydeck 차트 갱신 ---
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

                # 맵 그리기
                map_placeholder.pydeck_chart(pdk.Deck(
                    layers=layers,
                    initial_view_state=view_state,
                    map_style="light",
                    map_provider="carto",
                    tooltip={"text": "Name: {name}\nType: {type}"}
                ))

                # --- 정보 패널 갱신 ---
                # 가장 마지막에 들어온 패킷 정보 표시
                latest_packet_data = new_packets[-1]
                packet_placeholder.code(json.dumps(latest_packet_data, indent=2, ensure_ascii=False, default=str), language='json')
                
                with status_placeholder.container():
                    current_ts = latest_packet_data.get('timestamp', 'Unknown')
                    st.write(f"**Server Time:** {current_ts}")
                    st.write(f"**Tracked Ships:** {len(grouped)}")
                    st.write(f"**Packet Size:** {len(new_packets)} rows")

        # CPU 과점유 방지 (약 10FPS)
        time.sleep(0.1)