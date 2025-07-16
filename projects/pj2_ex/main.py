import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt5.QtCore import QTimer, pyqtSlot, QCoreApplication # pyqtSlot 임포트

# UI 정의 파일 임포트
from mainwindow import Ui_MainWindow
from setting import SettingDialog

# LangChain 및 OpenAI 관련 임포트
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow() # mainwindow.py의 Ui_MainWindow 사용
        self.ui.setupUi(self)

        # OpenAI API 키 설정 및 표시 초기화
        # 환경 변수에서 API 키를 가져오거나, 없다면 빈 문자열로 초기화
        self.current_api_key = os.environ.get("OPENAI_API_KEY", "")
        self._update_api_key_display()

        self.chat_model = None # ChatOpenAI 모델은 API 키가 유효할 때 초기화

        # custom_widgets.MyPlainTextEdit에 send_btn 연결
        self.ui.input_text.set_send_button(self.ui.send_btn)

        # UI 요소와 슬롯 연결
        self.ui.open_settings_btn.clicked.connect(self._open_settings_dialog)
        self.ui.send_btn.clicked.connect(self.send_message_and_display)
        
        # input_text에서 Enter 키 누를 때 send_btn 누르고 포커스 유지
        self.ui.input_text.setFocus() # 시작 시 input_text에 포커스

        # 단어별 표시를 위한 변수 초기화 (timer 사용)
        self.word_index = 0
        self.display_words = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._display_next_word)

        # 초기 ChatOpenAI 모델 로드 (앱 시작 시 API 키가 이미 환경 변수에 있다면)
        if self.current_api_key:
            try:
                self.chat_model = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)
            except Exception as e:
                QMessageBox.critical(self, "초기 모델 로드 실패", f"앱 시작 시 모델 로드 실패: {e}\n"
                                                                  "API 키를 확인하거나 설정해주세요.")

    def _update_api_key_display(self):
        """현재 API 키 상태를 UI에 표시합니다."""
        if self.current_api_key:
            display_key = f"{self.current_api_key[:5]}...{self.current_api_key[-5:]}" if len(self.current_api_key) > 10 else self.current_api_key
            self.ui.display_api_key_text.setText(f"현재 API 키: {display_key}\n(클릭하여 설정)")
        else:
            self.ui.display_api_key_text.setText("API 키가 설정되지 않았습니다.\n(설정 버튼을 클릭해주세요.)")

    def _open_settings_dialog(self):
        """설정 다이얼로그를 열고 API 키를 전달/수신합니다."""
        settings_dialog = SettingDialog(self) # setting.py의 SettingDialog 사용
        settings_dialog.set_api_key(self.current_api_key) # 현재 API 키를 다이얼로그에 미리 설정
        
        # SettingDialog에서 settings_applied 시그널이 발생하면 _apply_new_api_key 슬롯 호출
        settings_dialog.settings_applied.connect(self._apply_new_api_key)
        
        settings_dialog.exec_() # 다이얼로그를 모달로 실행

    @pyqtSlot(str) # 이 메서드가 문자열 인자를 받는 슬롯임을 명시 (선택 사항)
    def _apply_new_api_key(self, new_api_key):
        """SettingDialog에서 전달받은 새로운 API 키를 적용합니다."""
        self.current_api_key = new_api_key
        os.environ["OPENAI_API_KEY"] = new_api_key # 환경 변수 업데이트

        self._update_api_key_display() # UI의 API 키 디스플레이 업데이트

        # 새로운 API 키로 ChatOpenAI 모델 다시 초기화 시도
        try:
            self.chat_model = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)
            QMessageBox.information(self, "설정 적용", "새로운 API 키가 적용되었고, 모델이 초기화되었습니다.")
        except Exception as e:
            self.chat_model = None # 초기화 실패 시 모델을 None으로 설정
            QMessageBox.critical(self, "모델 초기화 실패", f"API 키 적용 후 모델 초기화에 실패했습니다: {e}\n"
                                                           "API 키를 다시 확인해주세요. 인터넷 연결도 확인해주세요.")


    def send_message_and_display(self):
        """사용자 메시지를 보내고, 응답을 단어별로 화면에 표시합니다."""
        # 이전 타이머가 실행 중이면 중지하고 초기화
        if self.timer.isActive():
            self.timer.stop()
        self.ui.output_text.clear()
        self.word_index = 0
        self.display_words = []

        if not self.chat_model:
            QMessageBox.warning(self, "모델 없음", "OpenAI 모델이 초기화되지 않았습니다. 설정에서 API 키를 입력해주세요.")
            return

        user_message_text = self.ui.input_text.toPlainText().strip()
        if not user_message_text:
            QMessageBox.warning(self, "입력 오류", "메시지를 입력해주세요.")
            return

        # 사용자 메시지 출력 및 입력 필드 비우기
        self.ui.output_text.append(f"You: {user_message_text}\n")
        self.ui.input_text.clear()
        self.ui.output_text.append("Assistant: ") # 어시스턴트 응답 시작 표시

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content=user_message_text),
        ]

        try:
            # 1. OpenAI 모델로부터 전체 응답 텍스트를 한 번에 받아옴
            full_response = self.chat_model.invoke(messages).content
            # 2. 공백을 기준으로 단어 리스트 생성
            self.display_words = full_response.split(' ')
            
            # 3. QTimer를 시작하여 단어별로 순차적으로 표시
            self.timer.start(50) # 50ms 간격으로 단어 표시

        except Exception as e:
            QMessageBox.critical(self, "API 오류", f"메시지 전송 중 오류 발생: {e}")
            self.ui.output_text.append("\n[오류가 발생했습니다. 다시 시도해주세요.]")

    def _display_next_word(self):
        """QTimer에 의해 호출되어 다음 단어를 QTextEdit에 추가합니다."""
        if self.word_index < len(self.display_words):
            word = self.display_words[self.word_index]
            cursor = self.ui.output_text.textCursor()
            cursor.movePosition(cursor.End) # 커서를 문서의 끝으로 이동
            
            # 마지막 단어가 아니면 공백 추가, 마지막 단어면 줄바꿈
            if self.word_index < len(self.display_words) - 1:
                cursor.insertText(word + " ")
            else:
                cursor.insertText(word + "\n")
            
            self.ui.output_text.setTextCursor(cursor) # 변경된 커서 적용
            # 스크롤을 자동으로 가장 아래로 내리기
            self.ui.output_text.verticalScrollBar().setValue(self.ui.output_text.verticalScrollBar().maximum())
            self.word_index += 1
        else:
            # 모든 단어를 다 표시했으면 타이머 중지
            self.timer.stop()
            self.ui.output_text.append("\n[답변 완료]")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())