import sys, os, time, copy, json, ast, markdown, psutil, signal, asyncio, sqlite3, socket, struct, requests
import pandas as pd
import subprocess
import atexit
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QMessageBox, QTableWidgetItem, QSizePolicy, QMenu, QFileDialog, QProgressDialog
)
from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QObject, QPoint, pyqtSignal, QThread, QUrl
from PyQt6.QtGui import QDoubleValidator, QAction, QTextCursor
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
from LLMStreamThread import LLMStreamThread
from AIS_Trajectory_compression import GenerateAISReport

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from langchain_community.utilities import SQLDatabase
from langchain_community.tools import QuerySQLDataBaseTool
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy import create_engine, inspect

#Query Routing
from typing import Literal, Optional
from pydantic import BaseModel, Field

#tokenizer
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import List
from transformers import AutoTokenizer
from datetime import datetime

sitmap_streamlit_process = None
dashboard_streamlit_process = None
geo_dashboard_streamlit_process = None

# DB 핸들링 함수
def init_db():
    db_path = "ships.db"

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"{db_path} 파일이 삭제되었습니다.")
        except Exception as e:
            QMessageBox.critical(None, "오류", f"db가 다른 프로그램에서 실행중이라면 종료해주세요")
            print(f"오류: {e}")
    else:
        print("삭제할 DB 파일이 존재하지 않습니다.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 테이블이 없으면 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ship_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ShipType TEXT,
            ShipName TEXT,
            mmsi INTEGER,
            timestamp TEXT,
            course REAL,
            speed REAL,
            longitude REAL,
            latitude REAL,
            higher_types TEXT,
            radius INTEGER
        )
    """)
    conn.commit()
    conn.close()

class ReceiveThread(QThread):
    log_signal = pyqtSignal(str)
    log_packet = pyqtSignal(int, list)
    disconnect_signal = pyqtSignal()
    msg_received = pyqtSignal(str)

    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.running = True
        self.packet_cnt = 0

    def recv_all(self, length):
        data = b''
        while len(data) < length:
            try:
                packet = self.socket.recv(length - len(data))
                if not packet: return None
                data += packet
            except:
                return None
        return data

    def run(self):
        # 스레드 내에서 DB 연결 (SQLite는 스레드 간 연결 공유 불가 원칙)
        conn = sqlite3.connect("ships.db")
        # conn.execute("PRAGMA journal_mode=WAL;") # 이 줄을 반드시 추가하세요!
        cursor = conn.cursor()

        while self.running:
            try:
                # 1. 헤더(4바이트) 읽기
                header = self.recv_all(5)
                if not header:
                    self.disconnect_signal.emit()
                    break
                
                # 2. 데이터 길이 파악
                data_type, data_len = struct.unpack('>BI', header)
                
                if data_type == 0:
                    # 3. 본문 읽기
                    body_bytes = self.recv_all(data_len)
                    if not body_bytes:
                        break

                    msg = body_bytes.decode('utf-8')

                    self.msg_received.emit(msg)

                else:
                    body_bytes = self.recv_all(data_len)
                    if not body_bytes:
                        break
                    # 4. JSON 파싱
                    json_str = body_bytes.decode('utf-8')
                    data_list = json.loads(json_str) # List of Dictionaries

                    if not data_list:
                        continue

                    # 5. DB Insert (Bulk)
                    # 딕셔너리 리스트를 튜플 리스트로 변환 (SQL 파라미터용)
                    db_tuples = []
                    for item in data_list:
                        # print(item)
                        res = (
                            item.get("ShipType"), item.get("ShipName"), item.get("mmsi"),
                            item.get("timestamp"), item.get("course"), item.get("speed"),
                            item.get("longitude"), item.get("latitude"), 
                            item.get("higher_types"), item.get("radius")
                        )
                        db_tuples.append(res)
                        self.packet_cnt += 1
                        self.log_packet.emit(self.packet_cnt, res)

                    # print(db_tuples)
                    
                    # 고속 저장
                    query = """
                        INSERT INTO ship_logs 
                        (ShipType, ShipName, mmsi, timestamp, course, speed, longitude, latitude, higher_types, radius)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    cursor.executemany(query, db_tuples)
                    conn.commit() # 트랜잭션 확정

                    # self.log_signal.emit(f"DB 저장 완료: {len(data_list)} 행")
                    # print(f"DB 저장 완료: {len(data_list)} 행")
            except Exception as e:
                self.log_signal.emit(f"에러 발생: {e}")
                self.disconnect_signal.emit()
                break

    def stop(self):
        self.running = False

class WaitingDialog(QProgressDialog):
    def __init__(self, parent=None):
        super().__init__("요청하신 내용을 바탕으로 최적의 답변을 준비하는 중입니다. 잠시만 기다려 주세요.",
                         None,
                         0, 0,
                         parent)
        
        # 플래그를 한 번에 설정 (Frameless + NoCloseButton)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                            Qt.WindowType.CustomizeWindowHint | 
                            Qt.WindowType.WindowStaysOnTopHint) # 최상단 유지 추가
        
        # 앱 전체를 차단하고 싶다면 ApplicationModal 권장
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumDuration(0)

    def closeEvent(self, event):
        # 작업이 끝나기 전까지는 X 버튼이나 단축키로 닫히지 않게 함
        if self.wasCanceled() or self.value() >= self.maximum():
            event.accept()
        else:
            event.ignore() # 닫기 요청 무시
    
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

class RouteQuery(BaseModel):
    datasource: Literal["ship_report", "ship_info", "none"] = Field(
        ...,
        description="사용자 질문에 따라 'ship_report' 또는 'ship_info' 또는 'none'으로 라우팅합니다."
    )
    target_ships: Optional[list[dict]] = Field(
        default=None,
        description="""datasource가 'ship_info'일 때만 해당 선박의 MMSI 번호를 추출하여 포함합니다.
        mmsi가 2개 이상일 경우 mmsi를 모두 포함하고 따옴표나 쌍따옴표 없이 int형으로 출력합니다
        'ship_report' 또는 'none'일 경우 이 필드는 비워둡니다(null)."""
    )

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
        self.set_web_view()                   #스트림릿 내부에 연동

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
        # self.token_encoding = tiktoken.get_encoding("o200k_harmony")
        self.MAX_TOKENS = 128000

        self.local_llm = None
        self.openai_llm = None

        #selected rag tech
        self.rag_indexing = "Default"
        self.rag_transformation = "Default"
        self.rag_post_processing = None

        self.report_msg = ""

        self.ui.default_retriever.setChecked(True)
        self.ui.default_generator.setChecked(True)

        self.scenario_time = None
        self.llm_worker = None
        self.stream_worker = None

        #쓰레드 기다리는 창
        self.waiting_dialog = None

        self.init_local_llm()
        self.init_web_view()
        
        #초기 chunk값 지정
        self.ui.parentretreiver_parent_chunk_size.setValue(3000)
        self.ui.parentretreiver_child_chunk_size.setValue(500)
        self.ui.summary_parent_chunk_size.setValue(3000)
        self.ui.hypo_parent_chunk_size.setValue(3000)
        self.ui.granular_chunk_size.setValue(3000)

        #전체화면 실행
        self.showMaximized()

        self.ui.splitter.setSizes([1204, 693])      #초기 프로그램 크기 조정

        #DB초기설정
        init_db()

        #소켓 관련 변수
        self.recv_thread = None
        self.socket = None
        self.start_server_time = ""
        self.curr_server_time = ""

        #날씨DB init
        conn = sqlite3.connect('d:/LEE/AI_team/github/Vision_AI_RnD_team/projects/test_project/ais_weather/korea_weather.db', check_same_thread=False)
        self.weather_cursor = conn.cursor()
        self.last_queried_hour = None

        #날씨데이터 저장
        # [ {'col1': 1, 'col2': 'a'}, {'col1': 2, 'col2': 'b'} ]
        self.weather_data = None

        self.ship_count = {}

    def init_local_llm(self):
        self.local_llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=self.current_chat_room.m_temperature,
            # max_tokens = 6000
        )
        # self.local_llm = ChatOpenAI(
        #     api_key="ai",
        #     model="openai/gpt-oss-20b",
        #     base_url="http://49.174.2.3:8000/v1",
        #     temperature=self.current_chat_room.m_temperature,
        #     # max_tokens = 6000
        # )
    def init_openai_llm(self):
        self.openai_llm = ChatOpenAI(
            api_key=self.current_chat_room.m_api_key,
            temperature=self.current_chat_room.m_temperature,
        )

    def init_web_view(self):
        initial_html = """
        <html>
        <head>
            <meta charset="utf-8">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>
                body { 
                    background-color: rgb(40,40,40); color: #d4d4d4; 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    line-height: 1.6; padding: 20px; 
                }
                table { border-collapse: collapse; width: 100%; margin: 15px 0; background: #252526; }
                th, td { border: 1px solid #444; padding: 10px; text-align: left; }
                th { background-color: #333; color: #b8f7b9; }
                code { background-color: #333; padding: 2px 4px; border-radius: 4px; }
                .cursor { 
                    display: inline-block; width: 8px; height: 18px; 
                    background-color: #b8f7b9; margin-left: 5px; 
                    vertical-align: middle; animation: blink 0.8s infinite; 
                }
                @keyframes blink { 50% { opacity: 0; } }
            </style>
        </head>
        <body>
            <div id="content"></div>
            <script>
                marked.setOptions({
                    breaks: true,
                    gfm: true
                });
                let fullMarkdown = ""; // 전체 문장을 저장할 변수
        
                function appendText(chunk) {
                    fullMarkdown += chunk; // 새로 들어온 조각만 합침
                    // 2. JS가 내부적으로 마크다운을 HTML로 변환 (매우 빠름)
                    document.getElementById('content').innerHTML = marked.parse(fullMarkdown) + '<span class="cursor"></span>';
                    window.scrollTo(0, document.body.scrollHeight);
                }
            </script>
        </body>
        </html>
        """
        self.ui.experiment_txt.setHtml(initial_html)

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
            parent_chunk_size=self.current_chat_room.parent_p_chunk_size,
            child_chunk_size=self.current_chat_room.parent_c_chunk_size
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
        # path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        files, _ = QFileDialog.getOpenFileNames(self, "파일 선택")
        folder_path = os.path.dirname(files[0])
        
        retriever_map = {
            "Default": self.create_default_retriever,
            "ParentRetriverPipeline": self.create_parent_retriever,
            "Summary": self.create_summary_retriever,
            "Hypothetical": self.create_hypothetical_retriever,
            "Granular": self.create_granular_retriever,
        }

        if folder_path:
            self.ui.path.setText(f"{folder_path}")

            self.ui.Loading_bar.setValue(0)
            self.ui.Load_btn.setEnabled(False) #작업 중 버튼 비활성화

            self.threading = QThread()

            if self.rag_indexing in retriever_map:
                self.worker = retriever_map[self.rag_indexing](folder_path)
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

    def splitter_logging(self):
        curr_size = self.ui.splitter.sizes()
        print(f"현재 사이즈: {curr_size}")

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
        # 스플리터 크기 디버깅
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
        self.ui.splitter.splitterMoved.connect(self.splitter_logging)

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

        #Client_func
        self.ui.btn_server_connect.clicked.connect(self.connect_server)

        self.ui.ship_btn.clicked.connect(self.debug_ais_llm_query)

        #program restart
        self.ui.reset_program.clicked.connect(self.restart_program)

    def debug_ais_llm_query(self):
        self.start_ais_llm_query("현재 상황에 대해 묘사해줘")

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
        self.ui.input_text.clear()
        
    def load_message(self):
        message = self.ui.input_text.toPlainText()

        if message.strip():
            self.ui.input_text.clear()
            self.query_routing_report(message)

        else:
            QMessageBox.about(
                self,
                "Error",
                "<p>Please enter any message</p>",
            )

    def init_query_routing(self):
        # 파일 열기 (r: 읽기 모드)
        with open('./data/ship_list.json', 'r', encoding='utf-8') as f:
            ship_list_json = json.load(f)

        structured_llm_router = self.local_llm.with_structured_output(RouteQuery)

        system = """당신은 사용자 질문을 '선박 리포트(ship_report)' '선박 정보(ship_info)' 또는 '기타(none)'로 분류하는 전문 라우터입니다.
        1. ship_report 선택 기준:.
        - 질문에 특정 선박 이름이나 MMSI 번호가 없는 경우.
        - 선박의 현재 위치, 상태, 항적 등 현재 상황에 대해 묻고 있지만, '어떤 선박'인지 식별할 수 있는 정보(이름/MMSI)가 전혀 없는 경우.
        - 현재 상황이나 상태 또는 지금까지의 상황에 대해 물어보는 경우.
        - 주요 쟁점 상황이나 종합적인 판단, 검토를 요청하는 경우.

        2. ship_info 선택 기준:
        - [선박리스트]에 존재하는 mmsi 번호 또는 선박이름(ShipName)이 포함되어 있는 경우.
        - 선박의 현재 위치, 상태, 항적, 이동패턴, 이동경로 등을 묻는 경우.

        3. none 선택 기준:
        - 질문에 [선박리스트]에 없는 선박 이름이나 MMSI 번호를 물어본 경우.
        - 인사, 일반적인 대화, 또는 해운/선박과 관련 없는 질문인 경우.

        [선박리스트]
        {ship_list_json}

        출력 규칙:
        - datasource가 'ship_info'인 경우, 제공된 선박 리스트에서 매칭된 {{ship_name: str, mmsi: int}} 객체의 리스트를 반환하십시오.
        - datasource가 'none'인 경우, target_ships 필드는 비워두십시오."""

        route_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human","{question}"),
            ]
        ).partial(ship_list_json=ship_list_json)

        return route_prompt | structured_llm_router

    def query_routing_report(self, question):
        question_router = self.init_query_routing()

        retriever_route = {
            'ship_report': lambda a1, a2: self.start_ais_llm_query(True, a1, a2),
            'ship_info': lambda a1, a2: self.start_ais_llm_query(False, a1, a2),
            'none': lambda a1, a2: self.rag_btn_llm(a1)
        }

        selected_data_source = question_router.invoke({"question": question})        

        mmsi_list = [
            i['mmsi']
            for i in selected_data_source.target_ships
        ]

        retriever_route[selected_data_source.datasource](question, mmsi_list)
    
    def apply_api_key(self):
        if self.ui.api_key_txt.text().strip():
            self.current_chat_room.m_api_key = self.ui.api_key_txt.text().strip()
            self.show_status_messages(f"api key is apply successful")

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
                "문서 내용에 기반하여 대한 답변을 제공하세요."
                # "만약 문서에 질문에 대한 정보가 없다면, '제공된 문서에는 이 질문에 대한 정보가 없습니다.'라고 답변하세요."
                "최대한 문서에 있는 내용을 사용하여 답변을 구성하고, 사실을 기반으로 명확하고 간결하게 응답해야 합니다."
                "답변은 영어로 표현된 원래 의미가 최대한 바뀌지 않도록 모두 한글로 번역해서 응답하세요"
                "기존의 답변의 markdown 형식도 그대로 유지하면서 번역해주세요"
                "문서 내용: {context}"),
                ("placeholder", "{history}"),
                ("human", "질문: {question}"),
            ]
        )

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

            report_msg = ""
            report_msg += f"Sended Message: {msg}\n\n"
            report_msg += "Ai Messages: \n"
            report_msg += answer.content
            report_msg += "\n\n"

            self.js_streaming(report_msg)
            
            self.show_status_messages("Default chat is working successful")
        else:
            print("오류")

    def rag_btn_llm(self, question):
        if self.rag_indexing != self.current_chat_room.rag_apply_indexing:
            QMessageBox.critical(self, "오류", "load 버튼으로 임베딩을 진행해주세요")
            return

        if not self.current_chat_room.m_api_key:
            QMessageBox.critical(self, "오류", "api key를 입력해주세요")
            return
        
        if not self.worker:
            QMessageBox.critical(self, "오류", "벡터스토어가 없습니다")
            return
        
        if self.stream_worker is not None:
            QMessageBox.critical(self, "오류", "이전작업이 아직 실행중입니다.")
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
                "문서 내용에 기반하여 대한 답변을 제공하세요."
                # "만약 문서에 질문에 대한 정보가 없다면, '제공된 문서에는 이 질문에 대한 정보가 없습니다.'라고 답변하세요."
                "최대한 문서에 있는 내용을 사용하여 답변을 구성하고, 사실을 기반으로 명확하고 간결하게 응답해야 합니다."
                "답변은 영어로 표현된 원래 의미가 최대한 바뀌지 않도록 모두 한글로 번역해서 응답하세요"
                "기존의 답변의 markdown 형식도 그대로 유지하면서 번역해주세요"
                "문서 내용: {context}"),
                ("placeholder", "{history}"),
                ("human", "질문: {question}"),
            ]
        )

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

        self.stream_worker = LLMStreamThread(question, self.local_llm, rag_history_chain)
        self.stream_worker.text_chunk_received.connect(self.handle_rag_response)
        self.stream_worker.stream_finished.connect(self.handle_rag_response_finished)
        self.stream_worker.finished.connect(self.stream_worker.deleteLater)

        self.waiting_dialog = WaitingDialog(self)
        self.waiting_dialog.setStyleSheet(self.GetStyleSheetTemplate())

        if self.stream_worker and self.stream_worker.isRunning():
            print("아직 작업 중입니다.")
        else:
            # 새로 생성하거나 기존 게 끝난 걸 확인 후 실행
            self.stream_worker.start()
            self.waiting_dialog.exec()

    def handle_rag_response(self, chunk):
        try:
            if self.isEnabled() == False:
                self.setEnabled(True)
            if hasattr(self, 'waiting_dialog') and self.waiting_dialog.isVisible():
                self.waiting_dialog.accept()

            self.js_streaming_chunk(chunk)
        except Exception as e:
            print(f"{e}")


    def handle_rag_response_finished(self):
        if self.stream_worker:
            self.stream_worker.deleteLater()
            self.stream_worker = None
        QTimer.singleShot(5000, self.EnableStreamButtons)

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

    def set_web_view(self):
        self.ui.weather_board.setUrl(QUrl("http://localhost:8502"))
        self.ui.geospatial_board.setUrl(QUrl("http://localhost:8503"))
        

    def GetStyleSheetTemplate(self):
        return """
        /* 1. QProgressDialog (다이얼로그 창 배경) */
        QProgressDialog {
            background-color: #000000; /* 검정 배경 */
            border: 2px solid rgb(184, 247, 185); /* 얇은 테두리 */
        }

        /* 2. 내부 QLabel (메시지 텍스트) */
        QProgressDialog QLabel {
            color: rgb(184, 247, 185);
            font-size: 11pt;
            font-weight: bold;
            padding: 5px;
        }

        /* 3. 내부 QProgressBar (전체 배경 및 테두리) */
        QProgressDialog QProgressBar {
            border: 1px solid rgb(184, 247, 185);
            border-radius: 5px;
            background-color: rgb(40, 40, 40);
            text-align: center;
            color: white;
        }

        /* 4. QProgressBar::chunk (채워지는 막대) */
        QProgressDialog QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgb(50, 120, 50), stop:1 rgb(100,180,100));
            border-radius: 2px;
        }
        """

    def start_ais_llm_query(self, flag: bool, question, mmsi_list):
        if self.llm_worker is not None:
            print("이전작업이 아직 실행중입니다.")
            return
                
        self.llm_worker = GenerateAISReport(flag, self.local_llm, question, self.weather_data, mmsi_list, self.start_server_time, self.curr_server_time)

        self.llm_worker.report_chunk_fin.connect(self.handle_ais_response)
        self.llm_worker.report_finished.connect(self.handle_ais_finished)
        self.llm_worker.report_error.connect(self.handle_ais_error)
        self.llm_worker.finished.connect(self.llm_worker.deleteLater)

        # 기다리는 창
        self.waiting_dialog  = WaitingDialog(self)
        self.waiting_dialog.setStyleSheet(self.GetStyleSheetTemplate())

        report_msg = ""
        report_msg += "Sended Message: " + question + "\n\n"
        report_msg += "Ai Messages: \n"
        self.js_streaming_header(report_msg)

        if self.llm_worker and self.llm_worker.isRunning():
            print("아직 작업 중입니다.")
        else:
            # 새로 생성하거나 기존 게 끝난 걸 확인 후 실행
            self.llm_worker.start()
            self.waiting_dialog.exec()

    def handle_ais_response(self, chunk):
        if self.isEnabled() == False:
            self.setEnabled(True)
        if hasattr(self, 'waiting_dialog') and self.waiting_dialog.isVisible():
            self.waiting_dialog.accept()
        self.js_streaming_chunk(chunk)

    def handle_ais_finished(self):
        if self.llm_worker:
            self.llm_worker.deleteLater()
            self.llm_worker = None

    def handle_ais_error(self, msg):
        if self.isEnabled() == False:
            self.setEnabled(True)
        if hasattr(self, 'waiting_dialog') and self.waiting_dialog.isVisible():
            self.waiting_dialog.accept()
        QMessageBox.critical(self, "오류", f"{msg}")
            
    def handle_error(self, msg):
        if self.isEnabled() == False:
            self.setEnabled(True)
        if hasattr(self, 'waiting_dialog') and self.waiting_dialog.isVisible():
            self.waiting_dialog.accept()

        QMessageBox.critical(self, "오류", f"{msg}")

    def js_streaming(self, response):
        words = response.split(' ')
        word_buffer = []

        for i, word in enumerate(words):
            word_buffer.append(word + " ")
            if len(word_buffer) >= 10 or i == len(words) - 1:
                combined_chunk = "".join(word_buffer)
                
                # JS에 전달 (이제 단어 하나가 아니라 10단어 뭉치 전달)
                safe_chunk = combined_chunk.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
                print(safe_chunk)
                self.ui.experiment_txt.page().runJavaScript(f"appendText(`{safe_chunk}`)")
                
                word_buffer = [] # 버퍼 비우기

            time.sleep(0.01)
            QCoreApplication.processEvents()

    def js_streaming_header(self, header):
        safe_chunk = json.dumps(header)
        self.ui.experiment_txt.page().runJavaScript(f"appendText({safe_chunk})")

    def js_streaming_chunk(self, chunk):
        if self.isEnabled() == False:
            self.setEnabled(True)
        if hasattr(self, 'waiting_dialog') and self.waiting_dialog.isVisible():
            self.waiting_dialog.accept()

        try:
            safe_chunk = json.dumps(chunk)
            self.ui.experiment_txt.page().runJavaScript(f"appendText({safe_chunk})")
        except Exception as e:
            print(f"{e}")
        
    def connect_server(self):
        ip = self.ui.ip_input.text()
        try:
            port = int(self.ui.port_input.text())
        except ValueError:
            QMessageBox.critical(self, "오류", "포트 번호는 숫자여야 합니다.")
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((ip, port))
            
            self.ui.text_server_log.append(f"[System] Connected to {ip}:{port}")
            self.toggle_ui(True)

            self.recv_thread = ReceiveThread(self.socket)
            self.recv_thread.msg_received.connect(self.process_server_message)
            self.recv_thread.log_signal.connect(self.update_log)
            self.recv_thread.log_packet.connect(self.update_packet_log)
            self.recv_thread.disconnect_signal.connect(self.on_disconnected)
            self.recv_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "접속 오류", f"서버에 접속할 수 없습니다.\n{e}")

    def update_log(self, msg):
        self.ui.text_server_log.append(msg)

    def update_packet_log(self, i, packet):
        time = packet[3]
        self.fetch_weather_and_position(time)
        self.curr_server_time = time

        if not self.start_server_time:
            self.start_server_time = time[:19]

        #현재 구역안에 있는 배 개수 계산
        self.counting_current_ship(packet)

        #시뮬레이션 시간 출력
        if isinstance(time, str) and len(time) >= 19:
            self.ui.server_time.setText(time[:19])

        # 로그가 5만개 이상일 경우 24500개 정리(패킷 1개에 2줄 차지함)
        if self.ui.text_server_log.document().blockCount() > 50000:
            # self.ui.text_server_log.clear()
            cursor = self.ui.text_server_log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(49000):
                cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.ui.text_server_log.setTextCursor(cursor)
        display_text = f"[{i}] Packet: {' | '.join(map(str, packet))} |"
        self.ui.text_server_log.append(display_text)

    def counting_current_ship(self, packet):
        # packet[2]: MMSI, packet[6]: 경도, packet[7]: 위도
        mmsi = packet[2]
        lon = packet[6]
        lat = packet[7]

        # 1. 운항 구역(Boundary) 내에 있는지 먼저 판단
        is_inside = (125.6 <= lon <= 131.2) and (lat <= 36)

        # 2. 상태에 따른 딕셔너리 조작
        if is_inside:
            # 영역 안에 있고 아직 등록되지 않았다면 추가 (이미 있다면 무시하거나 업데이트)
            if mmsi not in self.ship_count:
                self.ship_count[mmsi] = packet
        else:
            # 영역 밖에 있고 리스트에 존재한다면 삭제
            # pop(key, None)은 키가 없어도 에러를 내지 않으므로 if 체크 없이 한 줄로 가능합니다.
            self.ship_count.pop(mmsi, None)

    def fetch_weather_and_position(self, curr_time):
        # 1. 연도 계산 (3년 더하기)
        year_plus_3 = str(int(curr_time[:4]) + 3)

        # 2. 월-일 부분 (예: '-12-10 ')
        month_day = curr_time[4:11]

        # 3. '시' 부분만 추출해서 0 제거 (예: '03' -> 3 -> '3')
        # 인덱스 11:13은 'HH' 부분을 의미합니다.
        hour_int = int(curr_time[11:13])
        hour_str = str(hour_int)

        # 4. 최종 DB 포맷 조립 (예: '2025-12-10 3')
        current_hour_str = f"{year_plus_3}{month_day}{hour_str}"

        if self.last_queried_hour != current_hour_str:
            try:
                query = """
                    SELECT 
                        b.지점명,
                        b.latitude, 
                        b.longitude, 
                        w.*
                    FROM 
                        weather_buoy AS w
                    JOIN 
                        buoy_position AS b ON w.지점 = b.지점
                    WHERE 
                        w.일시 LIKE ?
                """

                # 3. 쿼리 실행
                search_param = f"{current_hour_str}:%"
                self.weather_cursor.execute(query, (search_param,))
                rows = self.weather_cursor.fetchall()
                
                # 4. 데이터 출력 및 처리
                if rows:
                    # 2. Pandas 데이터프레임으로 로드
                    col_names = [desc[0] for desc in self.weather_cursor.description]
                    df = pd.DataFrame(rows, columns=col_names)

                    # 3. 컬럼 슬라이싱 (Pandas에서 처리)
                    # 앞의 3개(지점명, lat, lon)와 w의 3번째 컬럼(인덱스로는 5번 이후) 조립
                    # 예: 지점명(0), lat(1), lon(2), 지점(3), 일시(4), 기온(5), 습도(6)...
                    # 만약 w 테이블의 3번째 컬럼부터 끝까지를 원하신다면:
                    target_cols = [0, 1, 2] + list(range(5, len(df.columns)))
                    final_df = df.iloc[:, target_cols]

                    # 날씨데이터를 llm에서 활용하기 위해 글로벌 변수에 저장 후 init 시 같이 넘기기 위함
                    # df형태로 저장
                    self.weather_data = final_df

                    #변환된 테이블 확인
                    # print("\n" + "="*50)
                    # print("전송 데이터 샘플 (상위 2행)")
                    # print("-"*50)
                    # print(final_df.head(2)) # 또는 final_df.iloc[:2]
                    # print("="*50 + "\n")

                    # 4. JSON으로 변환 (리스트-딕셔너리 형태)
                    # orient='records'를 쓰면 수만 줄의 데이터도 순식간에 변환됩니다.
                    # replace를 사용하여 모든 NaN 값을 None으로 바꿉니다.
                    # value_data = final_df.where(pd.notnull(final_df), None).to_dict(orient='records')
                    value_data = final_df.fillna(0).to_dict(orient='records')

                    url = "http://localhost:8600/update"
                    try:
                        r = requests.post(url, json=value_data)
                        print(f"상태 코드: {r.status_code}")

                        text_data = r.text
                        print(f"서버에러내용: {text_data}")

                    except Exception as e:
                        print(f"연결 에러: {e}")
                        

                    print(f"🔔 [시간 변경 감지] {current_hour_str}시 기상 데이터 갱신")
                    # print(rows[0][0], rows[0][1], rows[0][2])
                    for row in rows:
                        print(row)
                # 3. 조회가 완료되면 마지막 조회 시간을 현재 '시'로 업데이트
                self.last_queried_hour = current_hour_str
            except Exception as e:
                print(f"DB 조회 중 오류 발생: {e}")

    def toggle_ui(self, connected):
        #클라이언트 -> 서버 메세지 전송 확장성을 위한 func
        # self.msg_input.setEnabled(connected)
        # self.btn_send.setEnabled(connected)

        self.ui.btn_server_connect.setEnabled(not connected)
        self.ui.ip_input.setEnabled(not connected)
        self.ui.port_input.setEnabled(not connected)

    def process_server_message(self, msg):
        self.ui.text_server_log.append(f"[Server]: {msg}")

    def on_disconnected(self):
        self.ui.text_server_log.append("[System] Disconnected from server.")
        self.toggle_ui(False)
        if self.socket:
            self.socket.close()

    def closeEvent(self, event):
        if self.recv_thread:
            self.recv_thread.stop()
        if self.socket:
            self.socket.close()
        event.accept()

    def restart_program(self):
        """현재 프로그램을 종료하고 다시 시작합니다."""
        print("프로그램을 재시작합니다...")
        
        # 1. 현재 실행 중인 파이썬 인터프리터 경로 가져오기 (python.exe 등)
        python = sys.executable
        
        # 2. 실행 중인 스크립트 파일과 인자값 유지
        # os.execv는 현재 프로세스를 새로 시작하는 프로세스로 완전히 대체합니다.
        os.execv(python, [python] + sys.argv)

