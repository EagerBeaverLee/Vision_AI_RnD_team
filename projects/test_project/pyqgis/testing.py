import sys
import os

from qgis_setup import init_qgis_env
QGIS_PATH = init_qgis_env()

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import qVersion

# 1. 앱(QApplication)이 없으면 만들어줍니다.
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

print(f"✅ 현재 Qt 버전: {qVersion()}")

try:
    # 2. 이제 위젯을 만들어도 안전합니다.
    view = QWebEngineView()
    view.setHtml("<h1>Hello QtWebEngine!</h1>")
    view.resize(800, 600)
    view.show()
    
    print("🏆 대성공! WebEngine이 정상적으로 생성되었습니다.")
    
    # 창을 유지하려면 아래 주석 해제 (QGIS 외부 실행 시 필요)
    sys.exit(app.exec()) 

except Exception as e:
    print(f"❌ 실행 중 오류: {e}")