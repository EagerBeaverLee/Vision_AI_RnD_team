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
from collections import deque # [성능 포인트 1] Deque 추가

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

# 3. [중요] 세션 상태 초기화 (코드 최상단으로 이동하여 오류 방지)
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = queue.Queue()

# [성능 포인트 2] DataFrame 대신 Dictionary와 Deque 사용
if 'ship_states' not in st.session_state:
    st.session_state.ship_states = {} # {mmsi: latest_packet_dict}
if 'ship_trails' not in st.session_state:
    st.session_state.ship_trails = {} # {mmsi: deque([(lon, lat), ...])}

if 'packet_counter' not in st.session_state:
    st.session_state.packet_counter = 0
if 'is_connected' not in st.session_state:
    st.session_state.is_connected = False
if 'thread_running' not in st.session_state:
    st.session_state.thread_running = False

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
st.title("🛡️ 실시간 전술 상황도 (Optimized)")
col_map, col_packet = st.columns([3, 1])

with col_map:
    map_placeholder = st.empty()

with col_packet:
    st.subheader("📡 Status")
    status_placeholder = st.empty()
    st.subheader("📝 Last Packet")
    packet_placeholder = st.empty()

# 7. 뷰 스테이트
view_state = pdk.ViewState(latitude=36.5, longitude=127.5, zoom=6.5, pitch=0)

# ==========================================
# 8. [성능 포인트 3] Fragment를 이용한 부분 갱신
# ==========================================
@st.fragment(run_every=0.5) # 0.5초마다 이 함수만 재실행
def run_simulation_loop():
    if not st.session_state.is_connected:
        status_placeholder.warning("Disconnected")
        return

    processed_count = 0
    latest_packet = None
    
    # 큐에 있는 데이터를 싹 비울 때까지 반복
    while not st.session_state.data_queue.empty():
        try:
            # 1. 큐에서 아이템 꺼내기
            raw_item = st.session_state.data_queue.get_nowait()
            
            # 2. [수정] 아이템이 리스트(배치)인지 단일 딕셔너리인지 확인하여 통일
            # 리스트면 그대로 쓰고, 단일 딕셔너리면 리스트로 감싸서 for문 돌리기 편하게 만듦
            packets_to_process = raw_item if isinstance(raw_item, list) else [raw_item]
            
            # 3. 패킷 처리 루프
            for packet in packets_to_process:
                # 혹시라도 빈 데이터나 이상한 데이터가 섞여있을 경우 방어
                if not isinstance(packet, dict):
                    continue

                mmsi = packet.get('mmsi')
                if not mmsi: continue
                
                # 최신 상태 업데이트 (Dict 사용 -> O(1) 속도)
                st.session_state.ship_states[mmsi] = packet
                latest_packet = packet
                processed_count += 1
                
                # 항적 업데이트 (Deque 사용 -> 자동 길이 조절)
                if mmsi not in st.session_state.ship_trails:
                    st.session_state.ship_trails[mmsi] = deque(maxlen=history_len)
                
                st.session_state.ship_trails[mmsi].append([packet.get('longitude'), packet.get('latitude')])
            
        except queue.Empty:
            break
            
    st.session_state.packet_counter += processed_count

    # --- 시각화 데이터 준비 ---
    scatter_data = []
    path_data = []

    for mmsi, info in st.session_state.ship_states.items():
        # 색상 처리
        raw_type = str(info.get('unique_type', '9'))
        if not raw_type.isdigit(): raw_type = '9'
        color = BIG_DATA_TYPE_COLORS.get(raw_type, BIG_DATA_TYPE_COLORS['9'])
        
        scatter_data.append({
            "name": info.get('name', 'Unknown'),
            "coordinates": [info.get('longitude'), info.get('latitude')],
            "color": color,
            "type": raw_type,
            "mmsi": mmsi
        })
        
        # 항적 데이터
        if len(st.session_state.ship_trails[mmsi]) > 1:
            path_data.append({
                "path": list(st.session_state.ship_trails[mmsi]),
                "color": color
            })

    # 맵 그리기
    layers = [
        pdk.Layer(
            "PathLayer",
            path_data,
            get_path="path",
            get_color="color",
            width_min_pixels=2,
            opacity=0.6
        ),
        pdk.Layer(
            "ScatterplotLayer",
            scatter_data,
            get_position="coordinates",
            get_fill_color="color",
            get_radius=2000,
            pickable=True,
            auto_highlight=True
        )
    ]

    map_placeholder.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="light",
        tooltip={"text": "Name: {name}\nMMSI: {mmsi}\nType: {type}"}
    ))

    # 정보창 갱신
    with status_placeholder.container():
        st.metric("Total Packets", f"{st.session_state.packet_counter:,}")
        st.metric("Active Ships", len(st.session_state.ship_states))
        st.text(f"Processing: {processed_count} items/tick")

    if latest_packet:
        packet_placeholder.code(json.dumps(latest_packet, ensure_ascii=False), language='json')

# 앱 실행 시 루프 시작
run_simulation_loop()