import sys
import socket
import time
import struct
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextBrowser, QTextEdit, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QMainWindow)
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
        # self.init_ui()

    def connectSignalsSlots(self):
        self.ui.btn_start.clicked.connect(self.start_server)
        self.ui.btn_stop.clicked.connect(self.stop_server)
        self.ui.btn_disconnect.clicked.connect(self.disconnect_selected_client)
        self.ui.btn_send.clicked.connect(self.send_message)

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
            data_len = len(text_bytes)
            header = struct.pack('>I', data_len)

            client_socket.sendall(header + text_bytes)
            
            # [수정] 2. 전송중 표시 후 2초 뒤 복귀
            status_item.setText("데이터 전송중...")
            # QTimer.singleShot(밀리초, 콜백함수)
            QTimer.singleShot(2000, lambda: self.reset_status(status_item))
            
        except Exception as e:
            status_item.setText("전송 실패")
            self.ui.log_browser.append(f"[오류] 전송 실패: {e}")

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