import sys
import os

from qgis_setup import init_qgis_env

# 1. QGIS 환경 연결 (가상환경에 없는 PyQt6를 가져올 준비)
init_qgis_env()

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    print("성공: QtWebEngine이 로드되었습니다.")
    print(f"WebEngine Version Match check: {QWebEnginePage}")
except ImportError as e:
    print(f"실패: {e}")
except Exception as e:
    print(f"치명적 오류(버전 충돌 가능성): {e}")