import sys, asyncio

from PyQt5.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QMessageBox, QTextEdit
)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QTextCursor

from mainwindow import Ui_MainWindow
from setting import Settting_Dialog

from langchain_openai import OpenAI, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import AIMessageChunk
from langchain_community.chat_message_histories import ChatMessageHistory

class LLMStreamThread(QThread):
    text_chunk_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str)
    
    def __init__(self, msg, flag, ApiKey, Temp, Prompt, history, parent=None):
        super().__init__(parent)
        self.input_msg = msg
        self._running = True    #쓰레드가 이미 실행중인지 확인 여부

        self.m_flag = flag
        self.m_apikey = ApiKey
        self.m_temperature = Temp
        self.m_prompt = Prompt
        self.chat_histroy = history

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._stream_text_history())
        
    async def _stream_text_history(self):
        try:
            chat_model = ChatOpenAI(
                api_key=self.m_apikey,
                temperature=self.m_temperature,
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        self.m_prompt
                    ),
                    ("placeholder", "{chat_history}"),
                    ("human", "{input}"),
                ]
            )
            output_parser = StrOutputParser()
            chain = prompt | chat_model | output_parser

            chain_history = RunnableWithMessageHistory(
                chain,
                lambda session_id: self.chat_histroy,
                input_messages_key="input",
                history_messages_key="chat_history",
            )

            async for chunk in chain_history.astream({"input": self.input_msg}, {"configurable": {"session_id": "unused"}},):
                if not self._running:
                    break

                text_to_emit = ""
                if isinstance(chunk, AIMessageChunk):
                    # AIMessageChunk라면 .content 속성에서 문자열 추출
                    if chunk.content: # content가 비어있지 않은 경우에만 추출
                        text_to_emit = chunk.content
                elif isinstance(chunk, str):
                    # 이미 문자열인 경우 그대로 사용
                    text_to_emit = chunk
                else:
                    # 예상치 못한 다른 타입의 chunk가 오는 경우 (디버깅용)
                    print(f"경고: 예상치 못한 chunk 타입: {type(chunk)}, 내용: {chunk}")
                    text_to_emit = str(chunk) # 일단 문자열로 변환 시도

                if text_to_emit: # 추출된 텍스트가 비어있지 않으면 시그널 방출
                    self.text_chunk_received.emit(text_to_emit)
                    await asyncio.sleep(0.04)
            
        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.stream_finished.emit()

    def stop(self):
        self._running = False
        if self.loop.is_running():
            self.loop.stop()
        self.wait()

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.connectSignalsSlots()

        self.m_api_key = None
        self.m_temperature = None
        self.m_prompt = None
        self.chat_history = ChatMessageHistory() #챗히스토리 관리

        self.llm_stream_thread = None

    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.start_streaming)
        self.ui.setting_btn.clicked.connect(self._open_settings)
        
    
    def start_streaming(self):
        if self.llm_stream_thread and self.llm_stream_thread.isRunning():
            return
        input_msg = self.ui.input_text.toPlainText().strip()
        if not input_msg:
            QMessageBox.critical(self, "입력 오류", "메세지를 입력하세요")
            return

        self.ui.send_btn.setEnabled(False)
        self.ui.input_text.clear()
        self.ui.output_text.append(f"Sended Message: {input_msg}")
        self.ui.output_text.append("")
        self.ui.output_text.append("Ai Messages: ")

        self.llm_stream_thread = LLMStreamThread(input_msg, True, self.m_api_key, self.m_temperature, self.m_prompt, self.chat_history)
        self.llm_stream_thread.text_chunk_received.connect(self.append_text)
        self.llm_stream_thread.stream_finished.connect(self.streaming_finished)
        self.llm_stream_thread.stream_error.connect(self.display_error)
        self.llm_stream_thread.start()

    @pyqtSlot(str)
    def append_text(self, chunk):
        cursor = self.ui.output_text.textCursor()
        cursor.movePosition(QTextCursor.End)    #중간에 답변 생성 방지
        self.ui.output_text.setTextCursor(cursor)
        cursor.insertText(chunk)
        self.ui.output_text.verticalScrollBar().setValue(
            self.ui.output_text.verticalScrollBar().maximum()
        )

    @pyqtSlot()
    def streaming_finished(self):
        # QMessageBox.about(self,"성공", "출력이 끝났습니다")
        self.ui.send_btn.setEnabled(True)
        self.ui.output_text.append("")
        if self.llm_stream_thread:
            self.llm_stream_thread.quit()
            self.llm_stream_thread.wait()
            self.llm_stream_thread = None

    @pyqtSlot(str)
    def display_error(self, message):
        QMessageBox.critical(self, "실행 오류", f"실행 중 오류 발생: {message}")
        self.ui.send_btn.setEnabled(True)
        if self.llm_stream_thread:
            self.llm_stream_thread.quit()
            self.llm_stream_thread.wait()
            self.llm_stream_thread = None

    def closeEvent(self, event):
        if self.llm_stream_thread and self.llm_stream_thread.isRunning():
            self.llm_stream_thread.stop()
        super().closeEvent(event)

    def _open_settings(self):
        setting_dialog = Settting_Dialog(self)
        setting_dialog.set_values.connect(self._apply_setting)
        setting_dialog.set_api_key(self.m_api_key)
        setting_dialog.set_temperature(self.m_temperature)
        setting_dialog.set_prompt(self.m_prompt)
        setting_dialog.exec()
           
    def _apply_setting(self, load_api_key, load_temp, load_prompt):
        self.m_api_key = load_api_key
        self.m_temperature = load_temp
        self.m_prompt = load_prompt
    
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


