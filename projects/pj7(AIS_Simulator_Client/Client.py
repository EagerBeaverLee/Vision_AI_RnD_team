import sys, os
import socket
import sqlite3
import json
import struct
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextBrowser, QMessageBox)
from PyQt6.QtCore import QThread, pyqtSignal

# DB 핸들링 함수
def init_db():
    db_path = "ships.db"

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"{db_path} 파일이 삭제되었습니다.")
        except Exception as e:
            # QMessageBox.critical("오류", f"{e}")
            print(f"{e}")
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
            course INTEGER,
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
                    print(f"DB 저장 완료: {len(data_list)} 행")
            except Exception as e:
                self.log_signal.emit(f"에러 발생: {e}")
                self.disconnect_signal.emit()
                break

    def stop(self):
        self.running = False

class ClientWindow(QWidget):
    def __init__(self):
        super().__init__()
        init_db()
        self.socket = None
        self.recv_thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PyQt6 Socket Client (양방향)")
        self.resize(400, 500)

        layout = QVBoxLayout()

        # 1. 접속 정보
        conn_layout = QHBoxLayout()
        self.ip_input = QLineEdit("192.168.0.109")
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
            self.recv_thread.msg_received.connect(self.process_server_message)
            self.recv_thread.log_signal.connect(self.update_log)
            self.recv_thread.log_packet.connect(self.update_packet_log)
            self.recv_thread.disconnect_signal.connect(self.on_disconnected)
            self.recv_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "접속 오류", f"서버에 접속할 수 없습니다.\n{e}")

    def send_message(self):
        text = self.msg_input.text()
        if not text:
            return
        
        try:
            text_bytes = text.encode('utf-8')
            data_len = len(text_bytes)
            header = struct.pack('>I', data_len)

            self.socket.sendall(header + text_bytes)
            self.text_display.append(f"[Me]: {text}") # 내가 보낸 것도 화면에 표시
            self.msg_input.clear()
        except Exception as e:
            self.text_display.append(f"[Error] 전송 실패: {e}")
            self.on_disconnected()

    def update_log(self, msg):
        self.text_display.append(msg)

    def update_packet_log(self, i, packet):
        # print(f"Packet[{i}]" + str(packet))
        display_text = f"[{i}] Packet: {' | '.join(map(str, packet))} |"
        self.text_display.append(display_text)

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

    def process_server_message(self, msg):
        self.text_display.append(f"[Server]: {msg}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec())