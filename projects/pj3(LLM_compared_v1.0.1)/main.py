import sys, os, time
from PyQt5.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QMessageBox, QTextEdit
)
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.uic import loadUi

from mainwindow import Ui_MainWindow

from langchain_openai import OpenAI, ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.connectSignalsSlots()

        self.m_api_key = None
        self.m_temperature = None
        self.m_prompt = None
        self.chat_histroy = ChatMessageHistory() #챗히스토리 관리

    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.load_message)
        self.ui.api_key_txt.editingFinished.connect(self.apply_api_key)
        self.ui.prompt_txt.call_OutFocus.connect(self.apply_prompt)
        self.ui.temp_combo.currentTextChanged.connect(self.apply_temperature)
        
    def load_message(self):
        message = self.ui.input_text.toPlainText()

        if message.strip():
            self.ui.input_text.clear()
            self.default_llm(message)
            self.history_llm(message)

        else:
            QMessageBox.about(
                self,
                "Error",
                "<p>Please enter any message</p>",
            )
    def apply_api_key(self):
        if self.ui.api_key_txt.text().strip():
            self.m_api_key = self.ui.api_key_txt.text().strip()
            QMessageBox.about(self, "입력 완료", "api key 입력이 완료되었습니다")
        else:
            QMessageBox.critical(self, "입력 오류", "api key를 입력해주세요")

    def apply_prompt(self):
        if self.m_prompt == self.ui.prompt_txt.toPlainText().strip():
            return
        elif self.ui.prompt_txt.toPlainText().strip():
            self.m_prompt = self.ui.prompt_txt.toPlainText().strip()
            QMessageBox.about(self, "입력 완료", "prompt 입력이 완료되었습니다")
        else:
            QMessageBox.critical(self, "입력 오류", "prompt를 입력해주세요")
        
    def apply_temperature(self):
        self.m_temperature = self.ui.temp_combo.currentText()
        QMessageBox.about(self, "입력 완료", "temperature 입력이 완료되었습니다")

    def default_llm(self, msg):
        response = None
        chat_model = ChatOpenAI(
            api_key=self.m_api_key,
            temperature=self.m_temperature,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    self.m_prompt
                ),
                ("human", "{input}"),
            ]
        )
        chain = prompt | chat_model

        try:
            response = chain.invoke(
                {"input": msg},
            )
        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")

        if response:
            self.ui.non_history_txt.append(f"Sended Message: {msg}")
            self.ui.non_history_txt.append("")
            words = response.content.split(' ')
            self.ui.non_history_txt.append("Ai Messages: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.non_history_txt.textCursor()
                cursor.movePosition(cursor.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.non_history_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

        self.ui.non_history_txt.append("")

    def history_llm(self, msg):
        response = None
        chat_model = ChatOpenAI(
            api_key=self.m_api_key,
            temperature=self.m_temperature,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    self.m_prompt
                ),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
            ]
        )
        chain = prompt | chat_model

        chain_history = RunnableWithMessageHistory(
            chain,
            lambda session_id: self.chat_histroy,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

        try:
            response = chain_history.invoke(
                {"input": msg},
                {"configurable": {"session_id": "unused"}},
            )
        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")
        
        if response:
            self.ui.history_txt.append(f"Sended Message: {msg}")
            self.ui.history_txt.append("")
            words = response.content.split(' ')
            self.ui.history_txt.append("Ai Messages: ")

            #stream효과
            for i, w in enumerate(words):
                cursor = self.ui.history_txt.textCursor()
                cursor.movePosition(cursor.End)

                # 마지막 단어가 아니면 공백 추가
                if i < len(words) - 1:
                    cursor.insertText(w + " ")
                else:
                    cursor.insertText(w + "\n")
                
                self.ui.history_txt.setTextCursor(cursor)
                
                # 텍스트가 추가될 때마다 UI 업데이트
                QCoreApplication.processEvents()
                
                # 시작적 지연
                time.sleep(0.05)

        self.ui.history_txt.append("")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