def kill_process_on_port(port):
        """특정 포트를 사용 중인 프로세스를 찾아 종료"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # 포트 연결 정보 확인
                connections = proc.connections(kind='inet')
                for conn in connections:
                    if conn.laddr.port == port:
                        print(f"포트 {port}를 사용 중인 프로세스 발견 (PID: {proc.info['pid']}, 이름: {proc.info['name']})")
                        
                        # 🌟 윈도우에서도 문제없는 강제 종료 방식
                        proc.kill() 
                        
                        # 종료될 때까지 잠시 대기 (선택사항)
                        proc.wait(timeout=3)
                        print(f"PID {proc.info['pid']} 프로세스가 성공적으로 종료되었습니다.")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception as e:
                print(f"종료 시도 중 오류 발생: {e}")

def start_streamlit():
    kill_process_on_port(8501)
    kill_process_on_port(8502)
    kill_process_on_port(8503)
    global sitmap_streamlit_process
    global dashboard_streamlit_process
    global geo_dashboard_streamlit_process
    # Streamlit 앱 실행 명령어

    cmd = ["streamlit", "run", "./previous_files/fast_change.py", "--server.port=8501"]
    cmd2 = ["streamlit", "run", "./dashboard.py", "--server.headless=True", "--server.port=8502"]
    cmd3 = ["streamlit", "run", "./geo_dashboard.py", "--server.headless=True", "--server.port=8503"]

    sitmap_streamlit_process = subprocess.Popen(cmd)
    print("실시간 상황도 streamlit서버가 백그라운드에서 시작되었습니다.")

    dashboard_streamlit_process = subprocess.Popen(cmd2)
    print("Dashboard streamlit서버가 백그라운드에서 시작되었습니다.")

    geo_dashboard_streamlit_process = subprocess.Popen(cmd3)
    print("Geo Dashboard streamlit서버가 백그라운드에서 시작되었습니다.")

def stop_streamlit():
    """Streamlit 서버 프로세스 종료"""
    global sitmap_streamlit_process
    global dashboard_streamlit_process

    if sitmap_streamlit_process:
        sitmap_streamlit_process.kill()
        print("상황도 Streamlit 서버가 종료되었습니다.")

    if dashboard_streamlit_process:
        dashboard_streamlit_process.kill()
        print("Dashboard Streamlit 서버가 종료되었습니다.")

    if geo_dashboard_streamlit_process:
        geo_dashboard_streamlit_process.kill()
        print("Geo Dashboard Streamlit 서버가 종료되었습니다.")

if __name__ == "__main__":
    atexit.register(stop_streamlit)

    start_streamlit()

    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


