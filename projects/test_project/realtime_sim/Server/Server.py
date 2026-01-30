import sys
import socket
import json
import struct
import csv
import os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QSpinBox, QTextBrowser, QMessageBox, QFileDialog)
from PyQt6.QtCore import QTimer

class ServerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.server_socket = None
        self.client_socket = None
        
        # 타이머 설정
        self.timer = QTimer()
        self.timer.timeout.connect(self.send_realtime_data)
        
        # CSV 스트리밍 관련 변수
        self.csv_path = None        # 파일 경로 저장
        self.file_handle = None     # 파일 객체 (open 상태 유지)
        self.csv_reader = None      # CSV Reader 객체
        self.current_line_count = 0 # 현재까지 보낸 라인 수 (로그 표시용)
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Large CSV Streaming Server")
        self.resize(500, 500)
        
        layout = QVBoxLayout()

        # 1. 파일 선택 및 서버 오픈
        file_layout = QHBoxLayout()
        self.lbl_status = QLabel("파일 선택 안됨")
        self.btn_load_csv = QPushButton("CSV 파일 선택")
        self.btn_load_csv.clicked.connect(self.select_csv_file)
        file_layout.addWidget(self.lbl_status)
        file_layout.addWidget(self.btn_load_csv)
        layout.addLayout(file_layout)

        self.btn_start_server = QPushButton("서버 오픈 (포트 9999)")
        self.btn_start_server.clicked.connect(self.start_server)
        layout.addWidget(self.btn_start_server)

        # 2. 전송 설정
        setting_layout = QHBoxLayout()
        setting_layout.addWidget(QLabel("전송 단위(줄):"))
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(10, 5000) 
        self.spin_batch.setValue(100)      
        self.spin_batch.setSingleStep(100)
        setting_layout.addWidget(self.spin_batch)
        layout.addLayout(setting_layout)

        # 3. 제어 버튼
        control_layout = QHBoxLayout()
        self.btn_send_start = QPushButton("전송 시작")
        self.btn_send_stop = QPushButton("중지")
        self.btn_send_start.clicked.connect(self.start_sending)
        self.btn_send_stop.clicked.connect(self.stop_sending)
        self.btn_send_start.setEnabled(False)
        self.btn_send_stop.setEnabled(False)
        
        control_layout.addWidget(self.btn_send_start)
        control_layout.addWidget(self.btn_send_stop)
        layout.addLayout(control_layout)

        # 4. 로그창
        self.log_browser = QTextBrowser()
        layout.addWidget(self.log_browser)

        self.setLayout(layout)

    def select_csv_file(self):
        """CSV 파일 경로만 저장하고, 실제 데이터는 읽지 않음 (메모리 절약)"""
        fname, _ = QFileDialog.getOpenFileName(self, 'CSV 파일 선택', '', 'CSV Files (*.csv)')
        if not fname:
            return

        self.csv_path = fname
        self.lbl_status.setText(f"선택됨: {os.path.basename(fname)}")
        self.log_browser.append(f"[System] 파일 경로 설정 완료: {fname}")
        
        # 파일이 정상적인지 헤더만 살짝 읽어보기
        try:
            with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                self.log_browser.append(f"[Check] 컬럼 확인: {headers}")
        except Exception as e:
            QMessageBox.critical(self, "파일 오류", f"파일을 읽을 수 없습니다: {e}")
            self.csv_path = None

    def start_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('', 9999))
            self.server_socket.listen(1)
            self.log_browser.append("[System] 서버 대기중... 클라이언트 접속을 기다립니다.")
            self.server_socket.settimeout(0.1) 
            self.wait_for_client()
        except Exception as e:
            self.log_browser.append(f"[Error] {e}")

    def wait_for_client(self):
        try:
            client, addr = self.server_socket.accept()
            self.client_socket = client
            self.log_browser.append(f"[Connect] {addr[0]} 접속 완료")
            
            if self.csv_path:
                self.btn_send_start.setEnabled(True)
            self.btn_start_server.setEnabled(False)
        except socket.timeout:
            QTimer.singleShot(100, self.wait_for_client)

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
                self.log_browser.append("[Streaming] 파일 스트림 오픈")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 열기 실패: {e}")
            return

        self.btn_send_start.setEnabled(False)
        self.btn_send_stop.setEnabled(True)
        self.timer.start(1000) # 0.1초 간격 전송

    def stop_sending(self):
        self.timer.stop()
        self.btn_send_start.setEnabled(True)
        self.btn_send_stop.setEnabled(False)
        self.log_browser.append("[System] 전송 일시정지 (파일 연결은 유지됨)")
        
        # 완전히 파일을 닫고 싶다면 여기서 self.file_handle.close()를 하고 None 처리를 해도 됨
        # 현재는 '일시정지' 개념이므로 닫지 않음.

    def send_realtime_data(self):
        if not self.client_socket:
            self.stop_sending()
            return

        batch_size = self.spin_batch.value()
        data_chunk = []

        # 배치 사이즈만큼 파일에서 한 줄씩 읽기
        try:
            for _ in range(batch_size):
                try:
                    # iterator에서 다음 줄 가져오기
                    row = next(self.csv_reader)
                    data_chunk.append(row)
                    self.current_line_count += 1
                except StopIteration:
                    # 파일 끝에 도달하면 파일 닫고 다시 열기 (Loop)
                    self.log_browser.append("[Cycle] 파일 끝 도달 -> 처음부터 다시 시작")
                    self.file_handle.close()
                    self.file_handle = open(self.csv_path, 'r', encoding='utf-8-sig')
                    self.csv_reader = csv.DictReader(self.file_handle)
                    self.current_line_count = 0
                    # 끊김 없이 바로 다음 데이터를 이어서 읽고 싶다면 재귀호출 혹은 여기서 continue
                    # 여기서는 이번 턴은 읽은 만큼만 보내고 다음 턴에 처음부터 시작
                    break
        except Exception as e:
            self.log_browser.append(f"[Read Error] {e}")
            self.stop_sending()
            return

        if not data_chunk:
            return

        # 데이터 전송 (프로토콜: 헤더(길이) + JSON바디)
        try:
            json_str = json.dumps(data_chunk)
            json_bytes = json_str.encode('utf-8')
            
            # 헤더: 데이터 길이 (4바이트 Big Endian)
            header = struct.pack('>I', len(json_bytes))
            
            self.client_socket.sendall(header + json_bytes)
            
            # 로그 출력 (너무 자주 찍히지 않게)
            if self.current_line_count % (batch_size * 5) == 0 or self.current_line_count < batch_size * 2:
                self.log_browser.append(f"[Send] {len(data_chunk)}건 전송 (누적: {self.current_line_count})")
                
        except Exception as e:
            self.log_browser.append(f"[Socket Error] {e}")
            self.stop_sending()
            self.client_socket.close()
            self.client_socket = None

    def closeEvent(self, event):
        # 종료 시 파일 안전하게 닫기
        if self.file_handle:
            self.file_handle.close()
        if self.server_socket:
            self.server_socket.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ServerWindow()
    window.show()
    sys.exit(app.exec())