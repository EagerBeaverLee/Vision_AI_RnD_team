import sys
import asyncio
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QPushButton, QWidget, QLineEdit
from qasync import QEventLoop, asyncSlot
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

class ChatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt6 + LangChain Streaming")
        self.resize(600, 400)

        # 1. UI 구성
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("질문을 입력하고 엔터를 누르세요...")
        self.send_button = QPushButton("질문하기")

        layout = QVBoxLayout()
        layout.addWidget(self.output_display)
        layout.addWidget(self.input_field)
        layout.addWidget(self.send_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 2. LLM 설정 (streaming=True 필수)
        self.llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=0.1,
        )

        # 이벤트 연결
        self.send_button.clicked.connect(self.handle_query)
        self.input_field.returnPressed.connect(self.handle_query)

    @asyncSlot()
    async def handle_query(self):
        user_text = self.input_field.text().strip()
        if not user_text:
            return

        # UI 초기화 및 비활성화
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        self.output_display.append(f"\n<b>나:</b> {user_text}\n<b>AI:</b> ")
        
        try:
            # 3. LangChain astream 사용
            # astream은 비동기 제너레이터를 반환합니다.
            async for chunk in self.llm.astream([HumanMessage(content=user_text)]):
                # 각 청크의 내용(content)을 UI에 추가
                content = chunk.content
                if content:
                    self.output_display.insertPlainText(content)
                    # 자동 스크롤
                    self.output_display.ensureCursorVisible()
        except Exception as e:
            self.output_display.append(f"\n[오류 발생]: {str(e)}")
        finally:
            self.input_field.setEnabled(True)
            self.send_button.setEnabled(True)
            self.output_display.append("\n")

async def main():
    # 4. qasync 통합 루프 설정
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = ChatApp()
    window.show()

    with loop:
        await loop.run_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
