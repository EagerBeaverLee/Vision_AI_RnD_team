import streamlit as st
import streamlit.components.v1 as components

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
from streamlit.runtime import Runtime

import holoviews as hv


st.markdown("""
    <style>
    /* 4. 카드 제목 스타일 */
    .card-dashboard {
        height: 50px;
        min-height: 30px !important;
        max-height: 30px !important;
        color: #B8F7B9;
        font-size: 1.1rem;
        font-weight: bold;
        margin-bottom: 1px;
        display: flex;
        align-items: center;
        gap: 8px;
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

# 1. 전역 데이터 저장소
@st.cache_resource
def get_global_store():
    return {}

# 데이터 저장소
data_store = get_global_store()

# 2. --- FastAPI 설정 ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/update")
async def update_api(request: Request):
    try:
        # [핵심] await를 사용하여 Form 데이터를 비동기적으로 수신합니다.
        payload = await request.json()
        if payload:
            data_store.update(payload)
            
            # Streamlit 화면 갱신 트리거
            runtime = Runtime.instance()
            for session_info in runtime._session_mgr.list_sessions():
                session_info.session.request_rerun(None)
                    
                return {"status": "success", "message": "Map updated"}
            return {"status": "fail", "message": "No HTML content"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# API 서버 실행
if 'api_running' not in st.session_state:
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8601, log_level="error"), daemon=True).start()
    st.session_state.api_running = True
# ======================================================================

# --- 3. UI 레이아웃 ---
st.set_page_config(layout="wide", page_title="실시간 항적 분석 대시보드")   # 넓게 보여주는 설정

# [중요] Holoviews에게 Bokeh를 백엔드로 사용한다고 명시적으로 알려줘야 합니다.
hv.extension('bokeh')

@st.fragment
def display_dashboard():
    # FastAPI의 data_store에서 HTML을 가져옴
    # 실제 환경에서는 전역 변수나 DB, 혹은 st.session_state를 통해 데이터가 공유되어야 합니다.
    moving_list = data_store.get("moving", "")
    stop_list = data_store.get("stop", "")
    slow_list = data_store.get("slow", "")

    def transform_data(data_list):
        try:
            # 데이터가 [{...}, {...}] 리스트 형태라면 바로 변환됩니다.
            if isinstance(data_list, list):
                res_list = pd.DataFrame(data_list)
            else:
                # 데이터가 만약 딕셔너리 형태라면 리스트로 감싸서 변환
                res_list = pd.DataFrame([data_list])
            return res_list
        except Exception as e:
            # 에러 발생 시 빈 데이터프레임이라도 만들어야 대시보드가 안 터집니다.
            print(f"변환 실패: {e}")
            res_list = pd.DataFrame(columns=['ShipName', 'mmsi'])
            return res_list
    
    moving_df = transform_data(moving_list)
    stop_df = transform_data(stop_list)
    slow_df = transform_data(slow_list)
    
    od_map_html = data_store.get("od_flow_map", "")
    shiptype_html = data_store.get("shiptype", "")
    port_map_0 = data_store.get("port_map_0", "")
    port_map_1 = data_store.get("port_map_1", "")
    port_map_2 = data_store.get("port_map_2", "")
    port_map_3 = data_store.get("port_map_3", "")

    # print("이동중인 선박")
    # print(moving_df)


    ship_data_dict = {
        "순항": moving_df,
        "정박": stop_df,
        "저속운항": slow_df,
    }
    
    # key디버깅
    # print("받은 data_store Key 리스트")
    # print(data_store.keys())

    if od_map_html:
        col1, col2, col3 = st.columns([1.2,2,1])
        with col1:
            st.markdown('<div class="card-dashboard">📋 함정 상세 목록</div>', unsafe_allow_html=True)
            status_filter = st.radio(
                "상태선택", ["순항", "정박", "저속운항"], 
                horizontal=True,  # 버튼을 가로로 배치해서 공간 절약
                label_visibility="collapsed"  # "visible", "hidden", "collapsed" 중 선택
            )

            # 3. [핵심] 선택된 값에 따라 데이터프레임 교체
            # 사용자가 '순항'을 누르면 status_filter는 "순항"이 되고, 
            # ship_data_dict["순항"]에 해당하는 데이터프레임이 선택됩니다.
            display_df = ship_data_dict[status_filter]

            # 라디오 버튼 아래에 검색창 추가
            search_term = st.text_input("🔍 함정명 또는 MMSI 검색", "")

            if search_term:
                # 이름이나 MMSI에 검색어가 포함된 행만 필터링
                display_df = display_df[
                    display_df['ShipName'].str.contains(search_term, case=False) | 
                    display_df['mmsi'].astype(str).str.contains(search_term)
                ]
            
            # 4. 필터링된 리스트 전시
            # 컬럼이 너무 많으면 지저분하므로 이름과 MMSI 등 필요한 정보만 보여줍니다.
            st.dataframe(
                display_df, 
                height=200,
                width='stretch', # 컬럼 너비를 화면에 맞게 꽉 채움
                hide_index=True          # 불필요한 인덱스 번호 숨기기
            )
        with col2:
            st.markdown('<div class="card-dashboard">Integrated Analysis: OD Flows, Avg Speed & Clusters</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                od_map_html, 
                height=370,
                scrolling=True                
            )
        with col3:
            st.markdown('<div class="card-dashboard">Shiptype Count</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                shiptype_html, 
                height=370,
                scrolling=True                
            )
        col4, col5 = st.columns([1,1])
    
        with col4:
            st.markdown('<div class="bar-dashboard">부산항 현황</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                port_map_0, 
                height=330, 
                scrolling=True
            )
        with col5:
            st.markdown('<div class="bar-dashboard">울산항 현황</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                port_map_1, 
                height=330, 
                scrolling=True
            )
        col6, col7 = st.columns([1,1])

        with col6:
            st.markdown('<div class="bar-dashboard">광양·하동항 현황</div>', unsafe_allow_html=True) 
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                port_map_2, 
                height=330, 
                scrolling=True
            )
        with col7:
            st.markdown('<div class="bar-dashboard">목포항 현황</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                port_map_3, 
                height=330, 
                scrolling=True
            )

    else:
        st.info("데이터 수신 대기 중입니다... (QThread를 시작해주세요)")

# 함수 실행
display_dashboard()