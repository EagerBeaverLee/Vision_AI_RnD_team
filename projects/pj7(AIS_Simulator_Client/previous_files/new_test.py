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

# 6. 메인 레이아웃 구성 (여기서 빈 그릇들을 미리 다 만들어둡니다!)
st.title("🛡️ 실시간 전술 상황도 (No-Blink)")
col_map, col_packet = st.columns([3, 1])

# [지도 영역]
with col_map:
    # 지도는 어쩔 수 없이 pydeck_chart를 호출해야 하지만, empty에 덮어쓰면 깜빡임 최소화
    map_chart_placeholder = st.empty()

# [정보 영역] - 미리 레이아웃을 잡아두고 변수에 할당합니다.
with col_packet:
    st.subheader("📡 Status")
    # 컬럼 3개를 미리 만들고 각각의 'empty' 슬롯을 확보
    status_placeholder = st.empty()
    
    st.subheader("📝 Last Packet")
    # 로그가 찍힐 공간 확보
    log_code_box = st.empty()

# 7. 뷰 스테이트
view_state = pdk.ViewState(latitude=36.5, longitude=127.5, zoom=6.5, pitch=0)

# ==========================================
# 8. Fragment 루프 (업데이트 로직)
# ==========================================
@st.fragment(run_every=0.5)
def run_simulation_loop():
    # 연결 안됐으면 조용히 리턴
    if not st.session_state.is_connected:
        return

    processed_count = 0
    latest_packet = None
    
    # 큐 비우기
    while not st.session_state.data_queue.empty():
        try:
            raw_item = st.session_state.data_queue.get_nowait()
            packets_to_process = raw_item if isinstance(raw_item, list) else [raw_item]
            
            for packet in packets_to_process:
                if not isinstance(packet, dict): continue

                mmsi = packet.get('mmsi')
                if not mmsi: continue
                
                st.session_state.ship_states[mmsi] = packet
                latest_packet = packet
                processed_count += 1
                
                if mmsi not in st.session_state.ship_trails:
                    st.session_state.ship_trails[mmsi] = deque(maxlen=history_len)
                
                st.session_state.ship_trails[mmsi].append([packet.get('longitude'), packet.get('latitude')])
            
        except queue.Empty:
            break
            
    st.session_state.packet_counter += processed_count

    # --- 데이터 준비 ---
    scatter_data = []
    path_data = []

    for mmsi, info in st.session_state.ship_states.items():
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
        
        if len(st.session_state.ship_trails[mmsi]) > 1:
            path_data.append({
                "path": list(st.session_state.ship_trails[mmsi]),
                "color": color
            })

    # --- [핵심] 미리 만들어둔 빈 그릇(Placeholder)에 내용만 채워넣기 ---
    
    # 1. 지도 업데이트
    # Pydeck은 데이터가 많으면 렌더링에 시간이 걸리지만, placeholder에 덮어쓰면 깜빡임은 줄어듭니다.
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
    
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="light",
        tooltip={"text": "Name: {name}\nMMSI: {mmsi}\nType: {type}"}
    )
    map_chart_placeholder.pydeck_chart(deck)

    # 2. 메트릭 업데이트 (with container() 사용 안함 -> 깜빡임 제거)
    # metric_total.metric("Total Packets", f"{st.session_state.packet_counter:,}")
    # metric_active.metric("Active Ships", len(st.session_state.ship_states))
    # metric_rate.metric("Process Rate", f"{processed_count * 2}/sec")

    # 3. 로그 업데이트
    if latest_packet:
        log_code_box.code(json.dumps(latest_packet, indent=2, ensure_ascii=False, default=str), language='json')
    else:
        log_code_box.info("Waiting for data...")

    with status_placeholder.container():
        if latest_packet and isinstance(latest_packet, dict):
            current_ts = latest_packet['timestamp']
            st.write(f"**Server Time:** {current_ts}")
            st.write(f"**Tracked Ships:** {len(st.session_state.ship_states)}")
            st.write(f"**Packet Size:** {processed_count * 2}/sec")

# 앱 실행
run_simulation_loop()