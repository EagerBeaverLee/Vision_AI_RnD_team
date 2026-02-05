import asyncio
from qgis_setup import init_qgis_env

init_qgis_env()
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from datetime import datetime

class LLMStreamThread(QThread):
    text_chunk_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str) # 오류 시그널 추가

    def __init__(self, question, llm, chain, parent=None):
        super().__init__(parent)
        self.question = question
        # LangChain 모델 초기화 (API 키는 환경 변수에 설정되어 있어야 합니다)
        self.llm = llm
        # LangChain 체인 설정
        self.chain = chain
        self.experiment_config = {"configurable": {"session_id": "experiment"}}


    def run(self):
        print(f"[{QThread.currentThreadId()}] LLM작업 시작 {datetime.now()}")
        """
        비동기 코드를 실행하고 시그널을 통해 UI를 업데이트합니다.
        QThread 내에서 asyncio 이벤트 루프를 실행하기 위해 새로운 루프를 생성합니다.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._stream())

    async def _stream(self):
        try:
            buffer = []
            async for chunk in self.chain.astream({"question": self.question}, self.experiment_config,):
                if chunk:
                    buffer.append(chunk.content)

                if len(buffer) >= 10:
                    self.text_chunk_received.emit("".join(buffer))
                    buffer.clear()

            if buffer:
                self.text_chunk_received.emit("".join(buffer))

        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.stream_finished.emit()