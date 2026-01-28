import sys
from PyQt6.QtCore import Qt, QPropertyAnimation, QVariantAnimation, QRect, QEasingCurve, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QRadioButton, QWidget, QHBoxLayout, QMainWindow, QStyleOptionButton


class AnimatedRadioButton(QRadioButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(200) # 애니메이션 지속 시간 (밀리초)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad) # 부드러운 시작/끝 곡선

        # 애니메이션이 진행될 때마다 호출될 함수 연결
        self.animation.valueChanged.connect(self.update_indicator_color)
        
        self._current_color = QColor(255, 255, 255) # 초기 색상 (흰색)

        self.toggled.connect(self.start_color_animation)

    def start_color_animation(self, checked):
        if checked:
            start_color = QColor(40, 40, 40) # 배경색
            end_color = QColor(166, 217, 171) # 초록색
        else:
            start_color = QColor(166, 217, 171) # 초록색
            end_color = QColor(40, 40, 40) # 배경색

        self.animation.stop() # 이전 애니메이션이 있으면 중단
        self.animation.setStartValue(start_color)
        self.animation.setEndValue(end_color)
        self.animation.start()

    def update_indicator_color(self, color):
        self._current_color = color
        self.update() # 위젯을 다시 그리도록 요청

    def paintEvent(self, event):
        # 기본 paintEvent를 호출하여 라디오 버튼의 나머지 부분을 그린다.
        super().paintEvent(event)
        
         # indicator의 위치와 크기를 계산
        style = self.style()
        
        opt = QStyleOptionButton()
        # opt.initFrom(self)
        self.initStyleOption(opt)
        
        indicator_rect = style.subElementRect(
            style.SubElement.SE_RadioButtonIndicator,
            opt,
            self
        )
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isChecked():
            # 체크된 상태일 때만 애니메이션 색상으로 원을 그린다.
            painter.setBrush(self._current_color)
            painter.setPen(Qt.PenStyle.NoPen)
            # indicator_rect.center()를 사용하여 작은 원을 그린다.
            painter.drawEllipse(indicator_rect.center(), 6, 6)

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Animated Radio Button")
        self.setGeometry(300, 300, 300, 150)

        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        
        radio1 = AnimatedRadioButton("Option 1")
        radio2 = AnimatedRadioButton("Option 2")
        
        layout.addWidget(radio1)
        layout.addWidget(radio2)
        
        self.setCentralWidget(central_widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())
