# mainwindow.py (pyuic5로 생성된 파일)
from PyQt5 import QtCore, QtGui, QtWidgets

# custom_widgets에서 MyPlainTextEdit 임포트
from custom_widgets import MyPlainTextEdit

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(489, 450)

        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")

        # API 키 표시용 QTextEdit
        self.display_api_key_text = QtWidgets.QTextEdit(self.centralwidget)
        self.display_api_key_text.setGeometry(QtCore.QRect(10, 10, 461, 60))
        self.display_api_key_text.setReadOnly(True)
        self.display_api_key_text.setPlaceholderText("여기에 API 키가 표시됩니다.")
        self.display_api_key_text.setObjectName("display_api_key_text")

        # 설정 다이얼로그를 여는 버튼
        self.open_settings_btn = QtWidgets.QPushButton(self.centralwidget)
        self.open_settings_btn.setGeometry(QtCore.QRect(10, 80, 100, 30))
        self.open_settings_btn.setObjectName("open_settings_btn")

        self.output_text = QtWidgets.QTextEdit(self.centralwidget)
        self.output_text.setGeometry(QtCore.QRect(10, 120, 461, 180))
        self.output_text.setObjectName("output_text")
        self.output_text.setReadOnly(True)

        # QPlainTextEdit 대신 MyPlainTextEdit 사용
        self.input_text = MyPlainTextEdit(self.centralwidget)
        self.input_text.setGeometry(QtCore.QRect(10, 310, 391, 31))
        self.input_text.setObjectName("input_text")

        self.send_btn = QtWidgets.QPushButton(self.centralwidget)
        self.send_btn.setGeometry(QtCore.QRect(410, 310, 61, 31))
        self.send_btn.setObjectName("send_btn")

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 489, 21))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        # QtCore.QMetaObject.connectSlotsByName(MainWindow) # 메인 로직에서 연결하므로 주석 처리

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "LangChain Chat App"))
        self.open_settings_btn.setText(_translate("MainWindow", "Settings"))
        self.send_btn.setText(_translate("MainWindow", "send"))