import streamlit as st
import pydeck as pdk

# 초기 설정
if "v_state" not in st.session_state:
    st.session_state.v_state = {"latitude": 34.6, "longitude": 127.7, "zoom": 6}

# 슬라이더를 이용해 수동으로 조절하며 좌표 찾기 (가장 확실함)
st.sidebar.title("📍 좌표 찾기 도구")
lat = st.sidebar.slider("위도(Lat)", 30.0, 40.0, float(st.session_state.v_state['latitude']), 0.01)
lon = st.sidebar.slider("경도(Lon)", 120.0, 135.0, float(st.session_state.v_state['longitude']), 0.01)
zoom = st.sidebar.slider("줌(Zoom)", 0.0, 20.0, float(st.session_state.v_state['zoom']), 0.1)

# 슬라이더로 조절한 값을 세션에 저장
st.session_state.v_state.update({"latitude": lat, "longitude": lon, "zoom": zoom})

# 지도 생성
view_state = pdk.ViewState(**st.session_state.v_state)

bounds = [124.0, 30.0, 130.0, 36.0]

st.pydeck_chart(pdk.Deck(
    map_style=None,
    initial_view_state=view_state,
    map_constraints={
        "minZoom": 6,
        "maxZoom": 15,
        "extent": bounds  # [설정 핵심] 이 범위 밖으로 지도가 나가지 않음
    },
    layers=[]
))

# 현재 설정된 값을 텍스트로 크게 표시 (이걸 보고 bounds 결정)
st.code(f"""
// 현재 당신이 보고 있는 좌표와 줌입니다.
// 이 값을 복사해서 min_zoom과 bounds에 넣으세요!
min_zoom = {zoom:.2f}
bounds = [서쪽경도, 남쪽위도, 동쪽경도, 북쪽위도]
현재 중심: [{lon:.4f}, {lat:.4f}]
""")