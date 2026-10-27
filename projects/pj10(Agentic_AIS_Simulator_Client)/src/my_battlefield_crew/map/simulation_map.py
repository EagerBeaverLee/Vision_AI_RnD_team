import streamlit as st
import pandas as pd
import pydeck as pdk
import socket
import struct
import json
import threading
import queue
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
BIG_DATA_TYPE_COLORS_CLEAN = {
    'FIRST':	[31, 119, 180],    # 진한 파랑	
    'SECOND':	[255, 127, 14],    # 주황	    
    'THIRD':	[44, 160, 44],    # 초록	    
    'FOURTH':	[214, 39, 40],    # 빨강	    
    'FIFTH':	[148, 103, 189],    # 보라	    
    'SIXTH':	[140, 86, 75],    # 갈색	    
    'OTHER':	[227, 119, 194],    # 분홍
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
        while True:
        
            # 헤더 읽기 (Type 1B + Length 4B)
            header = b""
            while len(header) < 24:
                packet = client_socket.recv(24 - len(header))
                if not packet: return
                header += packet
            
            _, _, msg_len = struct.unpack('>B19sI', header)
            
            # 바디 읽기
            body = b""
            while len(body) < msg_len:
                packet = client_socket.recv(msg_len - len(body))
                if not packet: return
                body += packet
            
            # JSON 파싱 및 큐 삽입
            data = json.loads(body.decode('utf-8'))
            data_queue.put(data)
            
    except ConnectionResetError:
        print("🚨 서버에 의해 강제로 연결이 초기화되었습니다. (서버 다운 등)")
    except Exception as e:
        print(f"🚨 네트워크 에러 발생: {e}")
    finally:
        # [핵심] 정상 종료든, 에러든, 서버가 끊었든 마지막에는 무조건 소켓을 닫음
        client_socket.close()
        print("🔒 소켓이 안전하게 닫혔습니다.")

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
st.title("🛡️ AIS 대용량 시뮬레이터")
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
# 8. [최적화] 이중 속도 갱신 & 데이터 경량화
# ==========================================
# 상태 관리를 위한 변수 초기화 (한 번만 실행됨)
if 'loop_counter' not in st.session_state:
    st.session_state.loop_counter = 0

log_code_box.info("Waiting for data...")

@st.fragment(run_every=0.2) # 0.1초마다 매우 빠르게 실행 (데이터 수신용)
def run_simulation_loop():
    if not st.session_state.is_connected:
        return

    # 1. [고속 처리] 데이터 수신 및 상태 업데이트
    # 이 부분은 0.1초마다 수행되어야 큐가 밀리지 않음
    processed_count = 0
    latest_packet = None
    
    while not st.session_state.data_queue.empty():
        try:
            raw_item = st.session_state.data_queue.get_nowait()
            packets_to_process = raw_item if isinstance(raw_item, list) else [raw_item]
            
            for packet in packets_to_process:
                if not isinstance(packet, dict): continue

                mmsi = packet.get('mmsi')
                if not mmsi: continue

                if packet.get('longitude') < 125.6 or packet.get('longitude') > 131.2:
                    # 디버깅 로그
                    # print("lon out")
                    st.session_state.ship_states.pop(mmsi, None)
                    continue

                if packet.get('latitude') > 36:
                    # 디버깅 로그
                    # print("lat out")
                    st.session_state.ship_states.pop(mmsi, None)
                    continue
                
                # 상태 업데이트
                st.session_state.ship_states[mmsi] = packet
                latest_packet = packet
                processed_count += 1
                
                # 항적 업데이트
                if mmsi not in st.session_state.ship_trails:
                    st.session_state.ship_trails[mmsi] = deque(maxlen=history_len)
                
                st.session_state.ship_trails[mmsi].append([packet.get('longitude'), packet.get('latitude')])
            
        except queue.Empty:
            break
            
    st.session_state.packet_counter += processed_count

    # 2. [고속 갱신] 텍스트/숫자 UI는 매번 갱신 (가벼움)
    # metric_total.metric("Total Packets", f"{st.session_state.packet_counter:,}")
    # metric_active.metric("Active Ships", len(st.session_state.ship_states))
    # metric_rate.metric("Process Rate", f"{processed_count * 10}/sec") # 0.1s * 10

    # -----------------------------------------------------------
    # 3. [저속 갱신] 지도는 무거우므로 가끔 그리기 (핵심 최적화)
    # -----------------------------------------------------------
    st.session_state.loop_counter += 1
    
    # 10번 루프당 1번만 지도 갱신 (0.1s * 10 = 1.0초 간격)
    # 데이터 양이 많으면 이 값을 20(2초), 30(3초)으로 늘리세요.
    # run_every(0.4초) * MAP_UPDATE_INTERVAL(10) = 4초마다 갱신
    MAP_UPDATE_INTERVAL = 1
    
    if st.session_state.loop_counter % MAP_UPDATE_INTERVAL == 0:
        
        scatter_data = []
        path_data = []

        # 데이터 변환 (여기서 시간이 가장 많이 걸림)
        for mmsi, info in st.session_state.ship_states.items():
            if info is None:
                continue
            raw_type = str(info.get('higher_types', 'others'))
            #숫자인지 판별하여 숫자아닐경우 값 입력(빈데이터 처리)
            # if not raw_type.isdigit(): raw_type = '9'
            color = TYPE_COLORS.get(raw_type, TYPE_COLORS['others'])
            # color = BIG_DATA_TYPE_COLORS_CLEAN.get(raw_type, BIG_DATA_TYPE_COLORS_CLEAN['OTHER'])
            
            # 스캐터 데이터
            scatter_data.append({
                "name": info.get('ShipName', 'Unknown'),
                "coordinates": [info.get('longitude'), info.get('latitude')],
                "color": color,
                "type": raw_type,
                "mmsi": mmsi,
                "speed": info.get('speed', '0')
            })
            
            # [경량화] 항적 데이터 다운샘플링 (Downsampling)
            # 점이 20개 이상일 때만, 2칸 건너뛰어서 그리기 (데이터 1/2 감소)
            # history_len이 100개라면 [::5]로 5칸씩 건너뛰게 하세요.
            trail = st.session_state.ship_trails[mmsi]
            if len(trail) > 1:
                # 데이터가 너무 많으면 다운샘플링 비율을 높임 (예: [::5])
                # sampled_trail = list(trail)[::2] if len(trail) > 10 else list(trail)
                
                path_data.append({
                    # "path": sampled_trail,
                    "path": list(trail),
                    "color": color
                })

        # TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        
        # tile_layer = pdk.Layer(
        #     "TileLayer",
        #     data=TILE_URL,
        #     opacity=0.6 # 지도가 너무 밝으면 0.6 ~ 0.8 정도로 조절
        # )

        # Pydeck 렌더링
        layers = [
            # tile_layer,
            pdk.Layer(
                "PathLayer",
                path_data,
                get_path="path",
                get_color="color",
                width_min_pixels=2, # 선 두께 줄임
                opacity=0.5         # 투명도 높임
            ),
            pdk.Layer(
                "ScatterplotLayer",
                scatter_data,
                get_position="coordinates",
                get_fill_color="color",
                get_radius=1500, # 반지름 약간 줄임
                pickable=True,
                auto_highlight=True
            )
        ]
        
        # 맵 갱신
        deck = pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            # map_provider=None,  # 기본 인터넷 지도 제공자 끄기
            # map_style="mapbox://styles/mapbox/streets-v12",
            tooltip={"text": "Name: {name}\nMMSI: {mmsi}\nspeed: {speed}"}
        )
        # map_chart_placeholder.pydeck_chart(deck)
        map_chart_placeholder.pydeck_chart(
            deck, 
            # use_container_width=True,
            width='stretch',
            key="ais_realtime_map" 
        )

    # 3. 로그 업데이트
    if latest_packet:
        log_code_box.code(json.dumps(latest_packet, indent=2, ensure_ascii=False, default=str), language='json')

    if latest_packet and isinstance(latest_packet, dict):
        current_ts = latest_packet['timestamp']

        status_text = f"""Server Time: {current_ts}\nTracked Ships: {len(st.session_state.ship_states)}\nPacket Size: {processed_count * 2.5}/sec"""

        # 2. 합친 문자열을 code 블록에 덮어쓰기 (언어는 일반 텍스트이므로 None 또는 'text' 사용)
        status_placeholder.code(status_text, language='text')

# 앱 실행
run_simulation_loop()