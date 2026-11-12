import sys
import os
import time
import json
import psutil
import sqlite3
import socket
import struct
import pandas as pd
import subprocess
import atexit
import requests
import shutil
import threading
from pathlib import Path
from multiprocessing import shared_memory
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QMessageBox, QFileDialog
)
from PyQt6.QtCore import QTimer, pyqtSignal, QThread, QUrl, QLoggingCategory
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWebEngineCore import QWebEngineSettings

from langchain_openai import ChatOpenAI

from langfuse import get_client
from dotenv import load_dotenv

from my_battlefield_crew.ui.mainwindow import Ui_MainWindow
from my_battlefield_crew.setting.weather_data_sender import DataSenderThread
from my_battlefield_crew.setting.rag_config import RAGConfig
from my_battlefield_crew.setting.llm_config import LLMConfig
from my_battlefield_crew.setting.rag_setting_tab import RAGSettingManager
from my_battlefield_crew.setting.setting_tab import SettingTabManager
from my_battlefield_crew.RAG.embedding_worker import RemoteEmbeddingWorker

sitmap_streamlit_process = None
dashboard_streamlit_process = None
geo_dashboard_streamlit_process = None
chainlit_process = None

CHAINLIT_LLM_CONFIG_URL = "http://127.0.0.1:8504/api/llm/config"
CHAINLIT_RAG_CONFIG_URL = "http://127.0.0.1:8504/api/rag/config"
CHAINLIT_VECTORSTORE_URL = "http://127.0.0.1:8504/api/rag/vectorstore"

# chainlit 서버에 보내기 위한 
SHM_NAME = "ais_sim_server_time"
SHM_SIZE = 32
SHM_NAME_2 = "ais_start_server_time"
SHM_SIZE_2 = 32
SHM_DB_PATH_NAME = "db_path"
SHM_DB_PATH_LEN = 256

# 패킷으로 전달되는 데이터가 저장되는 DB경로
DB_PATH = "src/my_battlefield_crew/data/ships.db"

# DB 핸들링 함수
def init_db():
    db_path = DB_PATH

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
    server_time_sig = pyqtSignal(str)

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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        while self.running:
            try:
                # 1. 헤더(4바이트) 읽기
                header = self.recv_all(24)
                if not header:
                    self.disconnect_signal.emit()
                    break
                
                # 2. 데이터 길이 파악
                data_type, time_bytes, data_len = struct.unpack('>B19sI', header)

                curr_server_time = time_bytes.decode('utf-8')

                self.server_time_sig.emit(curr_server_time)
                
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

class Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 💡 MainWindow의 self.ui를 그대로 주입하여 RAG 전담 매니저 생성
        self.rag_manager = RAGSettingManager(self.ui, parent=self)
        self.setting_manager = SettingTabManager(self.ui, parent=self)
        self.embed_worker = None

        # 💡 1. 프로세스 간 공유 메모리 블록 생성 (이전 프로세스 잔존물 안전 처리)
        try:
            self.shm = shared_memory.SharedMemory(name=SHM_NAME, create=True, size=SHM_SIZE)
            self.shm2 = shared_memory.SharedMemory(name=SHM_NAME_2, create=True, size=SHM_SIZE_2)
            self.shm_db_path = shared_memory.SharedMemory(name=SHM_DB_PATH_NAME, create=True, size=SHM_DB_PATH_LEN)
        except FileExistsError:
            self.shm = shared_memory.SharedMemory(name=SHM_NAME)
            self.shm2 = shared_memory.SharedMemory(name=SHM_NAME_2)
            self.shm_db_path = shared_memory.SharedMemory(name=SHM_DB_PATH_NAME)

        self.connectSignalsSlots()
        self.set_web_view()                   #스트림릿 내부에 연동

        # 오른쪽 클릭된 아이템을 저장할 멤버 변수
        self.clicked_item = None

        self.worker = None

        self.MAX_TOKENS = 128000

        self.local_llm = None
        self.openai_llm = None

        #selected rag tech
        self.rag_indexing = "Default"
        self.rag_transformation = "Default"
        self.rag_post_processing = None

        self.report_msg = ""

        # self.ui.default_retriever.setChecked(True)
        self.ui.radio_qt_default.setChecked(True)

        self.scenario_time = None
        self.llm_worker = None
        self.stream_worker = None

        self.init_local_llm()
                
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

        QLoggingCategory.setFilterRules("js=false")

        # 1. 처음에는 접속 거부 에러 대신 로딩 안내 화면을 띄워둠
        self.ui.experiment_txt.setHtml(
            """
            <html>
                <body style="display:flex; justify-content:center; align-items:center; height:100vh; background:#1e1e1e; color:#ccc; font-family:sans-serif;">
                    <div style="text-align:center;">
                        <h2>Chainlit AI 엔진 구동 중...</h2>
                        <p style="font-size:14px; color:#888;">서버 포트(8504) 바인딩을 대기하고 있습니다.</p>
                    </div>
                </body>
            </html>
            """
        )

        # 2. 서버 포트 감시 타이머 시작 (0.5초마다 체크)
        self.retry_count = 0
        self.max_retries = 30  # 최대 15초 대기 (0.5s * 30)

        self.server_check_timer = QTimer(self)
        self.server_check_timer.setInterval(500)
        self.server_check_timer.timeout.connect(self._check_chainlit_ready)
        self.server_check_timer.start()

        load_dotenv()
        self.langfuse = get_client()
        
    def init_local_llm(self):
        self.local_llm = ChatOpenAI(
            api_key="ai",
            # model="openai/gpt-oss-20b",
            model="RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic",
            base_url="http://192.168.0.110:8000/v1",
            # base_url="http://49.174.2.3:8000/v1",
            # temperature=self.current_chat_room.m_temperature,
            # max_tokens = 6000
        )

    def init_openai_llm(self):
        self.openai_llm = ChatOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.1,
        )

    def _check_chainlit_ready(self):
        """8504 포트가 열렸는지 논블로킹 소켓으로 점검"""
        self.retry_count += 1

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            # connect_ex는 성공 시 0, 실패 시 에러 코드를 반환 (예외 미발생)
            result = s.connect_ex(("127.0.0.1", 8504))

            if result == 0:
                # 💡 포트 연결 성공: 타이머 끄고 실제 URL 로드
                self.server_check_timer.stop()
                print(">>> [MainWindow] Chainlit 서버 포트 오픈 확인, 페이지 로드")
                self.ui.experiment_txt.setUrl(QUrl("http://127.0.0.1:8504"))
                return

        # 타임아웃 초과 시 처리
        if self.retry_count >= self.max_retries:
            self.server_check_timer.stop()
            self.ui.experiment_txt.setHtml(
                "<h3 style='color:red; text-align:center;'>Chainlit 서버 응답 시간 초과</h3>"
            )

    def on_rag_config_auto_sync(self, config: RAGConfig):
        """UI 설정 변경 시 백그라운드 스레드를 통해 Chainlit으로 자동 동기화"""
        payload = config.model_dump(mode="json")

        def _send():
            try:
                resp = requests.post(
                    CHAINLIT_RAG_CONFIG_URL,
                    json=payload,
                    timeout=1.0  # 로컬 IPC 통신이므로 1초 타임아웃
                )
                if resp.status_code == 200:
                    # 메인 윈도우 하단 상태바가 있다면 2초간 안내 메시지 출력
                    if hasattr(self, "statusBar") and self.statusBar():
                        self.statusBar().showMessage("RAG 설정이 백엔드에 동기화되었습니다.", 2000)
                    print(f"[RAG CONFIG] Auto Sync 성공: {config.indexing.strategy}")
                else:
                    print(f"[RAG CONFIG] Auto Sync 서버 응답 오류 상태코드: {resp.status_code}, 메시지: {resp.text}")

            except requests.exceptions.ConnectionError:
                # Chainlit 서버가 아직 켜지지 않았을 때는 작업 흐름을 방해하지 않고 로그만 남김
                print("[Auto Sync 알림] Chainlit 서버가 구동 중이지 않아 설정을 전송하지 못했습니다.")
            except Exception as e:
                print(f"[Auto Sync 예외 발생] {e}")

        # UI 스레드가 블로킹되어 슬라이더가 멈칫하는 현상을 방지하기 위해 데몬 스레드로 즉시 실행
        threading.Thread(target=_send, daemon=True).start()

    def on_llm_config_auto_sync(self, config: LLMConfig):
        """UI 설정 변경 시 백그라운드 스레드를 통해 Chainlit으로 자동 동기화"""
        payload = config.model_dump(mode="json")

        def _send():
            try:
                resp = requests.post(
                    CHAINLIT_LLM_CONFIG_URL,
                    json=payload,
                    timeout=1.0  # 로컬 IPC 통신이므로 1초 타임아웃
                )
                if resp.status_code == 200:
                    # 메인 윈도우 하단 상태바가 있다면 2초간 안내 메시지 출력
                    if hasattr(self, "statusBar") and self.statusBar():
                        self.statusBar().showMessage("RAG 설정이 백엔드에 동기화되었습니다.", 2000)
                    print(f"[LLM CONFIG] Auto Sync 성공: {config.system_prompt[:10]}...")
                else:
                    print(f"[LLM CONFIG] Auto Sync 서버 응답 오류 상태코드: {resp.status_code}, 메시지: {resp.text}")

            except requests.exceptions.ConnectionError:
                # Chainlit 서버가 아직 켜지지 않았을 때는 작업 흐름을 방해하지 않고 로그만 남김
                print("[Auto Sync 알림] Chainlit 서버가 구동 중이지 않아 설정을 전송하지 못했습니다.")
            except Exception as e:
                print(f"[Auto Sync 예외 발생] {e}")

        # UI 스레드가 블로킹되어 슬라이더가 멈칫하는 현상을 방지하기 위해 데몬 스레드로 즉시 실행
        threading.Thread(target=_send, daemon=True).start()

    def on_select_documents(self):
        curr_config = self.setting_manager.get_config().model_dump()

        if curr_config.get("api_key") is None:
            QMessageBox.critical(self, "오류", "api key를 입력해주세요")
            return
        
        self.init_openai_llm()

        if self.openai_llm is None:
            print("openai_llm 초기화 오류")
            return
        
        # path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "RAG 사내 규정 문서 선택",
            "",
            "문서 파일 (*.pdf *.txt *.docx *.md);;All Files (*)",
        )

        if files:
            folder_path = os.path.dirname(files[0])
            print(f"선택한 폴더: {folder_path}")

        else:
            print("파일 선택이 취소되었습니다.")
            return

        # 💡 핵심: CWD 불일치 방지를 위해 무조건 완벽한 절대 경로로 정규화
        absolute_paths = [str(Path(f).resolve()) for f in files]

        # UI 초기화 및 비활성화 처리
        self.ui.progress_bar_doc.setValue(0)
        self.ui.btn_select_doc.setEnabled(False)
        if hasattr(self.ui, "btn_cancel_embed"):
            self.ui.btn_cancel_embed.setEnabled(True)

        self.ui.edit_select_path.setText(f"{folder_path}")
        
        # 백그라운드 워커 구동
        self.embed_worker = RemoteEmbeddingWorker(absolute_paths, parent=self)
        self.embed_worker.progress_changed.connect(self.ui.progress_bar_doc.setValue)
        self.embed_worker.status_message.connect(
            # lambda msg: self.statusBar().showMessage(msg, 3000)
            lambda msg: print("qt에서 받은 상태 메세지:" + msg)
        )
        self.embed_worker.finished.connect(self._on_embed_finished)        
        self.embed_worker.cancelled.connect(self._on_embed_finished)
        self.embed_worker.failed.connect(self._on_embed_failed)
        self.embed_worker.start()

    def connectSignalsSlots(self):
        # self.ui.send_btn.clicked.connect(self.load_message)
        self.ui.btn_select_doc.clicked.connect(self.on_select_documents)
        self.rag_manager.config_changed.connect(self.on_rag_config_auto_sync)
        self.setting_manager.config_changed.connect(self.on_llm_config_auto_sync)
        self.ui.btn_cancel_embed.clicked.connect(self.on_cancel_embedding)
        
        #Client_func
        self.ui.btn_server_connect.clicked.connect(self.connect_server)

        #program restart
        # self.ui.reset_program.clicked.connect(self.restart_program)

    def on_cancel_embedding(self):
        """임베딩 취소 버튼 클릭 시"""
        self.ui.btn_select_doc.setEnabled(True)
        self.ui.btn_cancel_embed.setEnabled(False)
        if self.embed_worker and self.embed_worker.isRunning():
            self.embed_worker.request_cancel()

    def _on_embed_finished(self):
        self.ui.btn_select_doc.setEnabled(True)
        if hasattr(self.ui, "btn_cancel_embed"):
            self.ui.btn_cancel_embed.setEnabled(False)

        # 💡 안전한 메모리 해제 및 참조 초기화
        if self.embed_worker is not None:
            self.embed_worker.deleteLater()  # Qt 이벤트 루프에서 안전하게 C++ 객체 삭제
            self.embed_worker = None  # 파이썬 레벨 참조 제거

    def _on_embed_failed(self, error_msg: str):
        self._on_embed_finished()
        QMessageBox.critical(self, "임베딩 오류", error_msg)

    def show_status_messages(self, message, is_error=False):
        if is_error:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ffcccc; color: red;}")
        else:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ccffcc; color: green;}")
        self.ui.statusbar.showMessage(message, 3000) # Show for 3 seconds
        
    def on_embedding_success(self):
        self.ui.progress_bar_doc.setValue(100)
        print("서버 인메모리 임베딩 적재 완료")

    def set_web_view(self):
        self.ui.weather_board.setUrl(QUrl("http://localhost:8502"))
        self.ui.geospatial_board.setUrl(QUrl("http://localhost:8503"))
        # chainlit결과 클립보드 복사 가능 설정
        self.ui.experiment_txt.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )

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
            self.recv_thread.server_time_sig.connect(self.update_server_time)
            self.recv_thread.disconnect_signal.connect(self.on_disconnected)
            self.recv_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "접속 오류", f"서버에 접속할 수 없습니다.\n{e}")

    def update_log(self, msg):
        self.ui.text_server_log.append(msg)

    def update_packet_log(self, i, packet):
        time = packet[3]
        self.fetch_weather_and_position(time)
        # self.curr_server_time = time

        if not self.start_server_time:
            self.start_server_time = time[:19]
            self.shm2.buf[:19] = self.start_server_time.encode("ascii")
            path_bytes = DB_PATH.encode("utf-8")
            # 1. 버퍼 전체를 널 바이트(0)로 초기화한 뒤
            self.shm_db_path.buf[:] = b"\x00" * len(self.shm_db_path.buf)
            # 2. 앞부분에 경로 바이트 대입
            self.shm_db_path.buf[:len(path_bytes)] = path_bytes

        #현재 구역안에 있는 배 개수 계산
        self.counting_current_ship(packet)

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

    def update_server_time(self, time):
        self.curr_server_time = time
        self.ui.server_time.setText(self.curr_server_time)
        self.shm.buf[:19] = self.curr_server_time.encode("ascii")

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

                    # 1. 스레드 생성 및 데이터 전달
                    self.sender_thread = DataSenderThread(url, value_data)
                    
                    # 2. 결과가 돌아왔을 때 실행할 함수 연결 (선택 사항)
                    self.sender_thread.result_signal.connect(self.on_send_finished)
                    
                    # 3. 백그라운드에서 전송 시작! (UI는 멈추지 않고 바로 다음 줄로 넘어감)
                    self.sender_thread.start()
                                        
                # 3. 조회가 완료되면 마지막 조회 시간을 현재 '시'로 업데이트
                self.last_queried_hour = current_hour_str
            except Exception as e:
                print(f"DB 조회 중 오류 발생: {e}")

    def on_send_finished(self, success, message):
        """스레드가 전송을 마치면 자동으로 호출되는 함수"""
        if success:
            print(f"데이터 전송 완료: {message}")
        else:
            print(f"데이터 전송 실패: {message}")

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
        if self.shm:
            self.shm.close()
            self.shm.unlink()
        if self.shm2:
            self.shm2.close()
            self.shm2.unlink() 
        if self.shm_db_path:
            self.shm_db_path.close()
            self.shm_db_path.unlink()
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
                # 네트워크 연결 정보 확인
                connections = proc.net_connections(kind='inet') 
                for conn in connections:
                    if conn.laddr.port == port:
                        current_pid = proc.info['pid'] # 루프 안에서 안전하게 할당
                        print(f"포트 {port}를 사용 중인 프로세스 발견 (PID: {current_pid}, 이름: {proc.info['name']})")
                        
                        # 윈도우 트리 종료 적용
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(current_pid)], 
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        print(f"PID {current_pid} 프로세스 트리가 성공적으로 종료되었습니다.")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception as e:
                # 🌟 pid 변수 대신 안전하게 수집된 proc.info['pid']를 사용하여 오류 방지
                print(f"PID {proc.info['pid']} ({proc.info['name']}) 종료 시도 중 오류 발생: {e}")

