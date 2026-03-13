import streamlit as st
import pandas as pd
import pydeck as pdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
from streamlit.runtime import Runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx

# 1. 전역 데이터 저장소
@st.cache_resource
def get_global_store():
    return {"df": pd.DataFrame()}

# 데이터 저장소
data_store = get_global_store()

# 2. FastAPI 설정
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

# --- 3. UI 레이아웃 ---
st.set_page_config(layout="wide", page_title="실시간 해양 관측망")

# 메인 타이틀은 프래그먼트 밖에 두어 고정
# st.title("📡 실시간 해양 기상 관측 시스템")

# --- 4. 통합 프래그먼트 (지도 + 대시보드) ---
@st.fragment
def main_dashboard():
    df = data_store["df"]
    
    # 컬럼 정의를 프래그먼트 안으로 이동 (에러 해결 핵심)
    m_col1, m_col2 = st.columns([3, 1])
    
    with m_col1:
        if not df.empty:
            # 데이터 클리닝 및 라벨 생성
            df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
            df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
            
            # 1. 가독성을 위해 텍스트 미리 생성 (줄바꿈 및 단위 포함)
            df["temp_text"] = df["temp"].astype(str) + "°C"
            df["hum_text"] = df["hum"].astype(str) + "%"

            view_state = pdk.ViewState(
                latitude=34.6,
                longitude=127.7,
                zoom=6, pitch=0
            )            
            point_layer = pdk.Layer(
                "ScatterplotLayer", df, id="points",
                get_position=["longitude", "latitude"],
                get_fill_color=[255, 60, 60, 200],
                get_radius=5000, pickable=True,
            )

            name_layer = pdk.Layer(
                "TextLayer",
                df,
                id="label-name",
                get_position=["longitude", "latitude"],
                get_text="지점명",
                get_size=54, # 크기를 확실하게 키움
                font_family="'Malgun Gothic', 'Dotum', 'Apple SD Gothic Neo', sans-serif",
                font_weight="bold",
                get_color=[0, 0, 0],
                get_background_color=[255, 255, 255, 200],
                get_pixel_offset=[0, -15],
                get_alignment_baseline="'bottom'",
                character_set="'auto'"
            )
            temp_layer = pdk.Layer(
                "TextLayer",
                df,
                id="label-temp",
                get_position=["longitude", "latitude"],
                get_text="temp_text",
                get_size=44, # 크기를 확실하게 키움
                line_height=1.0,
                font_family="'Malgun Gothic', 'Dotum', 'Apple SD Gothic Neo', sans-serif",
                font_weight="bold",
                get_color=[0, 0, 0],
                get_background_color=[255, 255, 255, 200],
                get_pixel_offset=[0, -10],
                get_alignment_baseline="'bottom'",
                # character_set=None
                character_set="'auto'"
            )
            hum_layer = pdk.Layer(
                "TextLayer",
                df,
                id="label-hum",
                get_position=["longitude", "latitude"],
                get_text="hum_text",
                get_size=44, # 크기를 확실하게 키움
                line_height=1.0,
                font_family="'Malgun Gothic', 'Dotum', 'Apple SD Gothic Neo', sans-serif",
                font_weight="bold",
                get_color=[0, 0, 0],
                get_background_color=[255, 255, 255, 200],
                get_pixel_offset=[0, -3],
                get_alignment_baseline="'bottom'",
                # character_set=None
                character_set="'auto'"
            )
            

            chart_container = st.empty()
            chart_container.pydeck_chart(
                pdk.Deck(
                    layers=[point_layer, name_layer, temp_layer, hum_layer],
                    initial_view_state=view_state, 
                    map_style="light",
                    tooltip={
                        "html": "<b>{지점명}</b><br>온도: {temp}°C<br>습도: {hum}%",
                        "style": {"backgroundColor": "white", "color": "black"}
                    }
                ),
                key="satellite_map"  # 고유 키가 중요합니다!
            )

        else:
            st.info("🛰️ 실시간 위성 데이터를 기다리는 중입니다...")

# 프래그먼트 실행
main_dashboard()