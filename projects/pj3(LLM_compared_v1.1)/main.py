import sys, asyncio
from PyQt5.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QMessageBox, QTextEdit
)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QMetaObject, Q_ARG, Qt
from PyQt5.QtGui import QTextCursor

from mainwindow import Ui_MainWindow

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import AIMessageChunk
from langchain_community.chat_message_histories import ChatMessageHistory

class LLMStreamThread(QThread):
    text_chunk_received = pyqtSignal(str, bool)
    stream_finished = pyqtSignal(bool)
    stream_error = pyqtSignal(str, bool)
    
    def __init__(self, msg, is_history_flag, ApiKey, Temp, Prompt, history, parent=None):
        super().__init__(parent)
        self.input_msg = msg
        self._running = True 
        self.is_history_flag = is_history_flag
        self.m_apikey = ApiKey
        self.m_temperature = Temp
        self.m_prompt = Prompt
        self.chat_history = history

        self._loop = None # 스레드 내부의 asyncio 루프 인스턴스
        self._current_task = None # 현재 실행 중인 asyncio 태스크
        self._termination_event = None # 루프 종료 신호를 위한 이벤트 (run() 내부에서 초기화)

    def run(self):
        # 🌟 QThread가 시작될 때 asyncio 이벤트 루프를 생성하고 설정합니다. 🌟
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._termination_event = asyncio.Event() # 루프 생성 후 이벤트 초기화
        print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: asyncio 이벤트 루프 생성 및 설정 완료.")
                                
        try:
            if self.is_history_flag:
                self._current_task = self._loop.create_task(self._stream_text_history())
            else:
                self._current_task = self._loop.create_task(self._stream_text())
            
            # 🌟 변경된 루프 실행 로직: 태스크가 완료되거나 종료 이벤트가 설정될 때까지 루프를 실행 🌟
            # 즉, _current_task와 _termination_event.wait() 두 코루틴 중 하나라도 완료될 때까지 대기
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: asyncio.wait 시작.")
            done, pending = self._loop.run_until_complete(
                asyncio.wait([self._current_task, self._termination_event.wait()],
                             return_when=asyncio.FIRST_COMPLETED)
            )
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: asyncio.wait 완료. Done: {len(done)}, Pending: {len(pending)}")

            # 만약 _current_task가 아직 완료되지 않았다면 취소 (예: _termination_event가 먼저 설정된 경우)
            if not self._current_task.done():
                print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] _current_task가 아직 완료되지 않아 취소합니다.")
                self._current_task.cancel()
                try:
                    self._loop.run_until_complete(self._current_task) # 취소된 태스크가 완료될 때까지 기다림
                except asyncio.CancelledError:
                    print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 취소된 _current_task가 성공적으로 종료되었습니다.")
                except Exception as e:
                    print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 취소된 _current_task 종료 중 예외 발생: {e}")

        except asyncio.CancelledError:
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: run() 메서드 최상위에서 CancelledError 처리됨.")
        except Exception as e:
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: run() 최상위 오류: {e}")
            self.stream_error.emit(f"스레드 실행 중 오류: {e}", self.is_history_flag)
        finally:
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: finally 블록 진입 - 루프 정리 시작.")
            
            # 루프가 None이 아니고 아직 닫히지 않았다면 정리 시도
            if self._loop and not self._loop.is_closed():
                # 현재 루프의 모든 태스크를 가져옵니다.
                pending_tasks = [task for task in asyncio.all_tasks(self._loop) if not task.done()]
                
                if pending_tasks:
                    print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: 남은 태스크 ({len(pending_tasks)}개) 취소 및 정리 중...")
                    for task in list(pending_tasks):
                        if not task.done():
                            task.cancel()
                    
                    try:
                        # 취소된 태스크들이 완료될 때까지 기다림
                        # Timeout을 설정하여 무한정 기다리지 않도록 합니다.
                        self._loop.run_until_complete(
                            asyncio.wait_for(
                                asyncio.gather(*pending_tasks, return_exceptions=True),
                                timeout=2 # 최대 2초 대기
                            )
                        )
                        print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 남은 태스크 정리 완료.")
                    except asyncio.TimeoutError:
                        print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 경고: 남은 태스크 정리 중 타임아웃 발생. 일부 태스크가 정리되지 않았을 수 있습니다.")
                    except Exception as e:
                        print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 남은 태스크 정리 중 예상치 못한 예외 발생: {e}")

                # 루프가 실행 중이었다면 안전하게 중지
                if self._loop.is_running():
                    print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 루프가 아직 실행 중이어서 stop() 호출.")
                    self._loop.stop()
            
            # 루프 닫기
            if self._loop and not self._loop.is_closed():
                if any(not task.done() for task in asyncio.all_tasks(self._loop)):
                    print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 경고: 루프 닫기 전 아직 완료되지 않은 태스크가 남아있습니다.")
                self._loop.close()
                print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: 이벤트 루프 닫힘.")
            else:
                print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 내부: 이벤트 루프가 없거나 이미 닫힘.")

            self.stream_finished.emit(self.is_history_flag)

    async def _stream_text(self):
        print(f"[{'NON-HISTORY'}] _stream_text 코루틴 시작.")
        try:
            chat_model = ChatOpenAI(
                api_key=self.m_apikey,
                temperature=self.m_temperature,
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.m_prompt),
                    ("human", "{input}"),
                ]
            )
            chain = prompt | chat_model

            async for chunk in chain.astream({"input": self.input_msg}):
                if not self._running:
                    print(f"[{'NON-HISTORY'}] _stream_text: _running 플래그 False, 스트리밍 중단 요청.")
                    raise asyncio.CancelledError # 취소 신호 발생시켜 루프 즉시 종료 유도

                text_to_emit = ""
                if isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        text_to_emit = chunk.content
                elif isinstance(chunk, str):
                    text_to_emit = chunk
                else:
                    print(f"경고: 예상치 못한 chunk 타입: {type(chunk)}, 내용: {chunk}")
                    text_to_emit = str(chunk)

                if text_to_emit:
                    self.text_chunk_received.emit(text_to_emit, self.is_history_flag)
                
                await asyncio.sleep(0.05) # 0.05초 딜레이 유지

            print(f"[{'NON-HISTORY'}] _stream_text: astream 루프 정상 종료.")

        except asyncio.CancelledError:
            print(f"[{'NON-HISTORY'}] _stream_text 작업이 취소되었습니다.")
            raise
        except Exception as e:
            print(f"[{'NON-HISTORY'}] 스트리밍 중 오류 발생 (_stream_text): {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}", self.is_history_flag)
        finally:
            print(f"[{'NON-HISTORY'}] _stream_text 코루틴 finally 블록 진입.")
            # 코루틴이 완료되면, run() 메서드의 asyncio.wait()를 깨우기 위해 _termination_event를 설정합니다.
            if self._termination_event and not self._termination_event.is_set():
                print(f"[{'NON-HISTORY'}] _stream_text: _termination_event 설정 요청.")
                self._termination_event.set()
            print(f"[{'NON-HISTORY'}] _stream_text 코루틴 최종 종료.")

    async def _stream_text_history(self):
        print(f"[{'HISTORY'}] _stream_text_history 코루틴 시작.")
        try:
            chat_model = ChatOpenAI(
                api_key=self.m_apikey,
                temperature=self.m_temperature,
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.m_prompt),
                    ("placeholder", "{chat_history}"),
                    ("human", "{input}"),
                ]
            )
            output_parser = StrOutputParser()
            chain = prompt | chat_model | output_parser

            chain_history = RunnableWithMessageHistory(
                chain,
                lambda session_id: self.chat_history, 
                input_messages_key="input",
                history_messages_key="chat_history",
            )

            async for chunk in chain_history.astream({"input": self.input_msg}, {"configurable": {"session_id": "unused"}},):
                if not self._running:
                    print(f"[{'HISTORY'}] _stream_text_history: _running 플래그 False, 스트리밍 중단 요청.")
                    raise asyncio.CancelledError

                text_to_emit = ""
                if isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        text_to_emit = chunk.content
                elif isinstance(chunk, str):
                    text_to_emit = chunk
                else:
                    print(f"경고: 예상치 못한 chunk 타입: {type(chunk)}, 내용: {chunk}")
                    text_to_emit = str(chunk)

                if text_to_emit:
                    self.text_chunk_received.emit(text_to_emit, self.is_history_flag)
                
                await asyncio.sleep(0.05) # 0.05초 딜레이 유지
            print(f"[{'HISTORY'}] _stream_text_history: astream 루프 정상 종료.")

        except asyncio.CancelledError:
            print(f"[{'HISTORY'}] _stream_text_history 작업이 취소되었습니다.")
            raise
        except Exception as e:
            print(f"[{'HISTORY'}] 스트리밍 중 오류 발생 (_stream_text_history): {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}", self.is_history_flag)
        finally:
            print(f"[{'HISTORY'}] _stream_text_history 코루틴 finally 블록 진입.")
            if self._termination_event and not self._termination_event.is_set():
                print(f"[{'HISTORY'}] _stream_text_history: _termination_event 설정 요청.")
                self._termination_event.set()
            print(f"[{'HISTORY'}] _stream_text_history 코루틴 최종 종료.")
    
    def stop(self):
        self._running = False
        # _current_task가 존재하고 아직 완료되지 않았다면 취소 요청
        if self._loop and self._current_task and not self._current_task.done():
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 외부: 비동기 태스크 취소 요청 (QMetaObject.invokeMethod).")
            QMetaObject.invokeMethod(self._loop, 'call_soon_threadsafe', Qt.QueuedConnection,
                                     Q_ARG(object, self._current_task.cancel))
        
        # 🌟 종료 이벤트 설정 🌟
        if self._loop and self._termination_event and not self._termination_event.is_set():
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 외부: _termination_event 설정 요청 (QMetaObject.invokeMethod).")
            # set_termination_event 슬롯을 직접 호출하는 대신,
            # call_soon_threadsafe를 통해 이벤트 설정을 해당 asyncio 루프 스레드로 넘깁니다.
            self._loop.call_soon_threadsafe(self._termination_event.set)
        else:
            print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] 스레드 외부: 비동기 태스크가 없거나 이미 완료됨, 또는 루프/이벤트가 없음/설정됨.")

    # set_termination_event 슬롯은 이제 필요 없어졌습니다. stop() 메서드에서 직접 _loop.call_soon_threadsafe를 사용하기 때문입니다.
    # @pyqtSlot()
    # def set_termination_event(self):
    #     if self._loop and self._termination_event and not self._termination_event.is_set():
    #         self._loop.call_soon_threadsafe(self._termination_event.set)
    #         print(f"[{'HISTORY' if self.is_history_flag else 'NON-HISTORY'}] set_termination_event 슬롯: _termination_event 설정 완료.")


