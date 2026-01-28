import sys
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, 
    QTextEdit, QProgressDialog, QProgressBar, QLabel
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer

# ----------------------------------------------------
# 1. 백그라운드 작업 (LLM 호출을 시뮬레이션)
# ----------------------------------------------------

class WorkerThread(QThread):
    """실제 LLM 호출 등의 긴 작업을 수행하는 워커 스레드"""
    
    # 작업 완료 시 메인 스레드로 결과를 전달하는 시그널
    finished_signal = pyqtSignal(str) 

    def __init__(self, question):
        super().__init__()
        self.question = question

    def run(self):
        # 실제 LLM API 호출 대신 긴 지연 시간을 시뮬레이션
        print(f"[{QThread.currentThreadId()}] LLM 작업 시작: {self.question}")
        
        # LLM 호출 시간 (예: 5초)
        time.sleep(5) 
        
        # 가상의 LLM 답변
        if "날씨" in self.question:
            response = "오늘의 날씨는 맑고 따뜻하며, 구름 한 점 없는 완벽한 날씨입니다."
        else:
            response = "LLM의 답변이 성공적으로 돌아왔습니다. 백그라운드 스레드에서 UI를 멈추지 않고 작업을 완료했습니다."
        
        print(f"[{QThread.currentThreadId()}] LLM 작업 완료.")
        
        # 결과를 메인 스레드에 보냄
        self.finished_signal.emit(response)

# ----------------------------------------------------
# 2. 대기 창 (QProgressDialog/QDialog)
# ----------------------------------------------------

class WaitingDialog(QProgressDialog):
    def __init__(self, parent=None):
        # QProgressDialog 생성 시 안내 문구(CancelButtonText 자리)를 사용하여 메시지를 표시합니다.
        # 내부적으로 이 텍스트를 QLabel에 설정합니다.
        super().__init__("LLM이 답변을 생성하는 중입니다. 잠시만 기다려주세요...", 
                         None, # 취소 버튼 텍스트 (None으로 설정하여 버튼 제거)
                         0, 0, 
                         parent)
        
        self.setWindowTitle("잠시 기다려 주세요")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumDuration(0) 
        
        # 🌟 QProgressDialog는 setLabelText() 메서드를 통해 안내 문구를 설정합니다.
        #    생성 시 이미 텍스트가 설정되었으므로, 추가적인 insertWidget()이 필요 없습니다.
        
        # self.setLabelText("LLM이 답변을 생성하는 중입니다. 잠시만 기다려주세요...")
        
        self.resize(350, 100)

# ----------------------------------------------------
# 3. 메인 창
# ----------------------------------------------------

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLM QProgressBar 대기 예제")
        self.setGeometry(100, 100, 600, 400)

        self.worker = None # WorkerThread 객체를 저장할 변수

        # UI 요소
        self.question_input = QTextEdit("오늘의 날씨는 어떤가요?")
        self.question_button = QPushButton("LLM에게 질문하기 (작업 시작)")
        self.answer_output = QTextEdit("여기에 LLM 답변이 출력됩니다.")
        self.answer_output.setReadOnly(True)

        # 레이아웃 설정
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("질문:"))
        layout.addWidget(self.question_input)
        layout.addWidget(self.question_button)
        layout.addWidget(QLabel("답변:"))
        layout.addWidget(self.answer_output)
        
        # 시그널 연결
        self.question_button.clicked.connect(self.start_llm_query)

    def start_llm_query(self):
        """LLM 작업 시작: 대기 창을 띄우고 워커 스레드를 실행"""
        
        if self.worker and self.worker.isRunning():
            print("이전 작업이 아직 실행 중입니다.")
            return

        question = self.question_input.toPlainText()
        self.answer_output.setText("LLM 답변을 기다리는 중...")
        self.question_button.setEnabled(False) # 버튼 비활성화

        # 1. 대기 창 생성 및 실행
        self.waiting_dialog = WaitingDialog(self)
        
        # 2. 워커 스레드 생성 및 시작
        self.worker = WorkerThread(question)
        
        # 작업 완료 시그널을 처리 함수에 연결
        self.worker.finished_signal.connect(self.handle_llm_response)
        
        # 스레드가 종료될 때 worker 객체를 삭제하도록 연결 (메모리 정리)
        self.worker.finished.connect(self.worker.deleteLater) 
        
        self.worker.start()

        # 3. 대기 창을 모달로 실행 (작업이 끝날 때까지 여기서 대기)
        #    Note: exec()는 워커 스레드가 백그라운드에서 돌아가는 동안 UI를 차단하지 않습니다.
        self.waiting_dialog.exec_()
        
    def handle_llm_response(self, response):
        """워커 스레드로부터 답변을 받아 처리"""
        
        # 1. 대기 창 닫기
        #    워커 스레드 작업이 완료되면 대기 창을 닫습니다.
        if hasattr(self, 'waiting_dialog') and self.waiting_dialog.isVisible():
            self.waiting_dialog.accept() # QProgressDialog를 닫습니다.

        # 2. 결과 출력 및 UI 복원
        self.answer_output.setText(response)
        self.question_button.setEnabled(True)
        self.worker = None # 작업 완료 후 워커 객체 참조 해제

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())