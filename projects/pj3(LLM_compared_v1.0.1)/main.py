import sys, os, time
from PyQt5.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QMessageBox, QTextEdit, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QDoubleValidator
from PyQt5.uic import loadUi

from mainwindow import Ui_MainWindow

from langchain_openai import OpenAI, ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

class ChatRoom:
    def __init__(self, name = "Unnamed chat"):
        self.name = name
        self.m_api_key = None
        self.m_temperature = "0.00"
        self.m_prompt = ""

        self.default_chat_log = ""
        self.experiment_chat_log = ""
        self.user_in_txt = ""

        self.chat_histroy = ChatMessageHistory() #챗히스토리 관리

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        validator = QDoubleValidator()
        validator.setRange(0.00, 1.00)
        validator.setDecimals(2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.ui.temp_val.setValidator(validator)

        self.m_api_key = None
        self.m_temperature = "0.00"
        self.m_prompt = None
        self.chat_histroy = ChatMessageHistory() #챗히스토리 관리

        self.connectSignalsSlots()

        self.chat_rooms = []    #채팅방 관리
        self.current_chat_room = None
        self.add_new_chat_room(initial=True)

    def slider_temp(self):        
        self.temperature_apply(True)

    def text_temp(self):
        self.temperature_apply(False)

    def temperature_apply(self, flag):
        if flag:
            float_val = self.ui.temp_slider.value() * 0.01
            if float_val == float(self.m_temperature) or str(float_val) == self.ui.temp_val.text().strip():
                return
            self.ui.temp_val.setText(str(float_val))
            QMessageBox.about(self, "입력 완료", "temperature 입력이 완료되었습니다")
        else:
            float_val = float(self.ui.temp_val.text().strip())
            if float_val == self.m_temperature or float_val * 100 == self.ui.temp_slider.value():
                return
            self.ui.temp_slider.setValue(int(float_val * 100))
            QMessageBox.about(self, "입력 완료", "temperature 입력이 완료되었습니다")

    def connectSignalsSlots(self):
        self.ui.send_btn.clicked.connect(self.load_message)
        self.ui.api_key_txt.editingFinished.connect(self.apply_api_key)
        self.ui.prompt_txt.call_OutFocus.connect(self.apply_prompt)

        self.ui.new_chat_btn.clicked.connect(self.add_new_chat_room)
        self.ui.del_chat_btn.clicked.connect(self.delete_selected_chat_room)
        self.ui.chat_room_table.itemSelectionChanged.connect(self.load_selected_chat_room)
        self.ui.temp_slider.sliderReleased.connect(self.slider_temp)

        self.ui.temp_val.editingFinished.connect(self.text_temp)

    def show_status_messages(self, message, is_error=False):
        if is_error:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ffcccc; color: red;}")
        else:
            self.ui.statusbar.setStyleSheet("QStatusBar {background-color: #ccffcc; color: green;}")
        self.ui.statusbar.showMessage(message, 3000) # Show for 3 seconds

    def update_chat_room_list(self):
        self.ui.chat_room_table.setRowCount(len(self.chat_rooms))
        for i, room in enumerate(self.chat_rooms):
            item = QTableWidgetItem(room.name)
            item.setData(Qt.UserRole, room) # Store the ChatRoom object in the item
            self.ui.chat_room_table.setItem(i, 0, item)
        
        # Select the current chat room in the list
        if self.current_chat_room and self.current_chat_room in self.chat_rooms:
            index = self.chat_rooms.index(self.current_chat_room)
            self.ui.chat_room_table.selectRow(index)
        elif self.chat_rooms:
            self.ui.chat_room_table.selectRow(0) # Select first if no current or current deleted

    def add_new_chat_room(self, initial = False):
        if not initial:
            self.stored_ui_information()
        new_room_name = f"Chat {len(self.chat_rooms) + 1}"
        new_room = ChatRoom(name=new_room_name)
        self.chat_rooms.append(new_room)
        self.update_chat_room_list()
        
        if not initial:
            self.current_chat_room = new_room
            self.load_chat_room_data_into_ui(new_room)
            self.show_status_messages(f"New chat room '{new_room_name}' created.")
            self.ui.chat_room_table.selectRow(len(self.chat_rooms) - 1) # Select the newly added row

    def delete_selected_chat_room(self):
        selected_row = self.ui.chat_room_table.selectedIndexes()
        if not selected_row:
            self.show_status_messages("No chat room selected to delete.", is_error=True)
            return
        
        row_to_del = selected_row[0].row()
        room_to_del = self.chat_rooms[row_to_del]

        if len(self.chat_rooms) == 1:
            self.show_status_messages("Cannot delete the last chat room. Create a new one first.", is_error=True)
            return
        
        self.chat_rooms.pop(row_to_del)
        self.show_status_messages(f"Chat room '{room_to_del.name}' deleted.")
        self.update_chat_room_list()

        if room_to_del == self.current_chat_room:
            if self.chat_rooms:
                new_selection_index = min(row_to_del, len(self.chat_rooms) - 1)
                self.ui.chat_room_table.selectRow(new_selection_index)
                self.current_chat_room = self.chat_rooms[new_selection_index]
                self.load_chat_room_data_into_ui(self.current_chat_room)
            else:
                self.current_chat_room = None
                self.clear_chat_ui()

    def stored_ui_information(self):
        if self.current_chat_room:
            self.current_chat_room.m_api_key = self.ui.api_key_txt.text().strip()
            self.current_chat_room.m_prompt = self.ui.prompt_txt.toPlainText().strip()
            self.current_chat_room.m_temperature = self.ui.temp_val.text().strip()
            self.current_chat_room.default_chat_log = self.ui.non_history_txt.toPlainText().strip()
            self.current_chat_room.experiment_chat_log = self.ui.history_txt.toPlainText().strip()
            self.current_chat_room.user_in_txt = self.ui.input_text.toPlainText().strip()


    def load_selected_chat_room(self):
        self.stored_ui_information()
        selected_items = self.ui.chat_room_table.selectedItems()
        if selected_items:
            selected_row = selected_items[0].row()
            room = self.chat_rooms[selected_row]
            if room != self.current_chat_room: # Only update if a different room is selected
                self.current_chat_room = room
                self.load_chat_room_data_into_ui(room)
                self.show_status_messages(f"Switched to chat room: '{room.name}'")
        else:
            # If nothing is selected (e.g., after deletion of last item), clear UI
            self.current_chat_room = None
            self.clear_chat_ui()

    def load_chat_room_data_into_ui(self, room):
        # Disconnect signals temporarily to prevent unwanted triggers
        self.ui.api_key_txt.editingFinished.disconnect(self.apply_api_key)
        self.ui.prompt_txt.call_OutFocus.disconnect(self.apply_prompt)

        self.ui.api_key_txt.setText(room.m_api_key if room.m_api_key else "")
        self.ui.prompt_txt.setText(room.m_prompt if room.m_prompt else "")
        self.ui.temp_val.setText(room.m_temperature)
        self.ui.non_history_txt.setText(room.default_chat_log)
        self.ui.history_txt.setText(room.experiment_chat_log)
        self.ui.input_text.setPlainText(room.user_in_txt)

        # Reconnect signals
        self.ui.api_key_txt.editingFinished.connect(self.apply_api_key)
        self.ui.prompt_txt.call_OutFocus.connect(self.apply_prompt)
    
    def clear_chat_ui(self):
        self.ui.api_key_txt.clear()
        self.ui.prompt_txt.clear()
        self.ui.temp_val.setText("0.00") # Reset to default
        self.ui.non_history_txt.clear()
        self.ui.history_txt.clear()
        self.ui.input_text.clear()
        
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

    def apply_prompt(self):
        if self.m_prompt == self.ui.prompt_txt.toPlainText().strip():
            return
        elif self.ui.prompt_txt.toPlainText().strip():
            self.m_prompt = self.ui.prompt_txt.toPlainText().strip()
            QMessageBox.about(self, "입력 완료", "prompt 입력이 완료되었습니다")
        
    
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
        self.current_chat_room.chat_histroy = self.chat_histroy

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())