class Window(QMainWindow, Ui_MainWindow):
    completed_threads = 0 
    total_threads_to_run = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.connectSignalsSlots()

        self.m_api_key = None
        self.m_temperature = None
        self.m_prompt = None
        self.chat_history = ChatMessageHistory() 

        self.llm_thread = None
        self.llm_history_thread = None


    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.start_streaming)
        self.ui.apply_btn.clicked.connect(self.apply_setting)
        
    def start_streaming(self):
        if (self.llm_thread and self.llm_thread.isRunning()):
            QMessageBox.information(self, "진행 중", "비히스토리 LLM 스트리밍이 진행 중입니다. 잠시 기다려주세요.")
            return
        if (self.llm_history_thread and self.llm_history_thread.isRunning()):
            QMessageBox.information(self, "진행 중", "히스토리 LLM 스트리밍이 진행 중입니다. 잠시 기다려주세요.")
            return

        input_msg = self.ui.input_text.toPlainText().strip()
        if not input_msg:
            QMessageBox.critical(self, "입력 오류", "메시지를 입력하세요")
            return

        self.ui.send_btn.setEnabled(False) 
        Window.completed_threads = 0 
        Window.total_threads_to_run = 2 

        # Non-history thread
        self.ui.non_history_txt.append(f"Sended Message: {input_msg}")
        self.ui.non_history_txt.append("")
        self.ui.non_history_txt.append("Ai Messages: ")
        # 🌟 parent=self 추가 🌟
        self.llm_thread = LLMStreamThread(input_msg, False, self.m_api_key, self.m_temperature, self.m_prompt, self.chat_history, parent=self)
        self.llm_thread.text_chunk_received.connect(self.append_text)
        self.llm_thread.stream_finished.connect(self.streaming_finished) 
        self.llm_thread.stream_error.connect(self.display_error)
        self.llm_thread.start()

        # History thread
        self.ui.history_txt.append(f"Sended Message: {input_msg}")
        self.ui.history_txt.append("")
        self.ui.history_txt.append("Ai Messages: ")
        # 🌟 parent=self 추가 🌟
        self.llm_history_thread = LLMStreamThread(input_msg, True, self.m_api_key, self.m_temperature, self.m_prompt, self.chat_history, parent=self)
        self.llm_history_thread.text_chunk_received.connect(self.append_text)
        self.llm_history_thread.stream_finished.connect(self.streaming_finished) 
        self.llm_history_thread.stream_error.connect(self.display_error)
        self.llm_history_thread.start()

        self.ui.input_text.clear()

    @pyqtSlot(str, bool)
    def append_text(self, chunk, flag):
        target_text_edit = self.ui.history_txt if flag else self.ui.non_history_txt
        cursor = target_text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        target_text_edit.setTextCursor(cursor)
        cursor.insertText(chunk)
        target_text_edit.verticalScrollBar().setValue(
            target_text_edit.verticalScrollBar().maximum()
        )

    @pyqtSlot(bool)
    def streaming_finished(self, is_history_flag):
        # 🌟 스레드 객체 참조를 바로 None으로 만들지 않습니다.
        # closeEvent나 다른 명시적인 정리 시점까지 유지합니다.
        if is_history_flag:
            self.ui.history_txt.append("")
        else:
            self.ui.non_history_txt.append("")
        
        Window.completed_threads += 1
        if Window.completed_threads == Window.total_threads_to_run:
            self.ui.send_btn.setEnabled(True) 
            print("All streaming threads finished.")

    @pyqtSlot(str, bool)
    def display_error(self, message, flag):
        QMessageBox.critical(self, "실행 오류", f"{'오른쪽' if flag else '왼쪽'} 메세지창 실행 중 오류 발생: {message}")
        self.ui.send_btn.setEnabled(True) 

        # 오류 발생 시 해당 스레드 정리 요청
        if flag:
            if self.llm_history_thread:
                self.llm_history_thread.stop()
                # self.llm_history_thread = None # 여기서 바로 None으로 만들지 않음
        else:
            if self.llm_thread:
                self.llm_thread.stop()
                # self.llm_thread = None # 여기서 바로 None으로 만들지 않음
        
        Window.completed_threads += 1 
        if Window.completed_threads == Window.total_threads_to_run:
            self.ui.send_btn.setEnabled(True)


    def closeEvent(self, event):
        # 애플리케이션 종료 시 스레드에 종료 요청 및 대기
        if self.llm_thread and self.llm_thread.isRunning():
            print(f"Window closeEvent: Stopping non-history thread...")
            self.llm_thread.stop()
            self.llm_thread.wait(3000) # 충분한 시간 대기
            if self.llm_thread.isRunning():
                print(f"Window closeEvent: Non-history thread did not stop gracefully.")
            self.llm_thread = None # 스레드가 완전히 종료된 후 참조 해제
            
        if self.llm_history_thread and self.llm_history_thread.isRunning():
            print(f"Window closeEvent: Stopping history thread...")
            self.llm_history_thread.stop()
            self.llm_history_thread.wait(3000) # 충분한 시간 대기
            if self.llm_history_thread.isRunning():
                print(f"Window closeEvent: History thread did not stop gracefully.")
            self.llm_history_thread = None # 스레드가 완전히 종료된 후 참조 해제
            
        super().closeEvent(event)

    def apply_setting(self):
        self.m_api_key = self.ui.api_key_txt.toPlainText().strip()
        self.m_prompt = self.ui.prompt_txt.toPlainText().strip()
        try:
            self.m_temperature = float(self.ui.temp_combo.currentText()) 
            QMessageBox.information(self, "설정 완료", "LLM 모델 설정이 완료되었습니다.")
        except ValueError:
            QMessageBox.critical(self, "설정 오류", "Temperature 값을 올바른 숫자로 입력해주세요.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    win = Window()
    win.show()

    sys.exit(app.exec_())