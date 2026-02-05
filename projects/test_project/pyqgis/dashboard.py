# dashboard.py
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(layout="wide")
st.title("📊 QGIS 연동 대시보드")

st.write("이 화면은 QGIS 우측 패널에 표시됩니다.")

# 예시 데이터 차트
chart_data = pd.DataFrame(np.random.randn(20, 3), columns=["A", "B", "C"])
st.line_chart(chart_data)

st.success("QtWebEngine(Qt 6.8.1)에서 정상 작동 중!")