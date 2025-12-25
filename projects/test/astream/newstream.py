import sys
import json
import asyncio
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

# LangChain 관련 임포트
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. 스트리밍 스레드 (기존 구조 유지)
class LLMStreamThread(QThread):
    chunk_received = pyqtSignal(str) # 한 조각씩 보낼 시그널
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, prompt_text):
        super().__init__()
        self.prompt_text = prompt_text
        self.llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=0.1,
        )
        self.chain = ChatPromptTemplate.from_template("{question}") | self.llm | StrOutputParser()

    def run(self):
        # 스레드 내부 전용 이벤트 루프 생성
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._stream())

    async def _stream(self):
        try:
            async for chunk in self.chain.astream({"question": self.prompt_text}):
                if chunk:
                    self.chunk_received.emit(chunk) # UI 스레드로 텍스트 전달
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

# 2. 메인 UI 클래스
class LLMApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("QThread + WebEngine Streaming")
        self.resize(800, 600)
        layout = QVBoxLayout(self)

        # WebEngineView (JS 스트리밍 출력용)
        self.webEngineView = QWebEngineView()
        self.webEngineView.setHtml(self.get_html_template())
        layout.addWidget(self.webEngineView)

        self.input_field = QLineEdit()
        self.send_button = QPushButton("질문 전송")
        self.send_button.clicked.connect(self.start_llm)

        self.full_text = ""
        
        layout.addWidget(self.input_field)
        layout.addWidget(self.send_button)

    def get_html_template(self):
        return """
        <html>
        <head>
            <meta charset="utf-8">
            <!-- 1. marked 라이브러리 로드 -->
            <script src="cdn.jsdelivr.net"></script>
            <style>
                /* 2. 표(Table) 및 마크다운 스타일 정의 */
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; 
                       padding: 25px; line-height: 1.6; color: #24292e; background-color: #ffffff; }
                
                #content { max-width: 100%; }

                /* 표 스타일 - 이 부분이 없으면 표가 깨져 보입니다 */
                table { border-collapse: collapse; width: 100%; margin-bottom: 16px; margin-top: 10px; }
                table th, table td { padding: 8px 13px; border: 1px solid #dfe2e5; }
                table tr { background-color: #fff; border-top: 1px solid #c6cbd1; }
                table tr:nth-child(2n) { background-color: #f6f8fa; }
                table th { font-weight: 600; background-color: #f6f8fa; }

                /* 인용구 스타일 */
                blockquote { border-left: 0.25em solid #dfe2e5; color: #6a737d; padding: 0 1em; margin: 10px 0; }
                
                /* 코드 블록 */
                pre { background-color: #f6f8fa; border-radius: 6px; padding: 16px; overflow: auto; border: 1px solid #ddd; }
                code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; 
                       background-color: rgba(27,31,35,0.05); padding: 0.2em 0.4em; border-radius: 3px; font-size: 85%; }

                .cursor { display: inline-block; width: 8px; height: 16px; background: #007bff; margin-left: 4px; vertical-align: middle; animation: blink 1s infinite; }
                @keyframes blink { 50% { opacity: 0; } }
                hr { height: 0.25em; padding: 0; margin: 24px 0; background-color: #e1e4e8; border: 0; }
            </style>
        </head>
        <body>
            <div id="content"></div>
            <script>
                let fullMarkdown = "";

                // marked 설정 최적화
                function getRenderer() {
                    if (typeof marked !== 'undefined') {
                        // v4.0 이상 대응 설정
                        marked.setOptions({
                            gfm: true,        // GitHub Flavored Markdown (표 지원)
                            breaks: true,     // 일반 엔터를 <br>로 변환
                            mangle: false,
                            headerIds: false
                        });
                        return true;
                    }
                    return false;
                }

                function appendText(chunk) {
                    fullMarkdown += chunk;
                    const contentDiv = document.getElementById('content');
                    
                    if (typeof marked !== 'undefined') {
                        try {
                            // marked.parse() 호출 시 표 서식이 포함된 마크다운 처리
                            contentDiv.innerHTML = marked.parse(fullMarkdown) + '<span class="cursor"></span>';
                        } catch (e) {
                            console.error("Parsing Error:", e);
                            contentDiv.innerHTML = "<pre>" + fullMarkdown + "</pre>";
                        }
                    } else {
                        // 라이브러리 로드 실패 시
                        contentDiv.innerText = fullMarkdown;
                    }
                    
                    window.scrollTo(0, document.body.scrollHeight);
                }

                function removeCursor() {
                    const c = document.querySelector('.cursor');
                    if(c) c.remove();
                }

                // 라이브러리 로드 대기 및 설정
                const checkMarked = setInterval(() => {
                    if (getRenderer()) {
                        console.log("Marked library ready.");
                        clearInterval(checkMarked);
                    }
                }, 100);
            </script>
        </body>
        </html>
        """



    def start_llm(self):
        text = self.input_field.text().strip()
        if not text: return

        self.send_button.setEnabled(False)
        self.input_field.clear()

        # 스레드 생성 및 시그널 연결
        self.thread = LLMStreamThread(text)
        self.thread.chunk_received.connect(self.update_web_view)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    @pyqtSlot(str)
    def update_web_view(self, chunk):
        # 🌟 핵심: 시그널로 받은 텍스트를 JS 인자로 안전하게 변환하여 실행
        safe_chunk = json.dumps(chunk)
        self.webEngineView.page().runJavaScript(f"appendText({safe_chunk})")

    def on_finished(self):
        self.webEngineView.page().runJavaScript("removeCursor()")
        self.send_button.setEnabled(True)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = LLMApp()
    ex.show()
    sys.exit(app.exec())
