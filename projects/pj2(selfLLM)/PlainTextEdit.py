from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtCore import Qt

class mPlainTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._send_button = None

    def set_send_button(self, button):
        """send_btn을 이 MyPlainTextEdit 인스턴스에 연결합니다."""
        self._send_button = button

    def keyPressEvent(self, event):
        # Enter 키가 눌렸고, Shift 키가 함께 눌리지 않았다면
        if (event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            if self._send_button: # send_button이 설정되어 있다면
                self._send_button.click() # send_button 클릭 시뮬레이션
                self.clear() # 메시지 전송 후 입력 필드 비우기 (선택 사항)
            return # 이벤트 처리 완료
        super().keyPressEvent(event) # 기본 QPlainTextEdit의 keyPressEvent 호출