def kill_process_tree(process):
    """부모 프로세스와 하위 자식 프로세스를 모두 강제 종료"""
    if process and process.poll() is None: # 프로세스가 존재하고 실행 중인 경우
        try:
            # /F: 강제 종료, /T: 자식 프로세스까지 트리 종료
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"프로세스 종료 중 오류 발생: {e}")

def start_streamlit():
    kill_process_on_port(8501)
    kill_process_on_port(8502)
    kill_process_on_port(8503)
    kill_process_on_port(8504)

    global sitmap_streamlit_process
    global dashboard_streamlit_process
    global geo_dashboard_streamlit_process
    global chainlit_process

    # uv 실행 파일 경로를 안전하게 탐색
    uv_bin = shutil.which("uv") or "uv"

    # Streamlit 앱 실행 명령어
    cmd = [uv_bin, "run", "streamlit", "run", "./src/my_battlefield_crew/map/simulation_map.py", "--server.port=8501"]
    cmd2 = [uv_bin, "run", "streamlit", "run", "./src/my_battlefield_crew/dashboard/weather_board.py", "--server.headless=True", "--server.port=8502"]
    cmd3 = [uv_bin, "run", "streamlit", "run", "./src/my_battlefield_crew/dashboard/geo_dashboard.py", "--server.headless=True", "--server.port=8503"]
    cmd4 = [uv_bin, "run", "chainlit", "run", "./src/my_battlefield_crew/chainlit_app/chat_main.py", "-h", "--port", "8504"]

    sitmap_streamlit_process = subprocess.Popen(cmd)
    print("실시간 상황도 streamlit서버가 백그라운드에서 시작되었습니다.")

    dashboard_streamlit_process = subprocess.Popen(cmd2)
    print("Dashboard streamlit서버가 백그라운드에서 시작되었습니다.")

    geo_dashboard_streamlit_process = subprocess.Popen(cmd3)
    print("Geo Dashboard streamlit서버가 백그라운드에서 시작되었습니다.")

    chainlit_process = subprocess.Popen(cmd4)
    print("Chainlit 서버가 백그라운드에서 시작되었습니다.")

def stop_streamlit():
    """Streamlit 서버 프로세스 종료"""
    global sitmap_streamlit_process
    global dashboard_streamlit_process
    global geo_dashboard_streamlit_process
    global chainlit_process

    if sitmap_streamlit_process:
        kill_process_tree(sitmap_streamlit_process)
        sitmap_streamlit_process = None
        print("상황도 Streamlit 서버가 종료되었습니다.")

    if dashboard_streamlit_process:
        kill_process_tree(dashboard_streamlit_process)
        dashboard_streamlit_process = None
        print("Dashboard Streamlit 서버가 종료되었습니다.")

    if geo_dashboard_streamlit_process:
        kill_process_tree(geo_dashboard_streamlit_process)
        geo_dashboard_streamlit_process = None
        print("Geo Dashboard Streamlit 서버가 종료되었습니다.")

    if chainlit_process:
        kill_process_tree(chainlit_process)
        chainlit_process = None
        print("Chainlit 서버가 종료되었습니다.")

if __name__ == "__main__":
    atexit.register(stop_streamlit)

    start_streamlit()

    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())