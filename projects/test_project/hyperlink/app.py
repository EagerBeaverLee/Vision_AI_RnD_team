import sys
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QObject, pyqtSlot

# 1. 자바스크립트에서 호출할 파이썬 객체
class Bridge(QObject):
    @pyqtSlot(str)
    def callFromJs(self, message):
        print(f"파이썬에서 받은 메시지: {message}")
        # 여기서 원하는 로직(파일 열기, DB 조회 등)을 수행하세요.

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)

        # 2. 웹 채널 설정
        self.channel = QWebChannel()
        self.bridge = Bridge()
        self.channel.registerObject("backend", self.bridge)
        self.browser.page().setWebChannel(self.channel)

        # 3. HTML 구성 (Markdown 변환 후의 결과물이라 가정)
        # qwebchannel.js는 Qt에서 제공하는 라이브러리입니다.
        html_content = """
        <html>
        <head>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script>
                new QWebChannel(qt.webChannelTransport, function (channel) {
                    window.backend = channel.objects.backend;
                });

                function linkClicked(word) {
                    backend.callFromJs(word);
                }
            </script>
        </head>
        <body>
            <h1>리포트 결과</h1>
            <p>이것은 분석 리포트입니다. 
               <a href="#" onclick="linkClicked('특정단어')">클릭하면 파이썬 호출</a>
            </p>
        </body>
        </html>
        """
        self.browser.setHtml(html_content)

app = QApplication(sys.argv)
win = MyWindow()
win.show()
sys.exit(app.exec())