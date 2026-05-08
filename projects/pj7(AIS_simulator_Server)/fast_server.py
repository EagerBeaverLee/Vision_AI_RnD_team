import sys, os, csv, json
import pandas as pd
import socket
import time
import struct
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextBrowser, QTextEdit, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QMainWindow, QFileDialog)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QIntValidator
from Server_UI import Ui_MainWindow

# [수정] 각 클라이언트의 수신을 담당하는 개별 스레드
class ClientHandler(QThread):
    msg_received = pyqtSignal(object, str) # 소켓, 메시지
    disconnected = pyqtSignal(object)      # 소켓

    def __init__(self, client_socket, addr):
        super().__init__()
        self.client_socket = client_socket
        self.addr = addr
        self.running = True

    def recv_all(self, length):
        data = b''
        while len(data) < length:
            packet = self.client_socket.recv(length - len(data))
            if not packet: return None
            data += packet
        return data

    def run(self):
        while self.running:
            try:
                header = self.recv_all(4)
                if not header:
                    self.disconnected.emit()
                    break

                data_len = struct.unpack('>I', header)[0]

                body_bytes = self.recv_all(data_len)
                if not body_bytes:
                    break
                    
                msg = body_bytes.decode('utf-8')

                # 클라이언트로부터 데이터 수신 대기
                # data = self.client_socket.recv(1024)
                # if not data:
                #     break
                # msg = data.decode('utf-8')
                self.msg_received.emit(self.client_socket, msg)

            except (ConnectionResetError, BrokenPipeError):
                # 2. 스트림릿이 강제 종료되거나 네트워크가 끊긴 경우
                print("클라이언트와 연결이 비정상적으로 끊어졌습니다.")
                break
            except OSError:
                # 3. 메인 스레드에서 client_socket.close()를 호출해서 recv()가 깨어난 경우
                print("서버에서 강제로 소켓을 닫았습니다.")
                break
            except Exception as e:
                print(f"알 수 없는 에러: {e}")
                break
        
        # while문을 빠져나오면 자원 정리
        self.cleanup()

    def cleanup(self):
        self.is_running = False
        try:
            self.client_socket.close()
        except:
            pass
        # UI 쪽에 스레드가 끝났음을 알림
        self.disconnected.emit(self)

    def stop(self):
        """메인 UI에서 강제로 스레드를 멈출 때 호출하는 메서드"""
        self.is_running = False
        try:
            # 소켓을 닫으면 run() 안의 recv()가 OSError를 발생시키며 즉시 대기가 풀림
            self.client_socket.close()
        except:
            pass

