import sys, os
import socket
import struct
import json
import sqlite3
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextBrowser, QMessageBox)
from PyQt6.QtCore import QThread, pyqtSignal

# 초기 DB 설정
def init_db():
    db_path = "ships.db"

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"{db_path} 파일이 삭제되었습니다.")
    else:
        print("삭제할 DB 파일이 존재하지 않습니다.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # CSV 필드에 맞춰 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ship_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ShipType TEXT,
            ShipName TEXT,
            mmsi TEXT,
            timestamp TEXT,
            course TEXT,
            speed TEXT,
            longitude TEXT,
            latitude TEXT,
            higher_types TEXT,
            radius TEXT
        )
    """)
    conn.commit()
    conn.close()

class ReceiveThread(QThread):
    log_signal = pyqtSignal(str)
    disconnect_signal = pyqtSignal()

    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.running = True

    def recv_all(self, length):
        """정해진 길이만큼 데이터를 확실하게 다 읽어오는 함수"""
        data = b''
        while len(data) < length:
            try:
                packet = self.socket.recv(length - len(data))
                if not packet:
                    return None
                data += packet
            except:
                return None
        return data

    def run(self):
        # 스레드별 독립적인 DB 연결
        conn = sqlite3.connect("ships.db")
        cursor = conn.cursor()

        while self.running:
            try:
                # 1. 헤더(4바이트) 읽기 (데이터 길이)
                header = self.recv_all(4)
                if not header:
                    self.disconnect_signal.emit()
                    break
                
                # 2. 데이터 길이 파악
                data_len = struct.unpack('>I', header)[0]
                
                # 3. 본문(JSON) 읽기
                body_bytes = self.recv_all(data_len)
                if not body_bytes:
                    break

                # 4. 파싱 및 DB 저장
                json_str = body_bytes.decode('utf-8')
                data_list = json.loads(json_str) # List of Dictionaries

                if not data_list:
                    continue

                # executemany를 위한 튜플 리스트 변환
                # CSV에서 읽어온 값은 모두 문자열일 수 있으므로 DB 스키마를 유연하게(TEXT) 잡거나
                # 여기서 형변환을 해주는 것이 좋습니다. (여기선 안전하게 그대로 저장)
                db_tuples = []
                for item in data_list:
                    db_tuples.append((
                        item.get("ShipType"), 
                        item.get("ShipName"), 
                        item.get("mmsi"),
                        item.get("timestamp"), 
                        item.get("course"), 
                        item.get("speed"),
                        item.get("longitude"), 
                        item.get("latitude"), 
                        item.get("higher_types"), 
                        item.get("radius")
                    ))
                
                query = """
                    INSERT INTO ship_logs 
                    (ShipType, ShipName, mmsi, timestamp, course, speed, longitude, latitude, higher_types, radius)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.executemany(query, db_tuples)
                conn.commit()

                # 로그 출력 (UI 부하를 줄이기 위해 간단히)
                # self.log_signal.emit(f"수신 및 저장 완료: {len(data_list)} 행")
                self.log_signal.emit(f"수신 및 저장 완료: {data_list}")

            except Exception as e:
                self.log_signal.emit(f"처리 에러: {e}")
                break
        
        conn.close()

    def stop(self):
        self.running = False

class ClientWindow(QWidget):
    def __init__(self):
        super().__init__()
        init_db() # 앱 시작 시 DB/테이블 생성 확인
        self.socket = None
        self.recv_thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("DB Saver Client")
        self.resize(400, 450)
        layout = QVBoxLayout()

        # 접속 UI
        conn_layout = QHBoxLayout()
        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("9999")
        self.btn_connect = QPushButton("서버 접속")
        self.btn_connect.clicked.connect(self.connect_server)
        conn_layout.addWidget(QLabel("IP:"))
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(self.port_input)
        conn_layout.addWidget(self.btn_connect)
        layout.addLayout(conn_layout)

        # 로그창
        self.log_display = QTextBrowser()
        layout.addWidget(self.log_display)
        self.setLayout(layout)

    def connect_server(self):
        ip = self.ip_input.text()
        port_str = self.port_input.text()
        
        try:
            port = int(port_str)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((ip, port))
            
            self.log_display.append(f"서버({ip}:{port})에 접속되었습니다.")
            self.btn_connect.setEnabled(False)

            self.recv_thread = ReceiveThread(self.socket)
            self.recv_thread.log_signal.connect(self.update_log)
            self.recv_thread.disconnect_signal.connect(self.on_disconnected)
            self.recv_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "접속 오류", f"연결 실패: {e}")

    def update_log(self, msg):
        # 로그창 내용이 너무 많아지면 메모리 정리
        if len(self.log_display.toPlainText()) > 10000:
            self.log_display.clear()
        self.log_display.append(msg)

    def on_disconnected(self):
        self.log_display.append("서버와 연결이 끊어졌습니다.")
        self.btn_connect.setEnabled(True)
        if self.socket:
            self.socket.close()

    def closeEvent(self, event):
        if self.recv_thread: 
            self.recv_thread.stop()
            self.recv_thread.wait()
        if self.socket: 
            self.socket.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec())