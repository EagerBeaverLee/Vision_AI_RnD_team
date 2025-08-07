import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, Qt
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from langchain.memory import ChatMessageHistory
import os

# Set your OpenAI API key
# os.environ["OPENAI_API_KEY"] = "YOUR_OPENAI_API_KEY"
# Make sure to replace "YOUR_OPENAI_API_KEY" with your actual key or set it as an environment variable.

# Global store for message histories (for RunnableWithMessageHistory)
store = {}

class LangchainWorker(QObject):
    """
    A QObject that runs Langchain streaming in a separate thread.
    It emits signals to update the GUI.
    """
    new_text_chunk = pyqtSignal(str)
    stream_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, use_history: bool = False, session_id: str = None, parent=None):
        super().__init__(parent)
        self.use_history = use_history
        self.session_id = session_id
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key="apikey") # You can choose a different model
        
        prompt = ChatPromptTemplate.from_messages(
                [
                    ("placeholder", "{chat_history}"),
                    ("human", "{input}"),
                ]
            )

        self.chat_history = ChatMessageHistory()

        chain = prompt | self.llm

        if self.use_history:
            if not self.session_id:
                raise ValueError("session_id must be provided if use_history is True")
            self.runnable = RunnableWithMessageHistory(
                chain,
                lambda session_id: self.chat_history,
                input_messages_key="messages",
            )
        else:
            self.runnable = self.llm

        self._stop_flag = False # For graceful termination

    def stop(self):
        """Sets a flag to gracefully stop the streaming."""
        self._stop_flag = True

    @pyqtSlot(str)
    def do_stream(self, prompt: str):
        self._stop_flag = False
        try:
            if self.use_history:
                config = {"configurable": {"session_id": "unused"}}
                
                input_data = {"messages": [HumanMessage(content=prompt)]}

                for chunk in self.runnable.stream(
                    input_data, # <-- 수정된 부분: 다시 딕셔너리 형태로 전달
                    config=config
                ):
                    if self._stop_flag:
                        break
                    if hasattr(chunk, 'content'):
                        self.new_text_chunk.emit(chunk.content)
            else:
                # 이전과 동일
                for chunk in self.runnable.stream(prompt):
                    if self._stop_flag:
                        break
                    if hasattr(chunk, 'content'):
                        self.new_text_chunk.emit(chunk.content)

        except Exception as e:
            self.error_occurred.emit(f"An error occurred: {e}")
        finally:
            self.stream_finished.emit()


