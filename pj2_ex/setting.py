# setting.py (pyuic5로 생성된 파일)
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout, QLabel
from PyQt5.QtCore import pyqtSignal

class Ui_SettingDialog(object):
    def setupUi(self, SettingDialog):
        SettingDialog.setObjectName("SettingDialog")
        SettingDialog.resize(400, 300)

        self.verticalLayout = QtWidgets.QVBoxLayout(SettingDialog)
        self.verticalLayout.setObjectName("verticalLayout")

        self.label = QtWidgets.QLabel(SettingDialog)
        self.label.setText("OpenAI API Key:")
        self.verticalLayout.addWidget(self.label)

        self.text_api = QtWidgets.QTextEdit(SettingDialog)
        self.text_api.setObjectName("text_api")
        self.text_api.setPlaceholderText("API 키를 입력하세요...")
        self.verticalLayout.addWidget(self.text_api)

        self.buttonBox = QtWidgets.QDialogButtonBox(SettingDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(SettingDialog)
        # self.buttonBox.accepted.connect(SettingDialog.accept) # 메인 로직에서 연결하므로 주석 처리
        # self.buttonBox.rejected.connect(SettingDialog.reject) # 메인 로직에서 연결하므로 주석 처리
        QtCore.QMetaObject.connectSlotsByName(SettingDialog)

    def retranslateUi(self, SettingDialog):
        _translate = QtCore.QCoreApplication.translate
        SettingDialog.setWindowTitle(_translate("SettingDialog", "Settings"))


class SettingDialog(QDialog):
    # API 키 값을 문자열로 전달할 시그널
    settings_applied = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_SettingDialog()
        self.ui.setupUi(self)

        # '확인' 버튼 클릭 시 _on_ok_button_clicked 호출
        self.ui.buttonBox.accepted.connect(self._on_ok_button_clicked)
        # '취소' 버튼 클릭 시 기본 reject() 호출
        self.ui.buttonBox.rejected.connect(self.reject)

    def _on_ok_button_clicked(self):
        api_key = self.ui.text_api.toPlainText().strip()
        self.settings_applied.emit(api_key) # 시그널 발생
        self.accept() # 다이얼로그 닫기

    def get_api_key(self):
        return self.ui.text_api.toPlainText()

    def set_api_key(self, key):
        self.ui.text_api.setPlainText(key)