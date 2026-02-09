import sys, os, csv, json
import socket
import time
import struct
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextBrowser, QTextEdit, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QMainWindow, QFileDialog)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
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
            except:
                break
        
        # 루프 탈출 시 연결 종료 신호 보냄
        self.disconnected.emit(self.client_socket)

    def stop(self):
        self.running = False

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

        self.timer = QTimer()
        self.timer.timeout.connect(self.send_packet)
        # self.init_ui()

        self.csv_path = None        # 파일 경로 저장
        self.file_handle = None     # 파일 객체 (open 상태 유지)
        self.csv_reader = None      # CSV Reader 객체
        self.current_line_count = 0 # 현재까지 보낸 라인 수 (로그 표시용)

    def connectSignalsSlots(self):
        self.ui.btn_select_file.clicked.connect(self.select_csv_file)
        self.ui.btn_start.clicked.connect(self.start_server)
        self.ui.btn_stop.clicked.connect(self.stop_server)
        self.ui.btn_disconnect.clicked.connect(self.disconnect_selected_client)
        self.ui.btn_send.clicked.connect(self.send_message)
        self.ui.btn_send_packet.clicked.connect(self.start_sending)
        self.ui.btn_pause_packet.clicked.connect(self.stop_sending)
        self.ui.btn_send_packet.setEnabled(False)
        self.ui.btn_pause_packet.setEnabled(False)

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
        
        if client_socket:
            client_socket.close() # 소켓을 닫으면 Handler에서 disconnected 시그널이 발생하여 UI 정리됨

    def handle_disconnection(self, client_socket):
        # 소켓 객체로 테이블에서 해당 행 찾아서 삭제 (인덱스 밀림 방지)
        for row in range(self.ui.client_table.rowCount()):
            item = self.ui.client_table.item(row, 0)
            if item.data(Qt.ItemDataRole.UserRole) == client_socket:
                ip = item.text()
                self.ui.client_table.removeRow(row)
                self.ui.log_browser.append(f"[해제] {ip} 연결 끊김")
                
                # 핸들러 정리
                if client_socket in self.client_handlers:
                    self.client_handlers[client_socket].stop()
                    del self.client_handlers[client_socket]
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

    def send_packet(self):
        row = self.ui.client_table.currentRow()
        if row < 0 or not self.csv_path:
            QMessageBox.warning(self, "알림", "대상을 선택하고 csv파일을 로드하세요.")
            return
        
        item = self.ui.client_table.item(row, 0)
        client_socket = item.data(Qt.ItemDataRole.UserRole)

        if not client_socket:
            self.stop_sending()
            return
        
        batch_size = self.ui.sending_size.value()
        data_chunk = []

        try:
            for _ in range(batch_size):
                try:
                    # iterator에서 다음 줄 가져오기
                    row = next(self.csv_reader)
                    data_chunk.append(row)
                    self.current_line_count += 1
                except StopIteration:
                    # 파일 끝에 도달하면 파일 닫고 다시 열기 (Loop)
                    self.log_browser.append("[System] 파일 끝 도달 스트리밍 종료")
                    self.file_handle.close()
                    self.stop_sending()
                    break
        except Exception as e:
            self.ui.log_browser.append(f"[Read Error] {e}")
            self.stop_sending()
            return
        
        if not data_chunk:
            return
        
        # 데이터 전송 (프로토콜: 헤더(길이) + JSON바디)
        try:
            json_str = json.dumps(data_chunk)
            json_bytes = json_str.encode('utf-8')

            DATA_TYPE = 1   # 메세지는 0, DB형식은 1
            
            # 헤더: 데이터 길이 (4바이트 Big Endian)
            header = struct.pack('>BI', DATA_TYPE, len(json_bytes))
            
            client_socket.sendall(header + json_bytes)
            
            # 로그 출력 (너무 자주 찍히지 않게)
            if self.current_line_count % (batch_size * 5) == 0 or self.current_line_count < batch_size * 2:
                self.ui.log_browser.append(f"[Send] {len(data_chunk)}건 전송 (누적: {self.current_line_count})")
            else:
                self.ui.log_browser.append(f"[Send] {len(data_chunk)}건 전송")
                
        except Exception as e:
            self.ui.log_browser.append(f"[Socket Error] {e}")
            self.stop_sending()

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
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 열기 실패: {e}")
            return

        self.ui.btn_send_packet.setEnabled(False)
        self.ui.btn_pause_packet.setEnabled(True)
        self.timer.start(1000) # 0.1초 간격 전송

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())