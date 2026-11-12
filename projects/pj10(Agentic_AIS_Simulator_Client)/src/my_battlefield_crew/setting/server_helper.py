import socket
import time
from PyQt6.QtCore import QThread, QUrl, pyqtSignal

class ServerWaitWorker(QThread):
    server_ready = pyqtSignal()

    def __init__(self, host: str, port: int, timeout: float = 15.0):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self):
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            # 💡 8504 포트가 실제로 열렸는지 0.2초마다 핑(ping)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)
                result = sock.connect_ex((self.host, self.port))
                if result == 0:  # 포트 바인딩 완료
                    time.sleep(0.3)  # HTTP 엔드포인트 준비 완료 안정화 대기
                    self.server_ready.emit()
                    return
            time.sleep(0.2)
        print(f"[Warning] {self.host}:{self.port} 서버 응답 시간 초과")