class MainWindow(QWidget):
    # Signals to start the worker threads
    start_stream_history_signal = pyqtSignal(str)
    start_stream_no_history_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_threads_and_workers()

    def init_ui(self):
        self.setWindowTitle("Langchain Streamer with PyQt5 QThread")
        self.setGeometry(100, 100, 1000, 700)

        main_layout = QVBoxLayout()

        # Input field
        self.input_label = QLabel("Enter your prompt:")
        main_layout.addWidget(self.input_label)
        self.input_text_edit = QTextEdit()
        self.input_text_edit.setFixedHeight(50)
        main_layout.addWidget(self.input_text_edit)

        # Buttons
        self.stream_button = QPushButton("Start Streaming (Both)")
        self.stream_button.clicked.connect(self.start_streaming)
        main_layout.addWidget(self.stream_button)

        # Output QTextEdit 1 (with history)
        self.output_label_history = QLabel("Output with Message History:")
        main_layout.addWidget(self.output_label_history)
        self.output_text_edit_history = QTextEdit()
        self.output_text_edit_history.setReadOnly(True)
        self.output_text_edit_history.setLineWrapMode(QTextEdit.WidgetWidth)
        main_layout.addWidget(self.output_text_edit_history)

        # Output QTextEdit 2 (no history)
        self.output_label_no_history = QLabel("Output without Message History:")
        main_layout.addWidget(self.output_label_no_history)
        self.output_text_edit_no_history = QTextEdit()
        self.output_text_edit_no_history.setReadOnly(True)
        self.output_text_edit_no_history.setLineWrapMode(QTextEdit.WidgetWidth)
        main_layout.addWidget(self.output_text_edit_no_history)

        self.setLayout(main_layout)

    def setup_threads_and_workers(self):
        # --- Thread and Worker for History Stream ---
        self.thread_history = QThread()
        self.worker_history = LangchainWorker(use_history=True, session_id="session1")
        self.worker_history.moveToThread(self.thread_history) # Move worker to its own thread

        # Connect signals:
        # 1. Main window signal to worker's slot to start streaming
        self.start_stream_history_signal.connect(self.worker_history.do_stream)
        # 2. Worker's new text signal to Main window's slot to update text edit
        self.worker_history.new_text_chunk.connect(self.append_text_history)
        # 3. Worker's finished signal to Main window's slot
        self.worker_history.stream_finished.connect(self.stream_finished_history)
        # 4. Worker's error signal to Main window's slot
        self.worker_history.error_occurred.connect(self.handle_error_history)
        # 5. Thread started signal to worker's do_stream (to ensure it runs on thread)
        #    This specific connection is removed because do_stream is explicitly called via start_stream_history_signal

        # Clean up when thread finishes (optional but good practice)
        self.thread_history.finished.connect(self.worker_history.deleteLater)
        self.thread_history.finished.connect(self.thread_history.deleteLater)
        self.thread_history.start() # Start the thread (it's now ready to accept tasks)


        # --- Thread and Worker for No History Stream ---
        self.thread_no_history = QThread()
        self.worker_no_history = LangchainWorker(use_history=False)
        self.worker_no_history.moveToThread(self.thread_no_history) # Move worker to its own thread

        # Connect signals:
        self.start_stream_no_history_signal.connect(self.worker_no_history.do_stream)
        self.worker_no_history.new_text_chunk.connect(self.append_text_no_history)
        self.worker_no_history.stream_finished.connect(self.stream_finished_no_history)
        self.worker_no_history.error_occurred.connect(self.handle_error_no_history)

        self.thread_no_history.finished.connect(self.worker_no_history.deleteLater)
        self.thread_no_history.finished.connect(self.thread_no_history.deleteLater)
        self.thread_no_history.start() # Start the thread


    def start_streaming(self):
        prompt = self.input_text_edit.toPlainText()
        if not prompt:
            self.output_text_edit_history.setText("Please enter a prompt.")
            self.output_text_edit_no_history.setText("Please enter a prompt.")
            return

        self.stream_button.setEnabled(False) # Disable button during streaming
        self.input_text_edit.setEnabled(False)
        self.output_text_edit_history.clear() # Clear before starting new stream
        self.output_text_edit_no_history.clear() # Clear before starting new stream

        # Emit signals to start streaming on respective worker threads
        self.start_stream_history_signal.emit(prompt)
        self.start_stream_no_history_signal.emit(prompt)


    @pyqtSlot(str)
    def append_text_history(self, chunk: str):
        self.output_text_edit_history.insertPlainText(chunk)
        self.output_text_edit_history.verticalScrollBar().setValue(
            self.output_text_edit_history.verticalScrollBar().maximum()
        )

    @pyqtSlot(str)
    def append_text_no_history(self, chunk: str):
        self.output_text_edit_no_history.insertPlainText(chunk)
        self.output_text_edit_no_history.verticalScrollBar().setValue(
            self.output_text_edit_no_history.verticalScrollBar().maximum()
        )

    @pyqtSlot()
    def stream_finished_history(self):
        print("History stream finished.")
        self.check_all_streams_finished()

    @pyqtSlot()
    def stream_finished_no_history(self):
        print("No history stream finished.")
        self.check_all_streams_finished()

    def check_all_streams_finished(self):
        # A simple way to re-enable the button.
        # For a more robust solution, you might use counters for active streams.
        # Here, we just re-enable assuming both might finish around the same time
        # or that a single finish means it's safe to interact again.
        # If you need strict synchronization, use two flags or a counter.
        self.stream_button.setEnabled(True)
        self.input_text_edit.setEnabled(True)

    @pyqtSlot(str)
    def handle_error_history(self, error_message: str):
        self.output_text_edit_history.setText(f"Error: {error_message}")
        self.stream_finished_history() # Ensure UI re-enables on error

    @pyqtSlot(str)
    def handle_error_no_history(self, error_message: str):
        self.output_text_edit_no_history.setText(f"Error: {error_message}")
        self.stream_finished_no_history() # Ensure UI re-enables on error

    def closeEvent(self, event):
        # Terminate threads gracefully when the main window closes
        print("Stopping threads...")
        self.worker_history.stop()
        self.worker_no_history.stop()

        self.thread_history.quit()
        self.thread_no_history.quit()

        self.thread_history.wait()
        self.thread_no_history.wait()
        print("Threads stopped.")
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())