import sys
import asyncio
import os # API 키를 환경 변수에서 로드하기 위해

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel
)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot


# LangChain 관련 임포트
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. LLM 응답을 시뮬레이션하는 비동기 함수 (실제 LangChain 연동으로 대체)
# async def mock_llm_response_astream(text_to_stream):
#     """
#     LLM의 astream 응답을 모방하는 비동기 제너레이터입니다.
#     각 문자마다 작은 지연을 줍니다.
#     """
#     for char in text_to_stream:
#         yield char
#         await asyncio.sleep(0.05) # 0.05초 지연

# 2. LLM 응답 스트리밍을 처리할 스레드 클래스
class LLMStreamThread(QThread):
    text_chunk_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str) # 오류 시그널 추가

    def __init__(self, prompt_text, parent=None):
        super().__init__(parent)
        self.prompt_text = prompt_text
        self._running = True
        # LangChain 모델 초기화 (API 키는 환경 변수에 설정되어 있어야 합니다)
        # 예: os.environ["OPENAI_API_KEY"] = "YOUR_API_KEY"
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key="apikey 입력") # 원하는 모델로 변경 가능

        # LangChain 체인 설정
        self.prompt = ChatPromptTemplate.from_template("{question}")
        self.output_parser = StrOutputParser()
        self.chain = self.prompt | self.llm | self.output_parser


    def run(self):
        """
        비동기 코드를 실행하고 시그널을 통해 UI를 업데이트합니다.
        QThread 내에서 asyncio 이벤트 루프를 실행하기 위해 새로운 루프를 생성합니다.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._stream_text())

    async def _stream_text(self):
        """
        LangChain을 사용하여 LLM 응답을 비동기적으로 스트리밍하고 텍스트 조각을 방출합니다.
        """
        try:
            # LangChain의 astream_events 또는 astream을 사용하여 스트리밍
            # astream_events는 더 상세한 이벤트를 제공하지만, 여기서는 단순 텍스트 스트리밍을 위해 astream 사용
            async for chunk in self.chain.astream({"question": self.prompt_text}):
                if not self._running:
                    break
                # LangChain astream은 일반적으로 문자열 조각을 반환합니다.
                self.text_chunk_received.emit(chunk)
                # 필요에 따라 작은 지연을 추가하여 타이핑 효과를 강조할 수 있습니다.
                await asyncio.sleep(0.05)

        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.stream_finished.emit()

    def stop(self):
        """스레드 실행을 중단합니다."""
        self._running = False
        if self.loop.is_running():
            self.loop.stop()
        self.wait()


# 3. 메인 GUI 애플리케이션 클래스 (변경 없음, LLMApp의 start_streaming 함수만 변경 필요)
class LLMApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.llm_stream_thread = None

    def initUI(self):
        self.setWindowTitle("LangChain LLM Astream & QTextEdit")
        self.setGeometry(100, 100, 600, 400)

        layout = QVBoxLayout()

        self.input_label = QLabel("질문:")
        layout.addWidget(self.input_label)

        self.input_text_edit = QTextEdit()
        self.input_text_edit.setFixedHeight(60) # 입력창 크기 조절
        self.input_text_edit.setPlaceholderText("여기에 질문을 입력하세요...")
        layout.addWidget(self.input_text_edit)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("LLM 응답이 여기에 타이핑됩니다...")
        layout.addWidget(self.text_edit)

        self.start_button = QPushButton("스트리밍 시작 (질문 전송)")
        self.start_button.clicked.connect(self.start_streaming)
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("스트리밍 중지")
        self.stop_button.clicked.connect(self.stop_streaming)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        self.status_label = QLabel("준비됨")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    @pyqtSlot()
    def start_streaming(self):
        if self.llm_stream_thread and self.llm_stream_thread.isRunning():
            return

        user_question = self.input_text_edit.toPlainText().strip()
        if not user_question:
            self.status_label.setText("질문을 입력해주세요.")
            return

        self.text_edit.clear()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("LLM 응답 스트리밍 중...")

        # LLMStreamThread에 사용자 질문 전달
        self.llm_stream_thread = LLMStreamThread(user_question)
        self.llm_stream_thread.text_chunk_received.connect(self.append_text)
        self.llm_stream_thread.stream_finished.connect(self.streaming_finished)
        self.llm_stream_thread.stream_error.connect(self.display_error) # 오류 시그널 연결
        self.llm_stream_thread.start()

    @pyqtSlot(str)
    def append_text(self, chunk):
        cursor = self.text_edit.textCursor()
        cursor.insertText(chunk)
        self.text_edit.verticalScrollBar().setValue(
            self.text_edit.verticalScrollBar().maximum()
        )

    @pyqtSlot()
    def streaming_finished(self):
        self.status_label.setText("스트리밍 완료!")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self.llm_stream_thread:
            self.llm_stream_thread.quit()
            self.llm_stream_thread.wait()
            self.llm_stream_thread = None

    @pyqtSlot(str)
    def display_error(self, message):
        self.status_label.setText(f"오류: {message}")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self.llm_stream_thread:
            self.llm_stream_thread.quit()
            self.llm_stream_thread.wait()
            self.llm_stream_thread = None

    @pyqtSlot()
    def stop_streaming(self):
        if self.llm_stream_thread and self.llm_stream_thread.isRunning():
            self.llm_stream_thread.stop()
            self.status_label.setText("스트리밍 중지됨")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def closeEvent(self, event):
        if self.llm_stream_thread and self.llm_stream_thread.isRunning():
            self.llm_stream_thread.stop()
        super().closeEvent(event)

if __name__ == '__main__':
    # !!! 중요: OpenAI API 키를 환경 변수에 설정해야 합니다. !!!
    # export OPENAI_API_KEY="YOUR_API_KEY_HERE"
    # 또는 코드에서 직접 설정 (권장하지 않음, 보안상 위험)
    # os.environ["OPENAI_API_KEY"] = "YOUR_API_KEY_HERE"

    app = QApplication(sys.argv)
    ex = LLMApp()
    ex.show()
    sys.exit(app.exec_())