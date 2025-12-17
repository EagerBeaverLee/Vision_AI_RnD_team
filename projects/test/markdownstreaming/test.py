import sys
import time
import markdown
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QCoreApplication

class MarkdownStreamWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QWebEngineView Markdown Streaming")
        self.resize(800, 600)

        # 메인 레이아웃 설정
        layout = QVBoxLayout()
        self.view = QWebEngineView()
        self.btn = QPushButton("스트리밍 시작")
        self.btn.clicked.connect(self.start_streaming)
        
        layout.addWidget(self.view)
        layout.addWidget(self.btn)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 1. 초기 HTML 뼈대 및 스타일 설정 (한 번만 호출)
        self.init_web_view()

    def init_web_view(self):
        initial_html = """
        <html>
        <head>
            <style>
                body { 
                    background-color: #1e1e1e; color: #d4d4d4; 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    line-height: 1.6; padding: 20px; 
                }
                table { border-collapse: collapse; width: 100%; margin: 15px 0; background: #252526; }
                th, td { border: 1px solid #444; padding: 10px; text-align: left; }
                th { background-color: #333; color: #b8f7b9; }
                code { background-color: #333; padding: 2px 4px; border-radius: 4px; }
                .cursor { 
                    display: inline-block; width: 8px; height: 18px; 
                    background-color: #b8f7b9; margin-left: 5px; 
                    vertical-align: middle; animation: blink 0.8s infinite; 
                }
                @keyframes blink { 50% { opacity: 0; } }
            </style>
        </head>
        <body>
            <div id="content"></div>
            <script>
                function updateMarkdown(html) {
                    const el = document.getElementById('content');
                    el.innerHTML = html + '<span class="cursor"></span>';
                    window.scrollTo(0, document.body.scrollHeight);
                }
            </script>
        </body>
        </html>
        """
        self.view.setHtml(initial_html)

    def start_streaming(self):
        self.btn.setEnabled(False)
        
        # 가상의 마크다운 응답 (표 포함)
        response = (
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
            "## 분석 결과 보고서\n\n"
            "전투력 변화 이벤트를 분석한 결과입니다.\n\n"
            "| 발생 시간 | 관여 부대 | 이벤트 내용 | 중요도 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 14:20 | 제1강습여단 | 적 경계초소 무력화 | 높음 |\n"
            "| 15:05 | 제3군수지원단 | 보급로 차단 확인 | 중간 |\n"
            "| 16:00 | 항공작전사령부 | 공중 지원 개시 | 매우 높음 |\n\n"
            "위 데이터는 실시간으로 집계된 수치이며, 추가 정보가 들어오는 대로 업데이트 예정입니다."
        )

        full_markdown = ""
        words = response.split(' ')

        for i, word in enumerate(words):
            full_markdown += word + (" " if i < len(words) -1 else "")
            
            # 2. 마크다운 변환
            html_chunk = markdown.markdown(full_markdown, extensions=['tables'])
            
            # 3. JavaScript를 통한 부분 업데이트 (핵심!)
            # 백틱(`)과 역슬래시(\) 이스케이프 처리하여 전송
            safe_html = html_chunk.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
            self.view.page().runJavaScript(f"updateMarkdown(`{safe_html}`)")

            # 시각적 지연 및 이벤트 루프 처리
            time.sleep(0.01)
            QCoreApplication.processEvents()
            
        self.btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MarkdownStreamWindow()
    window.show()
    sys.exit(app.exec())