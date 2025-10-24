import sys, os, time, copy, tiktoken
import subprocess
import atexit
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QMessageBox, QTableWidgetItem, QSizePolicy, QMenu, QFileDialog
)
from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QObject, QPoint, pyqtSignal, QThread, QUrl
from PyQt6.QtGui import QDoubleValidator, QAction
from PyQt6.uic import loadUi

from mainwindow import Ui_MainWindow
from Default_Gen import DefaultGenerator
from DefaultRetriever import DefaultRetriever
from ParentChildDocumentRetriever import ParentRetriverPipeline
from SummaryDocumentRetriever import SummaryDocumentRetrieverPipeline
from HypotheticalQuestionRetrieverPipeline import HypotheticalQuestionRetrieverPipeline
from GranularChunkExpansionRetriever import GranularChunkExpansionRetriverPipeline
from Rewrite_Retrieve_Read_Gen import RewriteRetrieveReadQuestionGenerator
from Step_Back_Question_Gen import StepBackQuestionGenerator
from Multiple_Questions_Gen import MultipleQuestionGenerator

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

#tokenizer
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import List
from transformers import AutoTokenizer

streamlit_process = None

class ChatRoom:
    def __init__(self, name):
        self.name = name
        self.m_api_key = None
        self.m_temperature = "0.00"
        self.m_prompt = ""

        self.default_chat_list = ""
        self.experiment_chat_list = ""
        self.user_in_txt = ""

        self.default_token = 0
        self.experiment_token = 0

        #Question Transformations
        self.rag_transformation = "Default"

        #Advanced Indexing
        self.rag_indexing = "Default"
        self.rag_apply_indexing = ""
        self.parent_p_chunk_size = 0
        self.parent_c_chunk_size = 0
        self.summary_p_chunk_size = 0
        self.hypo_p_chuck_size = 0
        self.granular_chucnk_size = 0

        #Retrieval Post-Processing
        self.rag_post_processing = None
        self.m_similarity = "0.00"
        self.m_keyword = None
        self.similarity_checked = False
        self.keyword_checked = False
        self.rrf_checked = False

        self.m_loading_bar = 0
        self.loaded_folder_path = ""

        self.default_history = ChatMessageHistory()
        self.experiment_history = ChatMessageHistory()

        self.chat_stored = {}
        self.default_session_id = "default"
        self.experiment_session_id = "experiment"
        self.default_config = {"configurable": {"session_id": self.default_session_id}}
        self.experiment_config = {"configurable": {"session_id": self.experiment_session_id}}

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
        # validator.setNotation(QDoubleValidator.StandardNotation)
        self.ui.temp_val.setValidator(validator)

        self.connectSignalsSlots()
        self.set_web_view()

        #chatroom 클래스 관련 변수
        self.chat_rooms = []                    #채팅방 관리
        self.current_chat_room = None
        self.add_new_chat_room(initial=True)    #처음에 채팅방 1개 만듬
        self.chat_room_update_flag = False      #채팅방 첫 생성인지 확인 flag

        #채팅방 ui관련 설정
        # self.ui.chat_room_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # self.ui.chat_room_table.customContextMenuRequested.connect(self.on_context_menu)

        # 오른쪽 클릭된 아이템을 저장할 멤버 변수
        self.clicked_item = None

        #slider 관련 변수
        self.left_animation = Slider_Animation(self)
        self.left_animation.animation_timer.timeout.connect(self.update_left_animation)
        self.right_animation = Slider_Animation(self)
        self.right_animation.animation_timer.timeout.connect(self.update_right_animation)

        self.threading = None
        self.text_splitter = None
        self.worker = None

        self.tokenizer = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")
        self.token_encoding = tiktoken.get_encoding("o200k_harmony")
        self.MAX_TOKENS = 128000

        self.local_llm = None
        self.openai_llm = None

        #selected rag tech
        self.rag_indexing = "Default"
        self.rag_transformation = "Default"
        self.rag_post_processing = None

        #초기값 세팅
        # self.ui.splitter.setSizes([175, 715, 278])      #초기 프로그램 크기 조정

        self.ui.default_retriever.setChecked(True)
        self.ui.default_generator.setChecked(True)

        

        self.init_local_llm()
        

    def init_local_llm(self):
        self.local_llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.108:8000/v1",
            temperature=self.current_chat_room.m_temperature,
            # max_tokens = 6000
        )
    def init_openai_llm(self):
        self.openai_llm = ChatOpenAI(
            api_key=self.current_chat_room.m_api_key,
            temperature=self.current_chat_room.m_temperature,
        )

    def create_default_generator(self):
        return DefaultGenerator(
            llm=self.local_llm
        )
    def create_rewrite_retrieve_read_generator(self):
        return RewriteRetrieveReadQuestionGenerator(
            llm=self.local_llm
        )
    def create_multiple_question_generator(self):
        return  MultipleQuestionGenerator(
            llm=self.local_llm
        )
    def create_step_back_question_generator(self):
        return StepBackQuestionGenerator(
            llm=self.local_llm
            # llm=self.openai_llm
        )

    def create_default_retriever(self, path):
        return DefaultRetriever(
            folder_path=path,
            api_key=self.current_chat_room.m_api_key
        )
    
    def create_parent_retriever(self, path):
        return ParentRetriverPipeline(
            folder_path=path,
            openai_api_key=self.current_chat_room.m_api_key,
            # parent_chunk_size=self.current_chat_room.parentretriever_parent_chunk_size,
            # child_chunk_size=self.current_chat_room.parentretriever_child_chunk_size
        )
    def create_summary_retriever(self, path):
        return SummaryDocumentRetrieverPipeline(
            folder_path=path,
            openai_api_key=self.current_chat_room.m_api_key,
            llm_model=self.local_llm
        )
    def create_hypothetical_retriever(self, path):
        return HypotheticalQuestionRetrieverPipeline(
            folder_path=path,
            openai_api_key=self.current_chat_room.m_api_key,
            llm_model=self.local_llm,
        )
    def create_granular_retriever(self, path):
        return GranularChunkExpansionRetriverPipeline(
            folder_path=path,
            openai_api_key=self.current_chat_room.m_api_key,
            granular_chunk_size=500,
        )

    def load_folder(self):
        if not self.current_chat_room.m_api_key:
            QMessageBox.critical(self, "오류", "api key를 입력해주세요")
            return
        
        self.init_openai_llm()
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        
        retriever_map = {
            "Default": self.create_default_retriever,
            "ParentRetriverPipeline": self.create_parent_retriever,
            "Summary": self.create_summary_retriever,
            "Hypothetical": self.create_hypothetical_retriever,
            "Granular": self.create_granular_retriever,
        }

        if path:
            self.ui.path.setText(f"{path}")

            self.ui.Loading_bar.setValue(0)
            self.ui.Load_btn.setEnabled(False) #작업 중 버튼 비활성화

            self.threading = QThread()

            if self.rag_indexing in retriever_map:
                self.worker = retriever_map[self.rag_indexing](path)
            else:
                print(f"Error: retriever_map에 없는 키: {self.rag_indexing}")
                return

            #현재 채팅방에 인덱싱 기법 저장
            self.current_chat_room.rag_apply_indexing = self.rag_indexing

            # self.worker = DefaultRetriever(
            #     folder_path=path,
            #     api_key=self.current_chat_room.m_api_key
            # )

            self.worker.moveToThread(self.threading)

            self.threading.started.connect(self.worker.run)
            self.worker.progresses.connect(self.ui.Loading_bar.setValue)
            self.worker.finished.connect(self.threading.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.finished.connect(self.threading.deleteLater)

            self.worker.finished.connect(lambda: self.ui.Load_btn.setEnabled(True))
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "오류", msg))
            self.worker.finished.connect(lambda: QMessageBox.information(self, "완료", "임베딩이 완료되었습니다"))
            self.worker.changeUi.connect(self.check_applied_indexing)

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
        # print(current_sizes)
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
        # print(current_sizes)
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

    # retrieval post processing
    def slider_score_value(self):
        #값이 0 이상이 될 경우 자동 체크
        if self.ui.similarity_slider.value() != 0:
            self.ui.similarity_post_processor.setChecked(True)
        else:
            self.ui.similarity_post_processor.setChecked(False)

        float_val = self.ui.similarity_slider.value() / 100
        if float_val == float(self.current_chat_room.m_similarity):
            return
        self.current_chat_room.m_similarity = str(float_val)
        self.sync_score_value()

    def text_score_value(self):
        float_val = self.ui.similarity_val.text().strip()
        if float_val == self.current_chat_room.m_similarity or float_val == "":
            return
        self.current_chat_room.m_similarity = float_val
        self.sync_score_value()

    def sync_score_value(self):
        final_val = self.current_chat_room.m_similarity
        if self.ui.similarity_slider.value() * 0.01 != float(final_val):
            self.ui.similarity_slider.setValue(int(float(final_val) * 100))
        if self.ui.similarity_val.text().strip() != final_val:
            self.ui.similarity_val.setText(final_val)

    def set_parent_retriever_parent_chunk_size(self):
        self.current_chat_room.parent_p_chunk_size = self.ui.parentretreiver_parent_chunk_size.value()

    def set_parent_retriever_child_chunk_size(self):
        self.current_chat_room.parent_c_chunk_size = self.ui.parentretreiver_child_chunk_size.value()

    def set_summary_retriever_parent_chunk_size(self):
        self.current_chat_room.summary_p_chunk_size = self.ui.summary_parent_chunk_size.value()

    def set_hypothetical_retriever_parent_chunk_size(self):
        self.current_chat_room.hypo_p_chuck_size = self.ui.hypo_parent_chunk_size.value()
        
    def set_granular_retriever_chunk_size(self):
        self.current_chat_room.granular_chucnk_size = self.ui.granular_chunk_size.value()

    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.load_message)
        self.ui.api_key_txt.textChanged.connect(self.apply_api_key)
        self.ui.prompt_txt.textChanged.connect(self.apply_prompt)
        # self.ui.new_chat_btn.clicked.connect(self.add_new_chat_room)
        # self.ui.del_chat_btn.clicked.connect(self.delete_selected_chat_room)
        # self.ui.chat_room_table.itemSelectionChanged.connect(self.load_selected_chat_room)
        # self.ui.chat_room_table.itemChanged.connect(self.room_name_changed)
        self.ui.temp_slider.valueChanged.connect(self.slider_temp_value)
        self.ui.temp_val.textChanged.connect(self.text_temp_value)
        # self.ui.left_split_btn.clicked.connect(self.toggle_left_animation)
        # self.ui.right_split_btn.clicked.connect(self.toggle_right_animation)
        self.ui.Load_btn.clicked.connect(self.load_folder)

        #Question Transformations
        self.ui.default_generator.toggled.connect(self.apply_rag_transformation)
        self.ui.rewrite_generator.toggled.connect(self.apply_rag_transformation)
        self.ui.multiple_generator.toggled.connect(self.apply_rag_transformation)
        self.ui.step_back_generator.toggled.connect(self.apply_rag_transformation)

        #Advanced Indexing
        self.ui.default_retriever.toggled.connect(self.apply_rag_indexing)
        self.ui.parent_retriever.toggled.connect(self.apply_rag_indexing)
        self.ui.summary_retriever.toggled.connect(self.apply_rag_indexing)
        self.ui.hypothetical_retriever.toggled.connect(self.apply_rag_indexing)
        self.ui.granular_retriever.toggled.connect(self.apply_rag_indexing)
        self.ui.parentretreiver_parent_chunk_size.valueChanged.connect(self.set_parent_retriever_parent_chunk_size)
        self.ui.parentretreiver_child_chunk_size.valueChanged.connect(self.set_parent_retriever_child_chunk_size)
        self.ui.summary_parent_chunk_size.valueChanged.connect(self.set_summary_retriever_parent_chunk_size)
        self.ui.hypo_parent_chunk_size.valueChanged.connect(self.set_hypothetical_retriever_parent_chunk_size)
        self.ui.granular_chunk_size.valueChanged.connect(self.set_granular_retriever_chunk_size)

        #Retrieval Post-Processing
        self.ui.similarity_slider.valueChanged.connect(self.slider_score_value)
        self.ui.similarity_val.textChanged.connect(self.text_score_value)
        self.ui.keyword_txt.textChanged.connect(self.apply_keyword)

    def show_status_messages(self, message, is_error=False):
        if is_error:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ffcccc; color: red;}")
        else:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ccffcc; color: green;}")
        self.ui.statusbar.showMessage(message, 3000) # Show for 3 seconds

    # def update_chat_room_list(self):
    #     self.chat_room_update_flag = True

    #     # self.ui.chat_room_table.setRowCount(len(self.chat_rooms))
    #     for i, room in enumerate(self.chat_rooms):
    #         item = QTableWidgetItem(room.name)
    #         item.setData(Qt.ItemDataRole.UserRole, room) # Store the ChatRoom object in the item
    #         # self.ui.chat_room_table.setItem(i, 0, item)
        
    #     # Select the current chat room in the list
    #     if self.current_chat_room and self.current_chat_room in self.chat_rooms:
    #         index = self.chat_rooms.index(self.current_chat_room)
    #         self.ui.chat_room_table.selectRow(index)
    #     elif self.chat_rooms:
    #         self.ui.chat_room_table.selectRow(0) # Select first if no current or current deleted

    #     self.chat_room_update_flag = False

    def add_new_chat_room(self, initial = False):
        if not initial:
            self.stored_ui_information()
        new_room_name = "Unnamed Chat"
        new_room = ChatRoom(name=new_room_name)
        self.chat_rooms.append(new_room)
        self.current_chat_room = self.chat_rooms[0]
        # self.update_chat_room_list()
        
        if not initial:
            self.current_chat_room = new_room
            self.load_chat_room_data_into_ui(new_room)
            self.show_status_messages(f"New chat room '{new_room_name}' created.")
            # self.ui.chat_room_table.selectRow(len(self.chat_rooms) - 1) # Select the newly added row

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
            self.current_chat_room.default_chat_list = self.ui.default_txt.toPlainText().strip()
            self.current_chat_room.experiment_chat_list = self.ui.experiment_txt.toPlainText().strip()
            self.current_chat_room.user_in_txt = self.ui.input_text.toPlainText().strip()

            #Question Transformation
            self.current_chat_room.rag_transformation = self.ui.rag_transformation.text()

            #Advanced Indexing
            self.current_chat_room.rag_indexing = self.ui.rag_indexing.text()

            #post-processing
            self.current_chat_room.similarity_checked = self.ui.similarity_post_processor.isChecked()
            self.current_chat_room.keyword_checked = self.ui.keywords.isChecked()
            self.current_chat_room.rrf_checked = self.ui.reciprocal_rank_fusion.isChecked()

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
        self.ui.keyword_txt.textChanged.disconnect(self.apply_keyword)

        self.ui.api_key_txt.setText(room.m_api_key if room.m_api_key else "")
        self.ui.prompt_txt.setText(room.m_prompt if room.m_prompt else "")
        self.ui.temp_val.setText(room.m_temperature)
        self.ui.temp_slider.setValue(int(float(room.m_temperature) * 100))
        self.ui.default_txt.setText(room.default_chat_list)
        self.ui.experiment_txt.setText(room.experiment_chat_list)
        self.ui.input_text.setPlainText(room.user_in_txt)

        #Question Transformations
        self.ui.rag_transformation.setText(room.rag_transformation)
        question_transformation = {
            "Default": self.ui.default_generator.setChecked,
            "Rewrite-Retrieve-Read Generator": self.ui.rewrite_generator.setChecked,
            "Multiple Questions Generator": self.ui.multiple_generator.setChecked,
            "Step-Back Question Generator": self.ui.step_back_generator.setChecked,
        }
        question_transformation[room.rag_transformation](True)

        #Advanced Indexing
        self.ui.rag_indexing.setText(room.rag_indexing)
        self.ui.parentretreiver_parent_chunk_size.setValue(room.parent_p_chunk_size)
        self.ui.parentretreiver_child_chunk_size.setValue(room.parent_c_chunk_size)
        self.ui.summary_parent_chunk_size.setValue(room.summary_p_chunk_size)
        self.ui.hypo_parent_chunk_size.setValue(room.hypo_p_chuck_size)
        self.ui.granular_chunk_size.setValue(room.granular_chucnk_size)
        advanced_indexing = {
            "Default": self.ui.default_retriever.setChecked,
            "ParentRetriverPipeline": self.ui.parent_retriever.setChecked,
            "Summary": self.ui.summary_retriever.setChecked,
            "Hypothetical": self.ui.hypothetical_retriever.setChecked,
            "Granular": self.ui.granular_retriever.setChecked,
        }
        advanced_indexing[room.rag_indexing](True)
        

        #Retrieval Post-Processing
        self.ui.rag_post_processing.setText(room.rag_post_processing)        
        self.ui.similarity_val.setText(room.m_similarity)
        self.ui.similarity_slider.setValue(int(float(room.m_similarity) * 100))
        self.ui.keyword_txt.setText(room.m_keyword)
        self.ui.similarity_post_processor.setChecked(room.similarity_checked)
        self.ui.keywords.setChecked(room.keyword_checked)
        self.ui.reciprocal_rank_fusion.setChecked(room.rrf_checked)

        self.ui.Loading_bar.setValue(room.m_loading_bar)
        self.ui.path.setText(room.loaded_folder_path)

        self.ui.default_token_bar.setFormat(f"used tokens: {self.current_chat_room.default_token:.2f}%")
        self.ui.default_token_bar.setValue(int(self.current_chat_room.default_token))
        self.ui.experiment_token_bar.setFormat(f"used tokens: {self.current_chat_room.experiment_token:.2f}%")
        self.ui.experiment_token_bar.setValue(int(self.current_chat_room.experiment_token))

        # Reconnect signals
        self.ui.api_key_txt.textChanged.connect(self.apply_api_key)
        self.ui.prompt_txt.textChanged.connect(self.apply_prompt)
        self.ui.keyword_txt.textChanged.connect(self.apply_keyword)
    
    def clear_chat_ui(self):
        self.ui.api_key_txt.clear()
        self.ui.prompt_txt.clear()
        self.ui.temp_val.setText("0.00") # Reset to default
        self.ui.default_txt.clear()
        self.ui.experiment_txt.clear()
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
            
            if self.rag_indexing != self.current_chat_room.rag_apply_indexing:
                QMessageBox.critical(self, "오류", "load 버튼으로 임베딩을 진행해주세요")
                return
            
            self.ui.input_text.clear()
            self.default_llm(message)
            self.rag_llm(message)
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

    def apply_keyword(self):
        if self.ui.keyword_txt.text():
            self.ui.keywords.setChecked(True)
        else:
            self.ui.keywords.setChecked(False)

        if self.ui.keyword_txt.text().strip():
            self.current_chat_room.m_keyword = self.ui.keyword_txt.text().strip()
            self.show_status_messages(f"keyword is apply successful")
        else:
            self.current_chat_room.m_keyword = None
        
    
    # non-histroy llm func
    # def default_llm(self, msg):
    #     response = None
    #     chat_model = ChatOpenAI(
    #         api_key=self.current_chat_room.m_api_key,
    #         temperature=self.current_chat_room.m_temperature,
    #     )
    #     prompt = ChatPromptTemplate.from_messages(
    #         [
    #             (
    #                 "system",
    #                 self.current_chat_room.m_prompt
    #             ),
    #             ("human", "{input}"),
    #         ]
    #     )
    #     chain = prompt | chat_model

    #     try:
    #         response = chain.invoke(
    #             {"input": msg},
    #         )
    #     except Exception as e:
    #         QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")

    #     if response:
    #         self.ui.default_txt.append(f"Sended Message: {msg}")
    #         self.ui.default_txt.append("")
    #         words = response.content.split(' ')
    #         self.ui.default_txt.append("Ai Messages: ")

    #         #stream효과
    #         for i, w in enumerate(words):
    #             cursor = self.ui.default_txt.textCursor()
    #             cursor.movePosition(cursor.MoveOperation.End)

    #             # 마지막 단어가 아니면 공백 추가
    #             if i < len(words) - 1:
    #                 cursor.insertText(w + " ")
    #             else:
    #                 cursor.insertText(w + "\n")
                
    #             self.ui.default_txt.setTextCursor(cursor)
                
    #             # 텍스트가 추가될 때마다 UI 업데이트
    #             QCoreApplication.processEvents()
                
    #             # 시작적 지연
    #             time.sleep(0.05)

    #     self.ui.default_txt.append("")

    def default_llm(self, msg):
        response = None

        # chat_model = ChatOpenAI(
        #     api_key=self.current_chat_room.m_api_key,
        #     temperature=self.current_chat_room.m_temperature,
        # )

        #Local LLM applied
        chat_model = self.local_llm

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "3단락 이하로 답변해줘"
                    # self.current_chat_room.m_prompt
                ),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
            ]
        )

        chain = (
            prompt
            # | RunnableLambda(lambda x: print(x["chat history"].messages))
            | chat_model
        )

        chain_history = RunnableWithMessageHistory(
            chain,
            self.get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

        try:
            # self.current_chat_room.default_history.add_user_message(msg)
            # response = chain.invoke(
            #     {"chat_history": self.current_chat_room.default_history.messages},
            # )
            # self.current_chat_room.default_history.add_ai_message(response)

            response = chain_history.invoke(
                {"input": msg},
                self.current_chat_room.default_config
            )

        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")
        
        if response:
            print(response.response_metadata['token_usage'])
            print(response.response_metadata['token_usage']['total_tokens'])
            self.current_chat_room.default_token += response.response_metadata['token_usage']['total_tokens'] / self.MAX_TOKENS * 100
            update = f"used tokens: {self.current_chat_room.default_token:.2f}%"
            self.ui.default_token_bar.setFormat(update)
            self.ui.default_token_bar.setValue(int(self.current_chat_room.default_token))
            print(self.current_chat_room.default_token)
            print(self.current_chat_room.default_token * 128000)

            self.ui.default_txt.append(f"Sended Message: {msg}")
            self.ui.default_txt.append("")
            words = response.content.split(' ')
            self.ui.default_txt.append("Ai Messages: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.default_txt.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.default_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

        self.ui.default_txt.append("")
        self.show_status_messages("Default chat is working successful")

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
            self.ui.experiment_txt.append(f"Sended Message: {msg}")
            self.ui.experiment_txt.append("")
            words = response.content.split(' ')
            self.ui.experiment_txt.append("Ai Messages: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.experiment_txt.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.experiment_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

        self.ui.experiment_txt.append("")
        self.show_status_messages("Experiment chat is ")

    def rag_llm(self, msg):
        if not self.current_chat_room.m_api_key:
            QMessageBox.critical(self, "오류", "api key를 입력해주세요")
            return
        
        if not self.worker:
            QMessageBox.critical(self, "오류", "벡터스토어가 없습니다")
            return

        generator_map = {
            "Default": self.create_default_generator,
            "Rewrite-Retrieve-Read Generator": self.create_rewrite_retrieve_read_generator,
            "Multiple Questions Generator": self.create_multiple_question_generator,
            "Step-Back Question Generator": self.create_step_back_question_generator,
        }
        print(self.rag_transformation)
        generator = generator_map[self.rag_transformation]()

        # prompt_template = """
        #     당신은 제공된 문서를 기반으로 사용자의 질문에 답변하는 유능한 조수입니다.
        #     문서의 내용을 철저히 검토하여 질문에 대한 답변을 제공하세요.
        #     만약 문서에 질문에 대한 정보가 없다면, "제공된 문서에는 이 질문에 대한 정보가 없습니다."라고 답변하세요.
        #     문서에 있는 내용만을 사용하여 답변을 구성하고, 사실을 기반으로 명확하고 간결하게 응답해야 합니다.

        #     이전 대화:
        #     {history}

        #     문서 내용:
        #     {context}

        #     질문: {question}

        #     답변:
        #     """
        # prompt = ChatPromptTemplate.from_template(prompt_template)
 
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", f"{self.current_chat_room.m_prompt}\n"
                "당신은 제공된 문서를 기반으로 사용자의 질문에 답변하는 유능한 조수입니다."
                "문서의 내용을 철저히 검토하여 질문에 대한 답변을 제공하세요."
                "만약 문서에 질문에 대한 정보가 없다면, '제공된 문서에는 이 질문에 대한 정보가 없습니다.'라고 답변하세요."
                "문서에 있는 내용만을 사용하여 답변을 구성하고, 사실을 기반으로 명확하고 간결하게 응답해야 합니다."
                "문서 내용: {context}"),
                ("placeholder", "{history}"),
                ("human", "질문: {question}"),
            ]
        )

        # llm = ChatOpenAI(
        #     api_key=self.current_chat_room.m_api_key,
        #     temperature=self.current_chat_room.m_temperature,
        # )
        similary = None
        keywords = None

        if self.ui.similarity_post_processor.isChecked() and self.ui.similarity_post_processor.isEnabled():
            similary = float(self.current_chat_room.m_similarity)
        if self.ui.keywords.isChecked() and self.ui.keywords.isEnabled():
            keyword = self.current_chat_room.m_keyword
            split_list = keyword.split(',')
            keywords = [item.strip() for item in split_list]

        rag_chain = generator.build_rag_chain(prompt, self.worker.copy_retriever(), similary, keywords, self.ui.reciprocal_rank_fusion.isChecked())

        rag_history_chain = RunnableWithMessageHistory(
            rag_chain,
            self.get_session_history,
            input_messages_key="question",
            history_messages_key="history",
        )

        answer = rag_history_chain.invoke(
            {"question": msg},
            self.current_chat_room.experiment_config,
        )

        if answer:
            print(answer.response_metadata['token_usage'])
            print(answer.response_metadata['token_usage']['total_tokens'])
            self.current_chat_room.experiment_token += answer.response_metadata['token_usage']['total_tokens'] / self.MAX_TOKENS * 100
            update = f"used tokens: {self.current_chat_room.experiment_token:.2f}%"
            self.ui.experiment_token_bar.setFormat(update)
            self.ui.experiment_token_bar.setValue(int(self.current_chat_room.experiment_token))
            print(self.current_chat_room.experiment_token)
            print(self.current_chat_room.experiment_token * 128000)

            self.ui.experiment_txt.append(f"Sended Message: {msg}")
            self.ui.experiment_txt.append("")
            self.ui.experiment_txt.append("Ai Messages: ")

            words = answer.content.split(' ')
            for i, doc in enumerate(words):
                cursor = self.ui.experiment_txt.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(doc + " ")
                else:
                    cursor.insertText(doc + "\n")
                
                self.ui.experiment_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)
            self.ui.experiment_txt.append("")
            self.show_status_messages("Default chat is working successful")
        else:
            print("오류")


        # retriever = self.worker.vector_db.as_retriever()
        # res_doc = retriever = retriever.invoke(msg)

        # if res_doc:
        #     for i, doc in enumerate(res_doc):
        #         print(f"[{i+1}] 문서내용: {doc.page_content[:200]}...")
        #         words = str(doc).split(' ')
        #         for j, d in enumerate(words):
        #             cursor = self.ui.experiment_txt.textCursor()
        #             cursor.movePosition(cursor.MoveOperation.End)

        #             # 마지막 단어가 아니면 공백 추가
        #             if j < len(words) - 1:
        #                 cursor.insertText(d + " ")
        #             else:
        #                 cursor.insertText(d + "\n")
                    
        #             self.ui.experiment_txt.setTextCursor(cursor)
                    
        #             # 텍스트가 추가될 때마다 UI 업데이트
        #             QCoreApplication.processEvents()
                    
        #             # 시작적 지연
        #             time.sleep(0.05)
        #         if doc.metadata:
        #             print(f"출처: {doc.metadata.get('source', '알 수 없음')}")
        # else:
        #     print("관련문서를 찾을 수 없습니다")
        # return
    
    
    #tokenizer func
    def count_tokens(self, messages: List[BaseMessage]) -> int:
        token_count = 0
        # 시스템 프롬프트 토큰도 계산
        token_count += len(self.token_encoding.encode("너는 친절한 AI 어시스턴트야. 항상 존댓말로 대답해."))
        
        for message in messages:
            token_count += len(self.token_encoding.encode(message.content))
        return token_count
    
    def get_full_prompt_token_count(self, prompt_object) -> int:
        """
        LLM에 전달되는 프롬프트의 모든 요소(role 포함)의 토큰 수를 정확하게 계산합니다.
        """
        full_prompt_string = ""
        
        # 프롬프트 객체는 messages 리스트를 가지고 있습니다.
        for message in prompt_object.messages:
            # 각 메시지를 LLM이 이해하는 형태로 문자열에 추가
            if isinstance(message, SystemMessage):
                full_prompt_string += f"<|system|>\n{message.content}\n"
            elif isinstance(message, HumanMessage):
                full_prompt_string += f"<|user|>\n{message.content}\n"
            elif isinstance(message, AIMessage):
                full_prompt_string += f"<|assistant|>\n{message.content}\n"
            # 기타 다른 메시지 타입이 있다면 추가

        # 최종적으로 완성된 전체 프롬프트 문자열을 토크나이징
        return len(self.tokenizer.encode(full_prompt_string))
    
    def get_session_history(self, session_id: str) -> ChatMessageHistory:
        if session_id not in self.current_chat_room.chat_stored:
            self.current_chat_room.chat_stored[session_id] = ChatMessageHistory()
        return self.current_chat_room.chat_stored[session_id]
    
    def apply_rag_transformation(self):
        radio_btn = self.sender()
        self.toggle_active_rrf(radio_btn.text())
        if radio_btn.isChecked():
            self.rag_transformation = radio_btn.text()
            self.ui.rag_transformation.setText(f'{radio_btn.text()}')
    
    def apply_rag_indexing(self):
        radio_btn = self.sender()
        if radio_btn.isChecked():
            self.rag_indexing = radio_btn.text()
            self.ui.rag_indexing.setText(f'{radio_btn.text()}')
            self.check_applied_indexing()

    def check_applied_indexing(self):
        if self.rag_indexing != self.current_chat_room.rag_apply_indexing:
            self.ui.rag_indexing.setStyleSheet("color: red;")
        else:
            self.ui.rag_indexing.setStyleSheet("color: rgb(166, 217, 171);")

    def toggle_active_rrf(self, val):
        if val == "Multiple Questions Generator":
            self.ui.reciprocal_rank_fusion.setEnabled(True)
            self.ui.similarity_post_processor.setChecked(False)
            self.ui.similarity_post_processor.setEnabled(False)
            self.ui.keywords.setChecked(False)
            self.ui.keywords.setEnabled(False)
            self.ui.similarity_slider.setEnabled(False)
            self.ui.similarity_val.setEnabled(False)
            self.ui.keyword_txt.setEnabled(False)
        else:
            self.ui.reciprocal_rank_fusion.setChecked(False)
            self.ui.reciprocal_rank_fusion.setEnabled(False)
            self.ui.similarity_post_processor.setEnabled(True)
            self.ui.keywords.setEnabled(True)
            self.ui.similarity_slider.setEnabled(True)
            self.ui.similarity_val.setEnabled(True)
            self.ui.keyword_txt.setEnabled(True)

    def apply_rag_post_processing(self):
        radio_btn = self.sender()
        if radio_btn.isChecked():
            self.rag_post_processing = radio_btn.text()
            self.ui.rag_post_processing.setText(f'{radio_btn.text()}')

    def set_web_view(self):
        self.ui.webEngineView.setUrl(QUrl("http://localhost:8501"))

def start_streamlit():
    """Streamlit 서버를 백그라운드에서 실행"""
    global streamlit_process
    # Streamlit 앱 실행 명령어
    cmd = ["streamlit", "run", "shorad_simulator.py", "--server.headless=True"]
    # cmd = ["streamlit", "run", "shorad_simulator.py"]
    streamlit_process = subprocess.Popen(cmd)
    print("Streamlit 서버가 백그라운드에서 시작되었습니다.")

def stop_streamlit():
    """Streamlit 서버 프로세스 종료"""
    global streamlit_process
    if streamlit_process:
        streamlit_process.kill()
        print("Streamlit 서버가 종료되었습니다.")

if __name__ == "__main__":
    atexit.register(stop_streamlit)

    start_streamlit()

    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