# 서버 연결 수락용 메인 스레드
class ServerThread(QThread):
    new_client_signal = pyqtSignal(object, str) # 소켓, IP

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.running = True
        self.server_socket = None

    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('', self.port))
            self.server_socket.listen(5)
            print(f"Server started on port {self.port}")

            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    self.new_client_signal.emit(client_socket, addr[0])
                except OSError:
                    break
        except Exception as e:
            print(f"Server Error: {e}")

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.client_handlers = {} # {socket_object: ClientHandler_thread}
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.connectSignalsSlots()
        self.ui.speed_factor_val.setValidator(QIntValidator(1,2000))

        self.is_paused = False

        self.timer = QTimer()
        # self.timer.timeout.connect(self.send_packet)
        # self.timer.timeout.connect(self.send_packet_by_time)
        self.timer.timeout.connect(self.on_timer_timeout)
        # self.init_ui()

        # [1] 변수 초기화 (AttributeError 방지)
        self.chunk_iterator = None  # 파일을 조금씩 읽어오는 친구
        self.buffer_df = pd.DataFrame() # 읽어온 데이터를 잠시 보관하는 그릇
        self.is_first_chunk = True   # 첫 번째 덩어리인지 확인용
        
        self.csv_path = None        # 파일 경로 저장
        self.file_handle = None     # 파일 객체 (open 상태 유지)
        self.csv_reader = None      # CSV Reader 객체
        self.current_line_count = 0 # 현재까지 보낸 라인 수 (로그 표시용)

        # 시뮬레이션 관련 변수들 초기화
        self.reader = None
        self.next_row = None
        self.sim_current_time = None
        self.real_last_tick = None
        self.speed_factor = 1
        self.next_row_buffer = None

        self.delta_seconds = 0

        self.ui.speed_factor_val.setText("1")


    def connectSignalsSlots(self):
        self.ui.btn_select_file.clicked.connect(self.select_csv_file)
        self.ui.btn_start.clicked.connect(self.start_server)
        self.ui.btn_stop.clicked.connect(self.stop_server)
        self.ui.btn_disconnect.clicked.connect(self.disconnect_selected_client)
        self.ui.btn_send.clicked.connect(self.send_message)
        self.ui.btn_send_packet.clicked.connect(self.start_sending)
        self.ui.btn_pause_packet.clicked.connect(self.toggle_pause)
        self.ui.btn_send_packet.setEnabled(False)
        self.ui.btn_pause_packet.setEnabled(False)
        self.ui.speed_factor_slider.valueChanged.connect(self.slider_speed_factor_value)
        self.ui.speed_factor_val.textChanged.connect(self.text_speed_factor_value)

        #program restart
        self.ui.reset_program.clicked.connect(self.restart_program)
        

    def toggle_pause(self):
        if not self.reader:
            return
        if not self.is_paused:
            # --- 일시정지 시점 ---
            self.ui.btn_pause_packet.setText("다시시작")
            self.timer.stop()
            self.is_paused = True
            print("시뮬레이션 일시정지")
        else:
            self.ui.btn_pause_packet.setText("일시정지")
            # --- 재개 시점 ---
            # 중요: 재개하는 순간의 실제 시간을 기록해야 
            # 일시정지 동안 흘러간 시간이 시뮬레이션에 더해지지 않음
            self.real_last_tick = datetime.now() 
            self.timer.start(200)
            self.is_paused = False
            print("시뮬레이션 재개")

    def start_server(self):
        self.server_thread = ServerThread(9999)
        self.server_thread.new_client_signal.connect(self.accept_new_client)
        self.server_thread.start()
        
        self.ui.btn_start.setEnabled(False)
        self.ui.btn_stop.setEnabled(True)
        self.ui.log_browser.append("[System] 서버가 시작되었습니다.")

    def stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait()
        
        # 모든 클라이언트 연결 종료
        self.disconnect_all_clients()
        
        self.ui.btn_start.setEnabled(True)
        self.ui.btn_stop.setEnabled(False)
        self.ui.log_browser.append("[System] 서버가 종료되었습니다.")

    def accept_new_client(self, client_socket, ip):
        # 1. UI 테이블에 추가
        row = self.ui.client_table.rowCount()
        self.ui.client_table.insertRow(row)
        
        # [핵심] IP 아이템에 소켓 객체를 숨겨둠 (UserRole) -> 인덱스가 바뀌어도 객체 추적 가능
        ip_item = QTableWidgetItem(ip)
        ip_item.setData(Qt.ItemDataRole.UserRole, client_socket) 
        
        self.ui.client_table.setItem(row, 0, ip_item)
        self.ui.client_table.setItem(row, 1, QTableWidgetItem("온라인"))

        # 2. 클라이언트별 수신 스레드 생성
        handler = ClientHandler(client_socket, ip)
        handler.msg_received.connect(self.process_client_message)
        handler.disconnected.connect(self.handle_disconnection)
        handler.finished.connect(handler.deleteLater)
        handler.start()
        
        self.client_handlers[client_socket] = handler
        self.ui.log_browser.append(f"[접속] {ip} 연결됨")

    def disconnect_selected_client(self):
        row = self.ui.client_table.currentRow()
        if row < 0:
            return
        
        # 숨겨둔 소켓 객체 꺼내기
        item = self.ui.client_table.item(row, 0)
        client_socket = item.data(Qt.ItemDataRole.UserRole)
        
        # ⭐ 직접 소켓을 닫지 않고, 스레드의 stop() 호출
        if client_socket in self.client_handlers:
            handler = self.client_handlers[client_socket]
            handler.stop() 
            # stop() 내에서 is_running = False 및 socket.close()가 실행되며
            # 안전하게 run() 루프를 빠져나오고 disconnected 시그널이 발생함

    def handle_disconnection(self, thread):
        # 1. 전달받은 스레드 객체에서 실제 소켓을 꺼냅니다.
        client_socket = thread.client_socket

        # 2. 딕셔너리에서 해당 스레드 제거
        if client_socket in self.client_handlers:
            del self.client_handlers[client_socket]

        # 3. UI 테이블에서 해당 소켓을 가진 행(Row) 찾아서 삭제
        for row in range(self.ui.client_table.rowCount()):
            item = self.ui.client_table.item(row, 0)
            
            # item.data 안에는 소켓이 들어있으므로, 정상적으로 일치하는지 비교 가능!
            if item and item.data(Qt.ItemDataRole.UserRole) == client_socket:
                ip = item.text()
                self.ui.client_table.removeRow(row)
                self.ui.log_browser.append(f"[종료] {ip} 연결 해제됨")
                break

    def disconnect_all_clients(self):
        # 테이블 역순으로 순회하며 모두 닫기
        for row in range(self.ui.client_table.rowCount() -1, -1, -1):
            item = self.ui.client_table.item(row, 0)
            sock = item.data(Qt.ItemDataRole.UserRole)
            if sock: sock.close()
            
    def select_csv_file(self):
        """CSV 파일 경로만 저장하고, 실제 데이터는 읽지 않음 (메모리 절약)"""
        fname, _ = QFileDialog.getOpenFileName(self, 'CSV 파일 선택', '', 'CSV Files (*.csv)')
        if not fname:
            return

        self.csv_path = fname
        self.ui.selected_file.setText(f"{os.path.basename(fname)}")
        self.ui.log_browser.append(f"[System] 파일 경로 설정 완료: {fname}")
        
        # 파일이 정상적인지 헤더만 살짝 읽어보기
        try:
            with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                self.ui.log_browser.append(f"[Check] 컬럼 확인: {headers}")
                self.ui.btn_send_packet.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "파일 오류", f"파일을 읽을 수 없습니다: {e}")
            self.csv_path = None

    def load_next_chunk(self):
        try:
            # 다음 10,000개 읽기 (여기서는 아직 문자열일 수 있음)
            next_chunk = next(self.reader)
            
            # [핵심 수정] 읽어온 데이터의 timestamp를 강제로 datetime으로 변환
            # format='mixed'는 다양한 형식을 알아서 처리, utc=True는 시간대 통일
            next_chunk['timestamp'] = pd.to_datetime(next_chunk['timestamp'], format='mixed', utc=True)
            
            # 기존 버퍼 뒤에 이어 붙이기
            self.buffer_df = pd.concat([self.buffer_df, next_chunk], ignore_index=True)
            
            # 디버깅용 로그 (필요시 삭제)
            print(f">>> 버퍼 리필 완료. 현재 버퍼 크기: {len(self.buffer_df)}")
            
        except StopIteration:
            print("파일의 끝에 도달했습니다.")
            # 더 이상 읽을 파일이 없으므로 타이머는 buffer_df가 다 비워지면 멈춥니다.
        except Exception as e:
            print(f"청크 로드 중 오류: {e}")
            self.timer.stop() # 심각한 오류면 멈춤

    def prepare_simulation(self, speed_factor):
        # 2. 기존 타이머가 돌고 있다면 중지
        self.timer.stop()

        # chunksize 설정
        self.reader = pd.read_csv(self.csv_path, chunksize=10000, iterator=True)
        
        try:
            # 첫 번째 청크 로드
            self.buffer_df = next(self.reader)
            
            # [수정] 강제 형변환 (utc=True로 통일)
            self.buffer_df['timestamp'] = pd.to_datetime(self.buffer_df['timestamp'], format='mixed', utc=True)
            
            # 시뮬레이션 시작 시간 설정
            self.sim_current_time = self.buffer_df.iloc[0]['timestamp']
            self.real_last_tick = datetime.now()
            
            self.timer.start(200) # 0.2초 간격
            print(f"시뮬레이션 시작: {self.sim_current_time}")
            
        except Exception as e:
            print(f"초기화 오류: {e}")

    def on_timer_timeout(self):
        if not self.csv_path:
            QMessageBox.warning(self, "알림", "csv파일을 로드하세요.")
            self.stop_sending()
            return
        
        if self.buffer_df is None or self.buffer_df.empty:
            return
        
        # 1. 타이머가 불린 사이 실제 현실에서 흐른 물리적 시간(dt) 계산
        now = datetime.now()
        real_delta_seconds = (now - self.real_last_tick).total_seconds()
        self.real_last_tick = now # 다음 계산을 위해 업데이트
        
        # 2. 시뮬레이션 시간 업데이트 (실제 흐른 시간 * 배속)
        # 예: 현실에서 0.1초 흘렀고 10배속이면, 시뮬레이션 시간은 1초 전진
        self.sim_current_time += timedelta(seconds=real_delta_seconds * self.speed_factor)
        self.delta_seconds += real_delta_seconds * self.speed_factor

        time_str = self.sim_current_time.strftime('%Y-%m-%d %H:%M:%S')
        self.ui.sim_current_time.setText(f"현재 시뮬레이션 시간: {time_str}")

        # ---------------------------------------------------------
        # [핵심] 벡터 연산으로 보낼 데이터 한 번에 추출 (속도 매우 빠름)
        # ---------------------------------------------------------
        
        # 2. 현재 시뮬레이션 시간보다 과거인 데이터 찾기 (Boolean Indexing)
        mask = self.buffer_df['timestamp'] <= self.sim_current_time
        
        # 보낼 데이터가 하나라도 있다면
        if mask.any():
            # (1) 보낼 데이터만 잘라냄
            send_df = self.buffer_df[mask]
            
            # (2) 남은 데이터로 버퍼 업데이트 (보낸 건 버퍼에서 삭제)
            self.buffer_df = self.buffer_df[~mask]
            
            # (3) DataFrame -> List of Dict 변환 (Loop보다 훨씬 빠름)
            packet_list = send_df.to_dict('records')
            
            # 3. 소켓 전송 (한 번에 묶어서 보냄)
            self.broadcast_packets(packet_list, time_str)

            print(f"[{len(packet_list)}건] 고속 전송 완료")

        if self.delta_seconds >= 1.0:
            self.timeUpdate_packets(time_str)
            self.delta_seconds -= 1

        # 4. 버퍼 관리 (데이터가 다 떨어졌거나 얼마 안 남았으면 리필)
        if len(self.buffer_df) < 100: # 예: 100개 미만 남으면 다음 청크 로드
            self.load_next_chunk()

    def broadcast_packets(self, data_chunk, curr_server_time: str):
        if not data_chunk:
            print("데이터가 없습니다")
            return       
        
        # 연결된 모든 소켓에게 패킷을 전송하도록 변경
         # 1. 테이블의 전체 행 수 확인
        row_count = self.ui.client_table.rowCount()

        for i in range(row_count):
            item = self.ui.client_table.item(i, 0)

            if item:
                client_socket = item.data(Qt.ItemDataRole.UserRole)
        
                try:
                    if client_socket:
                        # 데이터 전송 (프로토콜: 헤더(길이) + JSON바디)
                        json_str = json.dumps(data_chunk, default=str)
                        json_bytes = json_str.encode('utf-8')
                        
                        DATA_TYPE = 1   # 메세지는 0, DB형식은 1, 시간만 업데이트는 2

                        time_bytes = curr_server_time.encode('utf-8')

                        # 헤더
                        # field1: 데이터타입 (메세지는 0, DB형식은 1)
                        # field2: 서버의 현재 모의 시간(19바이트 문자열 -> 19s, ex. 2022-12-01 00:00:03)
                        # field3: 데이터 길이 (4바이트 Big Endian)
                        header = struct.pack('>B19sI', DATA_TYPE, time_bytes, len(json_bytes))
                        
                        client_socket.sendall(header + json_bytes)
                except Exception as e:
                    self.ui.log_browser.append(f"[Socket Error] {e}")
                    self.stop_sending()

        #누적 전송패킷 계산
        self.current_line_count += len(data_chunk)
        self.ui.log_browser.append(f"[Send] {len(data_chunk)}건 전송 (누적: {self.current_line_count})")

    def timeUpdate_packets(self, curr_server_time: str):
        row_count = self.ui.client_table.rowCount()
        for i in range(row_count):
            item = self.ui.client_table.item(i, 0)

            if item:
                client_socket = item.data(Qt.ItemDataRole.UserRole)
        
                try:
                    if client_socket:
                        DATA_TYPE = 2   # 메세지는 0, DB형식은 1, 시간만 업데이트는 2

                        time_str = "0"
                        time_json = time_str.encode('utf-8')

                        time_bytes = curr_server_time.encode('utf-8')

                        # 헤더
                        # field1: 데이터타입 (메세지는 0, DB형식은 1)
                        # field2: 서버의 현재 모의 시간(19바이트 문자열 -> 19s, ex. 2022-12-01 00:00:03)
                        # field3: 데이터 길이 (4바이트 Big Endian)
                        header = struct.pack('>B19sI', DATA_TYPE, time_bytes, len(time_json))
                        
                        client_socket.sendall(header + time_json)
                except Exception as e:
                    self.ui.log_browser.append(f"[Socket Timeupdate Error] {e}")
                    self.stop_sending()

    def send_message(self):
        row = self.ui.client_table.currentRow()
        text = self.ui.msg_edit.toPlainText()
        if row < 0 or not text:
            QMessageBox.warning(self, "알림", "대상을 선택하고 메시지를 입력하세요.")
            return

        item = self.ui.client_table.item(row, 0)
        client_socket = item.data(Qt.ItemDataRole.UserRole)
        status_item = self.ui.client_table.item(row, 1)

        try:
            text_bytes = text.encode('utf-8')
            
            DATA_TYPE = 0   # 메세지는 0, DB형식은 1

            header = struct.pack('>BI', DATA_TYPE, len(text_bytes))

            client_socket.sendall(header + text_bytes)

            self.ui.msg_edit.clear()
            
            # [수정] 2. 전송중 표시 후 2초 뒤 복귀
            status_item.setText("데이터 전송중...")
            # QTimer.singleShot(밀리초, 콜백함수)
            QTimer.singleShot(2000, lambda: self.reset_status(status_item))
            
        except Exception as e:
            status_item.setText("전송 실패")
            self.ui.log_browser.append(f"[오류] 전송 실패: {e}")

    def start_sending(self):
        if not self.csv_path:
            QMessageBox.warning(self, "경고", "CSV 파일이 선택되지 않았습니다.")
            return
        
        # 전송 시작 시 파일 열기 (Streaming 시작)
        try:
            if self.file_handle is None:
                self.file_handle = open(self.csv_path, 'r', encoding='utf-8-sig')
                self.csv_reader = csv.DictReader(self.file_handle)
                self.current_line_count = 0
                self.ui.log_browser.append("[Streaming] 파일 스트림 오픈")
            self.prepare_simulation(self.speed_factor)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 열기 실패: {e}")
            return

        self.ui.btn_send_packet.setEnabled(False)
        self.ui.btn_pause_packet.setEnabled(True)
        # self.timer.start(1000) # 0.1초 간격 전송

    def stop_sending(self):
        self.timer.stop()
        self.ui.btn_send_packet.setEnabled(True)
        self.ui.btn_pause_packet.setEnabled(False)

    def reset_status(self, item):
        # 아이템이 삭제되지 않고 존재할 때만 텍스트 변경
        try:
            if item: 
                item.setText("온라인")
        except:
            pass

    def process_client_message(self, client_socket, msg):
        # [수정] 3. 클라이언트 메시지 UI 전시
        # 어떤 IP인지 찾기 위해 테이블 검색
        sender_ip = "Unknown"
        for row in range(self.ui.client_table.rowCount()):
            item = self.ui.client_table.item(row, 0)
            if item.data(Qt.ItemDataRole.UserRole) == client_socket:
                sender_ip = item.text()
                break
        
        self.ui.log_browser.append(f"[{sender_ip}]: {msg}")

    # 시간배속 싱크
    def slider_speed_factor_value(self):
        float_val = self.ui.speed_factor_slider.value()
        if float_val == self.speed_factor:
            return
        self.speed_factor = float_val
        self.sync_speed_factor_value()

    def text_speed_factor_value(self):
        float_val = self.ui.speed_factor_val.text().strip()
        if float_val == "":
            return
        if int(float_val) == self.speed_factor:
            return
        self.speed_factor = int(float_val)
        self.sync_speed_factor_value()

    def sync_speed_factor_value(self):
        final_val = self.speed_factor
        if self.ui.speed_factor_slider.value() != final_val:
            self.ui.speed_factor_slider.setValue(int(final_val))
        if self.ui.speed_factor_val.text().strip() != str(final_val):
            self.ui.speed_factor_val.setText(str(final_val))

    def restart_program(self):
        """현재 프로그램을 종료하고 다시 시작합니다."""
        print("프로그램을 재시작합니다...")
        
        # 1. 현재 실행 중인 파이썬 인터프리터 경로 가져오기 (python.exe 등)
        python = sys.executable
        
        # 2. 실행 중인 스크립트 파일과 인자값 유지
        # os.execv는 현재 프로세스를 새로 시작하는 프로세스로 완전히 대체합니다.
        os.execv(python, [python] + sys.argv)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())