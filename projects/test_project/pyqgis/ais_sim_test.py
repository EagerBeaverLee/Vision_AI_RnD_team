import sys
import os

from qgis_setup import init_qgis_env
QGIS_PATH = init_qgis_env()

from datetime import timedelta

# PyQt6 Imports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel)
from PyQt6.QtCore import Qt, QTimer, QDateTime, QDate, QTime
from PyQt6.QtGui import QColor

# QGIS Imports
from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsSymbol,
    QgsRendererCategory, QgsCategorizedSymbolRenderer,
    QgsVectorLayerTemporalProperties, QgsDateTimeRange,
    QgsRasterLayer, QgsCoordinateReferenceSystem,
    QgsTemporalNavigationObject  # 시계열 제어 객체
)
from qgis.gui import QgsMapCanvas

# ==============================================================================
# 1. 환경 설정 (사용자 경로 수정 필수)
# ==============================================================================
# QGIS 설치 경로 (일반적인 Windows OSGeo4W 설치 경로 예시)
# bin 폴더가 아닌 apps/qgis 폴더를 지정해야 합니다.
QGIS_PREFIX_PATH = r"C:\Program Files\QGISQT6 3.44.6\apps\qgis-qt6" 
# CSV 데이터 경로
CSV_PATH = r"C:\Users\Dongheekoh\Downloads\Sample01_AIS_new_category_final.csv"

# 색상 정의
TYPE_COLORS = {
    'amphibious': QColor(255, 165, 0),
    'frigate': QColor(255, 255, 0),
    'destroyer': QColor(255, 0, 0),
    'patrolship': QColor(0, 255, 0),
    'others': QColor(150, 150, 150),
    'navalmine': QColor(255, 0, 255),
    'auxiliary': QColor(0, 255, 255),
    'default': QColor(255, 255, 255)
}

class AISSimulatorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt + QGIS AIS Simulation (EPSG:4326)")
        self.resize(1200, 800)

        # 상태 변수
        self.layer = None
        self.base_layer = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_simulation)
        self.current_time = None
        self.end_time = None
        
        # 시뮬레이션 설정
        self.simulation_speed_mins = 10  # 1프레임당 10분 진행
        self.trail_length_mins = 60      # 꼬리 길이 60분

        self.init_ui()
        self.load_layers()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 1. QGIS Map Canvas 설정
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor(20, 20, 20)) 
        self.canvas.enableAntiAliasing(True)
        
        # [수정 1] 좌표계를 EPSG:4326 (WGS 84)으로 강제 설정
        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        self.canvas.setDestinationCrs(crs_4326)
        
        # [수정 2] 시계열 제어기(Controller) 수동 생성 (NoneType 오류 해결)
        self.controller = QgsTemporalNavigationObject(self.canvas)
        self.canvas.setTemporalController(self.controller)
        
        layout.addWidget(self.canvas)

        # 2. 컨트롤 패널
        control_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 시뮬레이션 시작")
        self.btn_start.clicked.connect(self.toggle_simulation)
        control_layout.addWidget(self.btn_start)

        self.lbl_time = QLabel("Time: Ready")
        self.lbl_time.setStyleSheet("font-weight: bold; font-size: 14px;")
        control_layout.addWidget(self.lbl_time)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)

    def load_layers(self):
        # A. 배경 지도 (CartoDB Dark)
        # 배경 지도는 원본이 보통 3857이지만, 캔버스가 4326이므로 QGIS가 알아서 변환해줍니다.
        xyz_url = "type=xyz&url=https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png&zmax=19&zmin=0"
        self.base_layer = QgsRasterLayer(xyz_url, "Base Map", "wms")
        
        if self.base_layer.isValid():
            QgsProject.instance().addMapLayer(self.base_layer)
            self.canvas.setLayers([self.base_layer])
            self.canvas.setExtent(self.base_layer.extent())
        
        # B. AIS 데이터 (CSV) - EPSG:4326
        uri = f"file:///{CSV_PATH}?delimiter=,&xField=longitude&yField=latitude&crs=EPSG:4326"
        self.layer = QgsVectorLayer(uri, "AIS Data", "delimitedtext")

        if not self.layer.isValid():
            self.lbl_time.setText(f"Error: 파일 로드 실패")
            return

        # 스타일 적용
        self.apply_symbology(self.layer)
        
        # 시계열 속성 활성화
        tprops = self.layer.temporalProperties()
        tprops.setIsActive(True)
        # Enum 오류 방지를 위해 정수값 사용 (1 = Single Field Mode)
        tprops.setMode(QgsVectorLayerTemporalProperties.TemporalMode(1))
        tprops.setStartField("timestamp")
        
        QgsProject.instance().addMapLayer(self.layer)
        
        # 레이어 등록 (순서: AIS 위, 배경 아래)
        self.canvas.setLayers([self.layer, self.base_layer])
        
        # [중요] 캔버스가 4326이므로, 데이터 범위로 줌을 당기면 위경도 좌표계 비율로 보입니다.
        self.canvas.setExtent(self.layer.extent())
        self.canvas.refresh()

        # 시간 파싱 로직 (날짜/시간 호환성 강화)
        idx = self.layer.fields().indexFromName("timestamp")
        if idx >= 0:
            min_val = self.layer.minimumValue(idx)
            max_val = self.layer.maximumValue(idx)
            
            # 타입 자동 처리
            if isinstance(min_val, QDate):
                self.start_time = QDateTime(min_val, QTime(0, 0, 0))
                self.end_time = QDateTime(max_val, QTime(23, 59, 59)) if isinstance(max_val, QDate) else self.start_time.addDays(1)
            elif isinstance(min_val, QDateTime):
                self.start_time = min_val
                self.end_time = max_val
            else: # String Parsing
                s_min, s_max = str(min_val), str(max_val)
                self.start_time = QDateTime.fromString(s_min, Qt.DateFormat.ISODate)
                if not self.start_time.isValid():
                    self.start_time = QDateTime.fromString(s_min, "yyyy-MM-dd HH:mm:ss")
                self.end_time = QDateTime.fromString(s_max, Qt.DateFormat.ISODate)
                if not self.end_time.isValid():
                    self.end_time = QDateTime.fromString(s_max, "yyyy-MM-dd HH:mm:ss")

            if self.start_time.isValid():
                self.current_time = self.start_time
                self.lbl_time.setText(f"Ready: {self.start_time.toString('yyyy-MM-dd HH:mm')}")
            else:
                self.lbl_time.setText("Error: 날짜 포맷 인식 불가")

    def apply_symbology(self, layer):
        categories = []
        for type_name, color in TYPE_COLORS.items():
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            symbol.setSize(3)
            if type_name == 'default': continue
            categories.append(QgsRendererCategory(type_name, symbol, type_name))
            
        def_sym = QgsSymbol.defaultSymbol(layer.geometryType())
        def_sym.setColor(TYPE_COLORS['default'])
        categories.append(QgsRendererCategory(None, def_sym, "Others"))
        
        renderer = QgsCategorizedSymbolRenderer('higher_types', categories)
        layer.setRenderer(renderer)

    def toggle_simulation(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_start.setText("▶ 시뮬레이션 재개")
        else:
            if not self.current_time or not self.layer:
                return
            self.timer.start(100)
            self.btn_start.setText("⏸ 일시 정지")

    def update_simulation(self):
        if self.current_time >= self.end_time:
            self.timer.stop()
            self.btn_start.setText("종료됨")
            return

        # 시간 진행
        self.current_time = self.current_time.addSecs(self.simulation_speed_mins * 60)

        # 궤적(Trail) 범위 설정
        trail_start = self.current_time.addSecs(-self.trail_length_mins * 60)
        temporal_range = QgsDateTimeRange(trail_start, self.current_time)

        # [수정 3] Enum 호환성을 위해 정수값 사용 (FixedRange = 2)
        # AttributeError 방지를 위해 self.controller 객체 사용
        try:
            # 안전하게 정수를 Enum으로 변환 시도
            mode = QgsTemporalNavigationObject.NavigationMode(2)
            self.controller.setNavigationMode(mode)
        except:
            # 변환 실패 시 정수 직접 주입 (구버전 호환)
            self.controller.setNavigationMode(2)
            
        self.controller.setTemporalExtents(temporal_range)
        
        self.canvas.refresh()
        self.lbl_time.setText(f"Time: {self.current_time.toString('yyyy-MM-dd HH:mm')}")

if __name__ == '__main__':
    # 환경 변수 설정
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = QGIS_PREFIX_PATH + r"\plugins"
    os.environ["PATH"] += ";" + QGIS_PREFIX_PATH + r"\bin"

    qgs = QgsApplication([], True)
    qgs.setPrefixPath(QGIS_PREFIX_PATH, True)
    qgs.initQgis()

    app = AISSimulatorApp()
    app.show()

    exit_code = qgs.exec()
    qgs.exitQgis()
    sys.exit(exit_code)