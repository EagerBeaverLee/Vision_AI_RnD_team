import asyncio
from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime

from langfuse import get_client
from langfuse.langchain import CallbackHandler

class LLMStreamThread(QThread):
    text_chunk_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str) # 오류 시그널 추가

    def __init__(self, question, llm, chain, trace_id, parent_span_id, parent=None):
        super().__init__(parent)
        self.question = question
        # LangChain 모델 초기화 (API 키는 환경 변수에 설정되어 있어야 합니다)
        self.llm = llm
        # LangChain 체인 설정
        self.chain = chain
        self.experiment_config = {
            "configurable": {"session_id": "experiment"},
            "callbacks": [CallbackHandler()]
        }
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id


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
        langfuse = get_client()
        try:
            with langfuse.start_as_current_observation(
                as_type="span",
                name="vector_stream",
                trace_context={
                    "trace_id": self.trace_id,
                    "parent_span_id": self.parent_span_id,
                },
                input={"question": self.question},
            ) as span:
                buffer = []
                async for chunk in self.chain.astream({"question": self.question}, self.experiment_config,):
                    if chunk:
                        buffer.append(chunk.content)

                    if len(buffer) >= 10:
                        self.text_chunk_received.emit("".join(buffer))
                        buffer.clear()

                if buffer:
                    self.text_chunk_received.emit("".join(buffer))

                self.text_chunk_received.emit("".join("\n\n"))
                span.update(output={"status": "streaming done"})

        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.stream_finished.emit()