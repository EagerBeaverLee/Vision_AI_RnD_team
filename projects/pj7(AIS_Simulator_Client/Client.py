import sys
import socket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextBrowser, QMessageBox)
from PyQt6.QtCore import QThread, pyqtSignal

class ReceiveThread(QThread):
    msg_signal = pyqtSignal(str)
    disconnect_signal = pyqtSignal()

    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.running = True

    def run(self):
        while self.running:
            try:
                data = self.socket.recv(1024)
                if not data:
                    self.disconnect_signal.emit()
                    break
                msg = data.decode('utf-8')
                self.msg_signal.emit(msg)
            except:
                self.disconnect_signal.emit()
                break

    def stop(self):
        self.running = False

class ClientWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.socket = None
        self.recv_thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PyQt6 Socket Client (양방향)")
        self.resize(400, 500)

        layout = QVBoxLayout()

        # 1. 접속 정보
        conn_layout = QHBoxLayout()
        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("9999")
        self.btn_connect = QPushButton("서버 접속")
        self.btn_connect.clicked.connect(self.connect_server)

        conn_layout.addWidget(QLabel("IP:"))
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_input)
        conn_layout.addWidget(self.btn_connect)
        layout.addLayout(conn_layout)

        # 2. 채팅창 (수신 메시지)
        layout.addWidget(QLabel("서버 메시지 / 로그:"))
        self.text_display = QTextBrowser()
        layout.addWidget(self.text_display)

        # 3. [추가] 송신 메시지 입력
        layout.addWidget(QLabel("서버로 보낼 메시지:"))
        input_layout = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.btn_send = QPushButton("전송")
        self.btn_send.clicked.connect(self.send_message)
        self.msg_input.returnPressed.connect(self.send_message) # 엔터키 전송

        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(self.btn_send)
        layout.addLayout(input_layout)

        self.setLayout(layout)
        self.toggle_ui(False) # 접속 전에는 입력 비활성화

    def toggle_ui(self, connected):
        self.msg_input.setEnabled(connected)
        self.btn_send.setEnabled(connected)
        self.btn_connect.setEnabled(not connected)
        self.ip_input.setEnabled(not connected)
        self.port_input.setEnabled(not connected)

    def connect_server(self):
        ip = self.ip_input.text()
        try:
            port = int(self.port_input.text())
        except ValueError:
            QMessageBox.critical(self, "오류", "포트 번호는 숫자여야 합니다.")
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((ip, port))
            
            self.text_display.append(f"[System] Connected to {ip}:{port}")
            self.toggle_ui(True)

            self.recv_thread = ReceiveThread(self.socket)
            self.recv_thread.msg_signal.connect(self.update_msg)
            self.recv_thread.disconnect_signal.connect(self.on_disconnected)
            self.recv_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "접속 오류", f"서버에 접속할 수 없습니다.\n{e}")

    def send_message(self):
        text = self.msg_input.text()
        if not text:
            return
        
        try:
            self.socket.sendall(text.encode('utf-8'))
            self.text_display.append(f"[Me]: {text}") # 내가 보낸 것도 화면에 표시
            self.msg_input.clear()
        except Exception as e:
            self.text_display.append(f"[Error] 전송 실패: {e}")
            self.on_disconnected()

    def update_msg(self, msg):
        self.text_display.append(f"[Server]: {msg}")

    def on_disconnected(self):
        self.text_display.append("[System] Disconnected from server.")
        self.toggle_ui(False)
        if self.socket:
            self.socket.close()

    def closeEvent(self, event):
        if self.recv_thread:
            self.recv_thread.stop()
        if self.socket:
            self.socket.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec())