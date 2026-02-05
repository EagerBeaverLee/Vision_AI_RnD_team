# main_app.py
import sys
import os

# [추가] GPU 가속 끄기 & 원격 디버깅 허용
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
os.environ["QT_XCB_GL_INTEGRATION"] = "none"

from qgis_setup import init_qgis_env
QGIS_PATH = init_qgis_env()

qgis_prefix = r"C:\Program Files\QGISQT6 3.44.6\apps\qgis-qt6"

# QGIS 라이브러리 임포트
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer
from qgis.gui import QgsMapCanvas

# PyQt6 임포트
from PyQt6.QtWidgets import QApplication, QMainWindow, QSplitter, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, Qt

class HybridApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QGIS + Streamlit Hybrid App")
        self.resize(1600, 900)

        # 2. 메인 레이아웃 (좌우 분할)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- [왼쪽] QGIS 지도 캔버스 ---
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(Qt.GlobalColor.white)
        self.canvas.enableAntiAliasing(True)
        
        # 지도 예시: OpenStreetMap 레이어 추가 (인터넷 필요)
        url = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0"
        self.rlayer = QgsRasterLayer(url, "OpenStreetMap", "wms")
        
        if self.rlayer.isValid():
            QgsProject.instance().addMapLayer(self.rlayer)
            self.canvas.setExtent(self.rlayer.extent())
            self.canvas.setLayers([self.rlayer])
        else:
            print("레이어 로드 실패")

        # --- [오른쪽] Streamlit 뷰어 ---
        self.webview = QWebEngineView()
        # Streamlit 주소 (미리 켜둬야 함)
        self.webview.load(QUrl("http://localhost:8501"))

        # 스플리터에 위젯 추가
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.webview)

        # 초기 비율 설정 (지도 6 : 웹 4)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        self.setCentralWidget(splitter)

def main():
    argv_bytes = [arg.encode('utf-8') for arg in sys.argv]
    # 3. QGIS 애플리케이션 초기화
    # 두 번째 인자 True는 GUI 기능을 사용한다는 뜻
    qgs = QgsApplication(argv_bytes, True)
    qgs.setPrefixPath(qgis_prefix, True)
    qgs.initQgis()

    # 4. 앱 실행
    app = HybridApp()
    app.show()

    # 이벤트 루프 실행
    exit_code = qgs.exec()
    
    # 5. 종료 처리 (메모리 해제)
    qgs.exitQgis()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()