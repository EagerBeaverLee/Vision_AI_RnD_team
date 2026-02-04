import sys
import os

from qgis_setup import init_qgis_env
QGIS_PATH = init_qgis_env()

from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QPushButton
from PyQt6.QtCore import Qt
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsProject, QgsDataSourceUri, QgsCoordinateReferenceSystem
from qgis.gui import QgsMapCanvas

class MyGisApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt6 + PyQGIS 가상환경 연동 성공")
        self.setMinimumSize(1000, 750)

        # 중앙 위젯 및 레이아웃 설정
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)

        # 1. 지도 캔버스 생성
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(Qt.GlobalColor.white)
        layout.addWidget(self.canvas)

        # 2. 버튼 추가 (지도 로드용)
        self.btn_load = QPushButton("배경지도(OpenStreetMap) 로드")
        self.btn_load.setFixedHeight(50)
        self.btn_load.clicked.connect(self.add_osm_layer)
        layout.addWidget(self.btn_load)

    def add_osm_layer(self):
        crs = QgsCoordinateReferenceSystem("EPSG:3857")
        QgsProject.instance().setCrs(crs)
        
        # XYZ 방식의 OSM 레이어 설정
        uri = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        osm_layer = QgsRasterLayer(uri, "OpenStreetMap", "wms")

        csv_file = r"C:\Users\Dongheekoh\Downloads\Sample01_AIS_new_category_final.csv" 
        csv_layer = self.load_csv_layer(csv_file, x_field="longitude", y_field="latitude")

        # 3. 레이어 리스트 구성
        layers = []
        if csv_layer and csv_layer.isValid():
            layers.append(csv_layer) # CSV 레이어를 위에 쌓음
        if osm_layer.isValid():
            QgsProject.instance().addMapLayer(osm_layer)
            layers.append(osm_layer) # 배경지도를 아래에 쌓음

        # 4. 캔버스 업데이트 (이 부분이 핵심입니다)
        self.canvas.setDestinationCrs(crs) # 캔버스 좌표계 강제 일치
        self.canvas.setLayers(layers) # 준비된 레이어들을 캔버스에 전달
        self.canvas.zoomToFullExtent() # 모든 레이어가 다 보이도록 줌 조정


    def load_csv_layer(self, file_path, x_field="longitude", y_field="latitude", layer_name="CSV_Data"):
        """
        CSV 파일을 QGIS 레이어로 로드하는 함수
        :param file_path: CSV 파일의 전체 경로
        :param x_field: 경도(X) 데이터가 담긴 컬럼명
        :param y_field: 위도(Y) 데이터가 담긴 컬럼명
        :param layer_name: QGIS 레이어 패널에 표시될 이름
        """
        
        # 1. URI 설정 (구분자, X/Y 필드, 좌표계 등 정의)
        # 인코딩(encoding=UTF-8)과 좌표계(crs=epsg:4326)를 명시하는 것이 안전합니다.
        uri = f"file:///{file_path}?delimiter=,&xField={x_field}&yField={y_field}&crs=epsg:4326"
        
        # 2. 벡터 레이어 생성 (프로바이더를 'delimitedtext'로 지정)
        csv_layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
        
        # 3. 레이어 유효성 검사 및 프로젝트 추가
        if csv_layer.isValid():
            QgsProject.instance().addMapLayer(csv_layer)
            print(f"✅ '{layer_name}' 레이어가 성공적으로 로드되었습니다. (피처 수: {csv_layer.featureCount()})")
            return csv_layer
        else:
            print("❌ 레이어 로드 실패: 파일 경로 또는 URI 설정을 확인하세요.")
            return None

def main():
    # [5] QgsApplication 초기화
    QgsApplication.setPrefixPath(QGIS_PATH, True)
    qgs = QgsApplication([], True)
    qgs.initQgis()

    # 앱 실행
    win = MyGisApp()
    win.show()

    # 이벤트 루프
    exit_code = qgs.exec()
    
    # 종료 처리
    qgs.exitQgis()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()