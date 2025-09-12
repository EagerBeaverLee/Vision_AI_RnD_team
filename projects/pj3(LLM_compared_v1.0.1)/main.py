import sys, os, time, copy
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QMessageBox, QTableWidgetItem, QSizePolicy, QMenu, QAction, QFileDialog
)
from PyQt5.QtCore import Qt, QCoreApplication, QTimer, QObject, QPoint, pyqtSignal, QThread
from PyQt5.QtGui import QDoubleValidator
from PyQt5.uic import loadUi

from mainwindow import Ui_MainWindow

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader, DirectoryLoader
from langchain_teddynote.document_loaders import HWPLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_core.output_parsers import StrOutputParser

class EmbeddingWorder(QObject):
    finished = pyqtSignal()
    progresses = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, folder_path, api_key, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.embedding_model = OpenAIEmbeddings(api_key=api_key)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
        self.vector_db = None

    def get_loader(self, filename):
        loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader,
            'csv': CSVLoader,
            'json': JSONLoader,
            'hwp': HWPLoader
        }

        _, file_extension = os.path.splitext(filename)
        file_extension = file_extension.lstrip('.')

        loader_class = loader_classes.get(file_extension)

        if not loader_class:
            raise ValueError(f"No loader available for file extension '{file_extension}'")
        
        # JSON 파일인 경우 jq_schema 인자를 추가하여 반환
        if file_extension == 'json':
            return loader_class(filename, jq_schema='.', text_content=False)
        else:
            # 그 외의 경우 일반적인 방식으로 로더 반환
            return loader_class(filename)
        
    def run(self):
        try:
            files = os.listdir(self.folder_path)
            total_files = len(files)
            save_vector = "./faiss_index_kr"

            if total_files == 0:
                self.error.emit("선택한 폴더에 파일이 없습니다.")
                self.finished.emit()
                return
            
            progress_step = 100 / total_files

            # all_chunks = []
            for i, file_name in enumerate(files):
                file_path = os.path.join(self.folder_path, file_name)
                try:
                    loader = self.get_loader(file_path)
                    chunks = self.text_splitter.split_documents(loader.load())
                    # all_chunks.extend(chunks)
                    # if self.vector_db:
                    #     self.vector_db.add_documents(chunks)
                    # else:
                    #     self.vector_db = FAISS.from_documents(chunks, self.embedding_model)
                    
                    curr_progress = (i + 1) * progress_step
                    self.progresses.emit(int(curr_progress))
                except Exception as e:
                    self.error.emit(f"{file_name} 파일 임베딩 중 오류 발생: {e}")

            # self.vector_db.save_local(save_vector)
            # print("FAISS 벡터스토어 생성 및 저장 완료")

            self.vector_db = FAISS.load_local(save_vector, self.embedding_model, allow_dangerous_deserialization=True)
            print("FAISS 벡터스토어 로드 완료")

            self.progresses.emit(100)
            self.finished.emit()

        except Exception as e:
            self.error.emit(f"임베딩 작업 중 치명적인 오류 발생: {e}")
            self.finished.emit()

class ChatRoom:
    def __init__(self, name):
        self.name = name
        self.m_api_key = None
        self.m_temperature = "0.00"
        self.m_prompt = ""

        self.default_chat_log = ""
        self.experiment_chat_log = ""
        self.user_in_txt = ""

        self.chat_histroy = ChatMessageHistory() #챗히스토리 관리

