from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
import requests

SERVER_BASE_URL = "http://127.0.0.1:8504"


class RemoteEmbeddingWorker(QThread):
    # UI 연동용 시그널
    progress_changed = pyqtSignal(int)  # 0 ~ 100 퍼센트
    status_message = pyqtSignal(str)  # 상태 텍스트
    finished = pyqtSignal()  # 완료
    cancelled = pyqtSignal()  # 작업 취소됨
    failed = pyqtSignal(str)  # 오류 발생

    def __init__(self, file_paths: list[str], parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self._is_aborted = False

    def run(self):
        url = f"{SERVER_BASE_URL}/api/rag/embed"
        payload = {"file_paths": self.file_paths}

        try:
            self.status_message.emit("서버 문서 분석 및 캐시 확인 중...")

            # 💡 stream=True로 SSE 스트리밍 청크 수신
            with requests.post(url, json=payload, stream=True, timeout=300) as resp:
                if resp.status_code != 200:
                    self.failed.emit(f"서버 오류 ({resp.status_code}): {resp.text}")
                    return

                for line in resp.iter_lines(decode_unicode=True):
                    if self._is_aborted:
                        break
                    if not line:
                        continue

                    # 1. 완료 상태
                    if line == "COMPLETE":
                        self.progress_changed.emit(100)
                        self.status_message.emit("임베딩 인메모리 적재 완료")
                        self.finished.emit()
                        return

                    # 2. 캐시 즉시 히트
                    elif line == "CACHED":
                        self.progress_changed.emit(100)
                        self.status_message.emit("기존 임베딩 캐시 재사용 (0초 소요)")
                        self.finished.emit()
                        return

                    # 3. 작업 취소 완료
                    elif line == "CANCELLED":
                        self.status_message.emit("임베딩 작업이 중단되었습니다.")
                        self.cancelled.emit()
                        return

                    # 4. 진행률 수치 (0 ~ 100)
                    try:
                        progress = int(line)
                        self.progress_changed.emit(progress)
                        self.status_message.emit(f"문서 임베딩 진행 중... ({progress}%)")
                    except ValueError:
                        pass

        except requests.exceptions.ConnectionError:
            self.failed.emit("Chainlit 서버와 연결할 수 없습니다.")
        except Exception as e:
            self.failed.emit(f"통신 중 예외 발생: {str(e)}")

    def request_cancel(self):
        """서버에 즉시 중단 API 요청 전송"""
        print("[qt프로그램]취소 요청")
        self._is_aborted = True
        try:
            requests.post(f"{SERVER_BASE_URL}/api/rag/embed/cancel", timeout=2.0)
        except Exception as e:
            print(f"[Cancel Error] {e}")