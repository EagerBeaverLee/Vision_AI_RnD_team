#folium import
import folium
from streamlit_folium import st_folium

from windrose import WindroseAxes
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Polygon, Circle

import plotly.graph_objects as go

import altair as alt

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

import pandas as pd
import pydeck as pdk
from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
from streamlit.runtime import Runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx

import holoviews as hv
from bokeh.embed import file_html
from bokeh.resources import INLINE


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
    od_map_html = data_store.get("od_flow_map", "")
    test_map_html = data_store.get("test_map", "")

    if od_map_html:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown('<div class="card-dashboard">1</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                od_map_html, 
                height=400,
                scrolling=True
                
            )
        col4, col5, col6, col7 = st.columns([1,1,1,1])
    
        with col4:
            st.markdown('<div class="bar-dashboard">1</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                test_map_html, 
                height=200, 
                scrolling=True
            )
        with col5:
            st.markdown('<div class="bar-dashboard">2</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                test_map_html, 
                height=200, 
                scrolling=True
            )
        with col6:
            st.markdown('<div class="bar-dashboard">3</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                test_map_html, 
                height=200, 
                scrolling=True
            )
        with col7:
            st.markdown('<div class="bar-dashboard">4</div>', unsafe_allow_html=True)
            # 이미 완성된 HTML이므로 렌더링 과정 없이 바로 삽입
            # height는 보내는 쪽에서 설정한 frame_height보다 50~100px 정도 크게 잡으세요.
            components.html(
                test_map_html, 
                height=200, 
                scrolling=True
            )

    else:
        st.info("데이터 수신 대기 중입니다... (QThread를 시작해주세요)")

# 함수 실행
display_dashboard()