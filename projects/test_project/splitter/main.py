import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QSplitter, QTextEdit, QPushButton
from PyQt5.QtCore import Qt

class SplitterToggleExample(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QSplitter Collapse Toggle")
        self.setGeometry(100, 100, 800, 600)
        
        main_layout = QVBoxLayout()
        
        # QSplitter 위젯 생성
        self.splitter = QSplitter(Qt.Horizontal)
        
        # QSplitter에 추가할 위젯들
        self.left_panel = QTextEdit("왼쪽 패널\n버튼을 눌러보세요.")
        self.right_panel = QTextEdit("오른쪽 패널")
        
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        
        # 초기 크기 설정 (줄어든 상태를 저장하기 위함)
        self.default_left_size = 200
        self.splitter.setSizes([self.default_left_size, 600])
        
        # 버튼 생성
        self.toggle_button = QPushButton("왼쪽 패널 토글")
        
        # 버튼의 clicked 시그널을 슬롯에 연결
        self.toggle_button.clicked.connect(self.toggle_left_panel)
        
        main_layout.addWidget(self.splitter)
        main_layout.addWidget(self.toggle_button)
        
        self.setLayout(main_layout)
        
    def toggle_left_panel(self):
        """
        왼쪽 패널을 줄이거나 복원하는 슬롯
        """
        current_sizes = self.splitter.sizes()
        left_panel_size = current_sizes[0]
        right_panel_size = current_sizes[1]
        
        # 현재 왼쪽 패널이 줄어든 상태인지 확인 (size가 0이거나 0에 가까운 값)
        if left_panel_size < 5:
            # 줄어든 상태라면, 원래 크기로 복원
            self.splitter.setSizes([self.default_left_size, right_panel_size])
        else:
            # 줄어들지 않은 상태라면, 크기를 0으로 줄임
            self.splitter.setSizes([0, left_panel_size + right_panel_size])