import sys, os, time
from PyQt5.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QMessageBox, QTextEdit
)
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.uic import loadUi

from mainwindow import Ui_MainWindow
from setting import Settting_Dialog

from langchain_openai import OpenAI, ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.connectSignalsSlots()

        self.m_api_key = None
        self.m_temperature = None
        self.m_prompt = None

    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.load_message)
        self.ui.setting_btn.clicked.connect(self._open_settings)
        
    def load_message(self):
        message = self.ui.input_text.toPlainText()

        if message.strip():
            self.send_GPT(message)
            self.ui.output_text.append("")
        else:
            QMessageBox.about(
                self,
                "Error",
                "<p>Please enter any message</p>",
            )

    def send_GPT(self, msg):
        QMessageBox.critical(self, "API Key", f"api key value: {self.m_api_key, self.m_temperature, self.m_prompt}")
        response = None
        #chat_model = OpenAI(
        chat_model = ChatOpenAI(
            api_key=self.m_api_key,
            temperature=self.m_temperature,
        )

        messages = [
            SystemMessage(content=f"{self.m_prompt}"),
            HumanMessage(content=f"{msg}")
        ]
        try:
            response = chat_model.invoke(messages)
        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")
        
        if response:
            self.ui.output_text.append(f"Sended Message: {msg}")
            self.ui.output_text.append("")
            words = response.content.split(' ')
            self.ui.input_text.clear()
            self.ui.output_text.append("AI Message: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.output_text.textCursor()
                cursor.movePosition(cursor.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.output_text.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

    def _open_settings(self):
        setting_dialog = Settting_Dialog(self)
        setting_dialog.set_values.connect(self._apply_setting)
        setting_dialog.set_api_key(self.m_api_key)
        setting_dialog.set_api_key(self.m_temperature)
        setting_dialog.set_api_key(self.m_prompt)
        setting_dialog.exec()
           
    def _apply_setting(self, load_api_key, load_temp, load_prompt):
        self.m_api_key = load_api_key
        self.m_temperature = load_temp
        self.m_prompt = load_prompt

    
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


