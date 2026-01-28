import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QSplitter, QTextEdit, QSizePolicy
from PyQt5.QtCore import Qt

class SplitterWithIgnoredPolicy(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QSplitter Ignored Size Policy")
        self.setGeometry(100, 100, 800, 600)
        
        main_layout = QVBoxLayout()
        
        self.splitter = QSplitter(Qt.Horizontal)
        
        self.left_panel = QTextEdit("왼쪽 패널\nSizePolicy.Ignored 적용")
        self.right_panel = QTextEdit("오른쪽 패널")
        
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        
        # --- 핵심 코드 ---
        # 1. 왼쪽 패널의 크기 정책을 Ignored로 설정
        #    -> QSplitter가 이 패널의 선호 크기를 무시하고 자유롭게 줄일 수 있게 됩니다.
        self.left_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        
        # 2. (기존 코드) 최소 크기를 0으로 설정
        self.left_panel.setMinimumSize(0, 0)
        self.right_panel.setMinimumSize(0, 0)
        
        # 3. (기존 코드) 스트레치 팩터 설정
        self.splitter.setStretchFactor(0, 0) # 왼쪽 패널은 늘어나지 않으려는 속성
        self.splitter.setStretchFactor(1, 1) # 오른쪽 패널은 남은 공간을 차지하려는 속성
        
        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SplitterWithIgnoredPolicy()
    ex.show()
    sys.exit(app.exec_())