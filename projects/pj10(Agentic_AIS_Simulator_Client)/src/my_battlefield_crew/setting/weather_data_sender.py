import requests
from PyQt6.QtCore import pyqtSignal, QThread

class DataSenderThread(QThread):
    # 전송 성공/실패 여부를 메인 UI에 알려주기 위한 시그널
    result_signal = pyqtSignal(bool, str) 

    def __init__(self, url, value_data):
        super().__init__()
        self.url = url
        self.value_data = value_data

    def run(self):
        """이 안의 코드는 백그라운드에서 실행되므로 화면이 멈추지 않습니다."""
        try:
            # 여기서 무거운 전송 작업 수행
            r = requests.post(self.url, json=self.value_data, timeout=5)
            
            if r.status_code == 200:
                self.result_signal.emit(True, "전송 성공")
            else:
                self.result_signal.emit(False, f"서버 에러: {r.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.result_signal.emit(False, f"통신 실패: {str(e)}")