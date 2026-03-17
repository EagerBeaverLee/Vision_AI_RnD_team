#folium import
import folium
from streamlit_folium import st_folium


import plotly.express as px
import plotly.graph_objects as go

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


@st.fragment
def render_folium_map():
    df = data_store["df"] # 전역 저장소에서 데이터 호출
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if not df.empty:
            # 지도 생성 (CartoDB Positron 타이틀이 깔끔합니다)
            m = folium.Map(location=[34.6, 127.7], zoom_start=7, tiles='openstreetmap')

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
                    <div style="font-size: 9pt; color: #ff0000;">{row['temp']}°C</div>
                    <div style="font-size: 9pt; color: #000fff;">{row['hum']}%</div>
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
                    tooltip=row['지점명']
                ).add_to(m)

            # 지도 표시 및 클릭 이벤트 수신
            output = st_folium(m, width='100%', height=700, key="folium_map")
            
            # 마커 클릭 시 상세정보 업데이트 로직
            if output.get("last_object_clicked_tooltip"):
                clicked_name = output["last_object_clicked_tooltip"]
                st.session_state.selected_station = df[df['지점명'] == clicked_name].iloc[0].to_dict()
                st.rerun() # 상세 정보창 갱신
        else:
            st.info("데이터 수신 대기 중...")


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
# main_dashboard()