class Slider_Animation(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.animation_timer = QTimer(parent)
        self.step = 0
        self.total_steps = 10   #(0.1초)
        self.stored_panel_size = 0
        self.is_collapsed = False

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        validator = QDoubleValidator()
        validator.setRange(0.00, 1.00)
        validator.setDecimals(2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.ui.temp_val.setValidator(validator)

        self.connectSignalsSlots()

        self.chat_rooms = []    #채팅방 관리
        self.current_chat_room = None
        self.add_new_chat_room(initial=True)

        # 오른쪽 클릭된 아이템을 저장할 멤버 변수
        self.clicked_item = None

        self.chat_room_update_flag = False

        self.left_animation = Slider_Animation(self)
        self.left_animation.animation_timer.timeout.connect(self.update_left_animation)

        self.right_animation = Slider_Animation(self)
        self.right_animation.animation_timer.timeout.connect(self.update_right_animation)

        self.ui.chat_room_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.chat_room_table.customContextMenuRequested.connect(self.on_context_menu)

        self.ui.splitter.setSizes([174, 758, 227])

        self.threading = None
        self.text_splitter = None

    def load_folder(self):
        if not self.current_chat_room.m_api_key:
            QMessageBox.critical(self, "오류", "api key를 입력해주세요")
            return
        
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        
        if path:
            self.ui.path.setText(f"{path}")

            self.ui.Loading_bar.setValue(0)
            self.ui.Load_btn.setEnabled(False) #작업 중 버튼 비활성화

            self.threading = QThread()
            self.worker = EmbeddingWorder(
                folder_path=path,
                api_key=self.current_chat_room.m_api_key
            )

            self.worker.moveToThread(self.threading)

            self.threading.started.connect(self.worker.run)
            self.worker.progresses.connect(self.ui.Loading_bar.setValue)
            self.worker.finished.connect(self.threading.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.finished.connect(self.threading.deleteLater)

            self.worker.finished.connect(lambda: self.ui.Load_btn.setEnabled(True))
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "오류", msg))
            self.worker.finished.connect(lambda: QMessageBox.information(self, "완료", "임베딩이 완료되었습니다"))

            self.threading.start()

    def on_context_menu(self, point: QPoint):
        self.clicked_item = self.ui.chat_room_table.itemAt(point)

        if self.clicked_item is None: 
            return
        
        menu = QMenu(self)

        action_add = QAction("Add Chat", self)
        action_rename = QAction("Rename Chat", self)
        action_delete = QAction("Delete Chat", self)
        action_duplicate = QAction("Duplicated Chat", self)
        
        action_add.triggered.connect(self.add_new_chat_room)
        action_rename.triggered.connect(self.rename_chat)
        action_duplicate.triggered.connect(self.duplicate_chat)
        action_delete.triggered.connect(self.delete_selected_chat_room)

        menu.addAction(action_add)
        menu.addAction(action_rename)
        menu.addAction(action_duplicate)
        menu.addSeparator()
        menu.addAction(action_delete)

        menu.exec_(self.ui.chat_room_table.mapToGlobal(point))

    def rename_chat(self):
        if self.clicked_item:
            self.ui.chat_room_table.editItem(self.clicked_item)

    def duplicate_chat(self):
        self.stored_ui_information()
        selected_row = self.ui.chat_room_table.selectedItems()
        if selected_row:
            index = selected_row[0].row()
            room = self.chat_rooms[index]
            duplicate_room = copy.copy(room)
            duplicate_room.name += "(copy)"
            self.chat_rooms.append(duplicate_room)
            self.update_chat_room_list()

    def toggle_left_animation(self):
        cur_sizes = self.ui.splitter.sizes()
        left_panel = cur_sizes[0]
        mid_panel = cur_sizes[1]
        right_panel = cur_sizes[2]

        if self.left_animation.animation_timer.isActive():
            return
        
        if self.left_animation.is_collapsed:
            self.start_sizes = [left_panel, mid_panel, right_panel]
            self.end_sizes = [self.left_animation.stored_panel_size, mid_panel - self.left_animation.stored_panel_size, right_panel]
            self.left_animation.stored_panel_size = 0
            self.ui.left_split_btn.setText("l<")
        else:
            self.start_sizes = [left_panel, mid_panel, right_panel]
            self.end_sizes = [self.left_animation.stored_panel_size, mid_panel + self.left_animation.stored_panel_size, right_panel]
            self.left_animation.stored_panel_size = left_panel
            self.ui.left_split_btn.setText(">l")

        self.left_animation.step = 0
        self.left_animation.animation_timer.start(10)

    def update_left_animation(self):
        self.left_animation.step += 1
        if self.left_animation.step > self.left_animation.total_steps:
            self.left_animation.animation_timer.stop()
            self.left_animation.is_collapsed = not self.left_animation.is_collapsed
            return
    
        progress = self.left_animation.step / self.left_animation.total_steps
        current_sizes = [
            int(self.start_sizes[0] + (self.end_sizes[0] - self.start_sizes[0]) * progress),
            int(self.start_sizes[1] - (self.end_sizes[0] - self.start_sizes[0]) * progress),
            int(self.start_sizes[2])
        ]
        
        self.ui.splitter.setSizes(current_sizes)

    def toggle_right_animation(self):
        cur_sizes = self.ui.splitter.sizes()
        left_panel = cur_sizes[0]
        mid_panel = cur_sizes[1]
        right_panel = cur_sizes[2]

        if self.right_animation.animation_timer.isActive():
            return
        
        if self.right_animation.is_collapsed:
            self.start_sizes = [left_panel, mid_panel, right_panel]
            self.end_sizes = [left_panel, mid_panel - self.right_animation.stored_panel_size, self.right_animation.stored_panel_size]
            self.right_animation.stored_panel_size = 0
            self.ui.right_split_btn.setText(">l")
        else:
            self.start_sizes = [left_panel, mid_panel, right_panel]
            self.end_sizes = [left_panel, mid_panel + self.right_animation.stored_panel_size, self.right_animation.stored_panel_size]
            self.right_animation.stored_panel_size = right_panel
            self.ui.right_split_btn.setText("l<")

        self.right_animation.step = 0
        self.right_animation.animation_timer.start(10)

    def update_right_animation(self):
        self.right_animation.step += 1
        if self.right_animation.step > self.right_animation.total_steps:
            self.right_animation.animation_timer.stop()
            self.right_animation.is_collapsed = not self.right_animation.is_collapsed
            return
    
        progress = self.right_animation.step / self.right_animation.total_steps
        current_sizes = [
            int(self.start_sizes[0]),
            int(self.start_sizes[1] - (self.end_sizes[2] - self.start_sizes[2]) * progress),
            int(self.start_sizes[2] + (self.end_sizes[2] - self.start_sizes[2]) * progress)
        ]
        
        self.ui.splitter.setSizes(current_sizes)

    def slider_temp_value(self):
        float_val = self.ui.temp_slider.value() / 100
        if float_val == float(self.current_chat_room.m_temperature):
            return
        self.current_chat_room.m_temperature = str(float_val)
        self.sync_temp_value()

    def text_temp_value(self):
        float_val = self.ui.temp_val.text().strip()
        if float_val == self.current_chat_room.m_temperature or float_val == "":
            return
        self.current_chat_room.m_temperature = float_val
        self.sync_temp_value()

    def sync_temp_value(self):
        final_val = self.current_chat_room.m_temperature
        if self.ui.temp_slider.value() * 0.01 != float(final_val):
            self.ui.temp_slider.setValue(int(float(final_val) * 100))
        if self.ui.temp_val.text().strip() != final_val:
            self.ui.temp_val.setText(final_val)

    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.load_message)
        self.ui.api_key_txt.textChanged.connect(self.apply_api_key)
        self.ui.prompt_txt.textChanged.connect(self.apply_prompt)
        self.ui.new_chat_btn.clicked.connect(self.add_new_chat_room)
        self.ui.del_chat_btn.clicked.connect(self.delete_selected_chat_room)
        self.ui.chat_room_table.itemSelectionChanged.connect(self.load_selected_chat_room)
        self.ui.chat_room_table.itemChanged.connect(self.room_name_changed)
        self.ui.temp_slider.valueChanged.connect(self.slider_temp_value)
        self.ui.temp_val.textChanged.connect(self.text_temp_value)
        self.ui.left_split_btn.clicked.connect(self.toggle_left_animation)
        self.ui.right_split_btn.clicked.connect(self.toggle_right_animation)
        self.ui.Load_btn.clicked.connect(self.load_folder)

    def show_status_messages(self, message, is_error=False):
        if is_error:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ffcccc; color: red;}")
        else:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ccffcc; color: green;}")
        self.ui.statusbar.showMessage(message, 3000) # Show for 3 seconds

    def update_chat_room_list(self):
        self.chat_room_update_flag = True

        self.ui.chat_room_table.setRowCount(len(self.chat_rooms))
        for i, room in enumerate(self.chat_rooms):
            item = QTableWidgetItem(room.name)
            item.setData(Qt.UserRole, room) # Store the ChatRoom object in the item
            self.ui.chat_room_table.setItem(i, 0, item)
        
        # Select the current chat room in the list
        if self.current_chat_room and self.current_chat_room in self.chat_rooms:
            index = self.chat_rooms.index(self.current_chat_room)
            self.ui.chat_room_table.selectRow(index)
        elif self.chat_rooms:
            self.ui.chat_room_table.selectRow(0) # Select first if no current or current deleted

        self.chat_room_update_flag = False

    def add_new_chat_room(self, initial = False):
        if not initial:
            self.stored_ui_information()
        new_room_name = "Unnamed Chat"
        new_room = ChatRoom(name=new_room_name)
        self.chat_rooms.append(new_room)
        self.update_chat_room_list()
        
        if not initial:
            self.current_chat_room = new_room
            self.load_chat_room_data_into_ui(new_room)
            self.show_status_messages(f"New chat room '{new_room_name}' created.")
            self.ui.chat_room_table.selectRow(len(self.chat_rooms) - 1) # Select the newly added row

    def delete_selected_chat_room(self):
        selected_row = self.ui.chat_room_table.selectedIndexes()
        if not selected_row:
            self.show_status_messages("No chat room selected to delete.", is_error=True)
            return
        
        row_to_del = selected_row[0].row()
        room_to_del = self.chat_rooms[row_to_del]

        if len(self.chat_rooms) == 1:
            self.show_status_messages("Cannot delete the last chat room. Create a new one first.", is_error=True)
            return
        
        self.chat_rooms.pop(row_to_del)
        self.show_status_messages(f"Chat room '{room_to_del.name}' deleted.")
        self.update_chat_room_list()

        if room_to_del == self.current_chat_room:
            if self.chat_rooms:
                new_selection_index = min(row_to_del, len(self.chat_rooms) - 1)
                self.ui.chat_room_table.selectRow(new_selection_index)
                self.current_chat_room = self.chat_rooms[new_selection_index]
                self.load_chat_room_data_into_ui(self.current_chat_room)
            else:
                self.current_chat_room = None
                self.clear_chat_ui()

    def stored_ui_information(self):
        if self.current_chat_room:
            self.current_chat_room.m_api_key = self.ui.api_key_txt.text().strip()
            self.current_chat_room.m_prompt = self.ui.prompt_txt.toPlainText().strip()
            self.current_chat_room.m_temperature = self.ui.temp_val.text().strip()
            self.current_chat_room.default_chat_log = self.ui.non_history_txt.toPlainText().strip()
            self.current_chat_room.experiment_chat_log = self.ui.history_txt.toPlainText().strip()
            self.current_chat_room.user_in_txt = self.ui.input_text.toPlainText().strip()

    def room_name_changed(self, item: QTableWidgetItem):
        if self.chat_room_update_flag:
            return
        
        row = item.row()        
        load_room = self.chat_rooms[row]        
        load_room.name = item.text().strip()
        self.chat_rooms[row] = load_room

        self.update_chat_room_list()

        self.show_status_messages(f"Renamed the room: '{load_room.name}'")

    def load_selected_chat_room(self):
        self.stored_ui_information()
        selected_items = self.ui.chat_room_table.selectedItems()
        if selected_items:
            selected_row = selected_items[0].row()
            room = self.chat_rooms[selected_row]
            if room != self.current_chat_room: # Only update if a different room is selected
                self.current_chat_room = room
                self.load_chat_room_data_into_ui(room)
                self.show_status_messages(f"Switched to chat room: '{room.name}'")
        else:
            # If nothing is selected (e.g., after deletion of last item), clear UI
            self.current_chat_room = None
            self.clear_chat_ui()

    def load_chat_room_data_into_ui(self, room):
        # Disconnect signals temporarily to prevent unwanted triggers
        self.ui.api_key_txt.textChanged.disconnect(self.apply_api_key)
        self.ui.prompt_txt.textChanged.disconnect(self.apply_prompt)

        self.ui.api_key_txt.setText(room.m_api_key if room.m_api_key else "")
        self.ui.prompt_txt.setText(room.m_prompt if room.m_prompt else "")
        self.ui.temp_val.setText(room.m_temperature)
        self.ui.temp_slider.setValue(int(float(room.m_temperature) * 100))
        self.ui.non_history_txt.setText(room.default_chat_log)
        self.ui.history_txt.setText(room.experiment_chat_log)
        self.ui.input_text.setPlainText(room.user_in_txt)

        # Reconnect signals
        self.ui.api_key_txt.textChanged.connect(self.apply_api_key)
        self.ui.prompt_txt.textChanged.connect(self.apply_prompt)
    
    def clear_chat_ui(self):
        self.ui.api_key_txt.clear()
        self.ui.prompt_txt.clear()
        self.ui.temp_val.setText("0.00") # Reset to default
        self.ui.non_history_txt.clear()
        self.ui.history_txt.clear()
        self.ui.input_text.clear()
        
    def load_message(self):
        message = self.ui.input_text.toPlainText()

        if message.strip():
            if not self.current_chat_room.m_api_key:
                QMessageBox.about(
                self,
                "Error",
                "<p>Please enter your api key</p>",
                )
                return
            self.ui.input_text.clear()
            self.rag_llm(message)

            # self.default_llm(message)
            # self.history_llm(message)

        else:
            QMessageBox.about(
                self,
                "Error",
                "<p>Please enter any message</p>",
            )
    def apply_api_key(self):
        if self.ui.api_key_txt.text().strip():
            self.current_chat_room.m_api_key = self.ui.api_key_txt.text().strip()
            self.show_status_messages(f"api key is apply successful")
            # self.init_vector_db()

    def apply_prompt(self):
        if self.current_chat_room.m_prompt == self.ui.prompt_txt.toPlainText().strip():
            return
        elif self.ui.prompt_txt.toPlainText().strip():
            self.current_chat_room.m_prompt = self.ui.prompt_txt.toPlainText().strip()
            self.show_status_messages(f"prompt is apply successful")
        
    
    def default_llm(self, msg):
        response = None
        chat_model = ChatOpenAI(
            api_key=self.current_chat_room.m_api_key,
            temperature=self.current_chat_room.m_temperature,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    self.current_chat_room.m_prompt
                ),
                ("human", "{input}"),
            ]
        )
        chain = prompt | chat_model

        try:
            response = chain.invoke(
                {"input": msg},
            )
        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")

        if response:
            self.ui.non_history_txt.append(f"Sended Message: {msg}")
            self.ui.non_history_txt.append("")
            words = response.content.split(' ')
            self.ui.non_history_txt.append("Ai Messages: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.non_history_txt.textCursor()
                cursor.movePosition(cursor.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.non_history_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

        self.ui.non_history_txt.append("")

    def history_llm(self, msg):
        response = None
        chat_model = ChatOpenAI(
            api_key=self.current_chat_room.m_api_key,
            temperature=self.current_chat_room.m_temperature,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    self.current_chat_room.m_prompt
                ),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
            ]
        )
        chain = prompt | chat_model

        chain_history = RunnableWithMessageHistory(
            chain,
            lambda session_id: self.current_chat_room.chat_histroy,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

        try:
            response = chain_history.invoke(
                {"input": msg},
                {"configurable": {"session_id": "unused"}},
            )
        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")
        
        if response:
            self.ui.history_txt.append(f"Sended Message: {msg}")
            self.ui.history_txt.append("")
            words = response.content.split(' ')
            self.ui.history_txt.append("Ai Messages: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.history_txt.textCursor()
                cursor.movePosition(cursor.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.history_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

        self.ui.history_txt.append("")
        self.show_status_messages("Experiment chat is ")

    def rag_llm(self, msg):
        retreiver = self.worker.vector_db.as_retriever(search_kwargs={"k": 2})

        prompt_template = """
            당신은 제공된 문서를 기반으로 사용자의 질문에 답변하는 유능한 조수입니다.
            문서의 내용을 철저히 검토하여 질문에 대한 답변을 제공하세요.
            만약 문서에 질문에 대한 정보가 없다면, "제공된 문서에는 이 질문에 대한 정보가 없습니다."라고 답변하세요.
            문서에 있는 내용만을 사용하여 답변을 구성하고, 사실을 기반으로 명확하고 간결하게 응답해야 합니다.

            질문: {question}

            문서 내용:
            {context}

            답변:
            """
        prompt = ChatPromptTemplate.from_template(prompt_template)

        llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.108:8000/v1",
            temperature=0.2,
            # max_tokens = 6000
        )
        # llm = ChatOpenAI(
        #     api_key=self.current_chat_room.m_api_key
        # )

        rag_chain=(
            {"context": retreiver, "question": RunnablePassthrough()}
            | RunnableLambda(self.print_retrieved_document)
            | prompt
            | llm
            | StrOutputParser()
        )
        

        answer = rag_chain.invoke(msg)
        if answer:
            self.ui.history_txt.append(f"Sended Message: {msg}")
            self.ui.history_txt.append("")
            self.ui.history_txt.append("Ai Messages: ")

            words = answer.split(' ')
            for i, doc in enumerate(words):
                cursor = self.ui.history_txt.textCursor()
                cursor.movePosition(cursor.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(doc + " ")
                else:
                    cursor.insertText(doc + "\n")
                
                self.ui.history_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)
            self.ui.history_txt.insertPlainText("\n")
        else:
            print("오류")


        # retreiver = self.worker.vector_db.as_retriever()
        # res_doc = retreiver = retreiver.invoke(msg)

        # if res_doc:
        #     for i, doc in enumerate(res_doc):
        #         print(f"[{i+1}] 문서내용: {doc.page_content[:200]}...")
        #         words = str(doc).split(' ')
        #         for j, d in enumerate(words):
        #             cursor = self.ui.history_txt.textCursor()
        #             cursor.movePosition(cursor.End)

        #             # 마지막 단어가 아니면 공백 추가
        #             if j < len(words) - 1:
        #                 cursor.insertText(d + " ")
        #             else:
        #                 cursor.insertText(d + "\n")
                    
        #             self.ui.history_txt.setTextCursor(cursor)
                    
        #             # 텍스트가 추가될 때마다 UI 업데이트
        #             QCoreApplication.processEvents()
                    
        #             # 시작적 지연
        #             time.sleep(0.05)
        #         if doc.metadata:
        #             print(f"출처: {doc.metadata.get('source', '알 수 없음')}")
        # else:
        #     print("관련문서를 찾을 수 없습니다")
        # return
    def print_retrieved_document(self, in_dict):
        print("\n--- [디버그] 검색된 문서 ---")
        for i, doc in enumerate(in_dict['context']):
            print(f"문서 #{i+1}: {doc.page_content}")
            if doc.metadata:
                print(f"출처: {doc.metadata.get('source', '알 수 없음')}")
        print("----------------------------\n")
        print(in_dict)
        print("----------------------------\n")
        # 다음 단계로 데이터를 전달하기 위해 받은 딕셔너리를 그대로 반환합니다.
        return in_dict

if __name__ == "__main__":

    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


