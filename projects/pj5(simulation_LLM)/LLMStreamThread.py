import asyncio
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class LLMStreamThread(QThread):
    text_chunk_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str) # 오류 시그널 추가

    def __init__(self, prompt_text, parent=None):
        super().__init__(parent)
        self.prompt_text = prompt_text
        self._running = True
        # LangChain 모델 초기화 (API 키는 환경 변수에 설정되어 있어야 합니다)
        # 예: os.environ["OPENAI_API_KEY"] = "YOUR_API_KEY"
        # self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key="apikey 입력") # 원하는 모델로 변경 가능
        self.llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=0.1,
        )

        # LangChain 체인 설정
        self.prompt = ChatPromptTemplate.from_template("{question}")
        self.output_parser = StrOutputParser()
        self.chain = self.prompt | self.llm | self.output_parser


    def run(self):
        """
        비동기 코드를 실행하고 시그널을 통해 UI를 업데이트합니다.
        QThread 내에서 asyncio 이벤트 루프를 실행하기 위해 새로운 루프를 생성합니다.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._stream_text())

    async def _stream_text(self):
        """
        LangChain을 사용하여 LLM 응답을 비동기적으로 스트리밍하고 텍스트 조각을 방출합니다.
        """
        try:
            # LangChain의 astream_events 또는 astream을 사용하여 스트리밍
            # astream_events는 더 상세한 이벤트를 제공하지만, 여기서는 단순 텍스트 스트리밍을 위해 astream 사용
            async for chunk in self.chain.astream({"question": self.prompt_text}):
                if not self._running:
                    break
                # LangChain astream은 일반적으로 문자열 조각을 반환합니다.
                self.text_chunk_received.emit(chunk)
                # 필요에 따라 작은 지연을 추가하여 타이핑 효과를 강조할 수 있습니다.
                await asyncio.sleep(0.01)

        except Exception as e:
            print(f"스트리밍 중 오류 발생: {e}")
            self.stream_error.emit(f"스트리밍 오류: {e}")
        finally:
            self.stream_finished.emit()

    def stop(self):
        """스레드 실행을 중단합니다."""
        self._running = False
        if self.loop.is_running():
            self.loop.stop()
        self.wait()