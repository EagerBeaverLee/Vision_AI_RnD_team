from PyQt5.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

class MyPlainTextEdit(QPlainTextEdit):
    def __init__(self, send_button=None, parent=None):
        super().__init__(parent)
        self._send_button = send_button
        self.setPlaceholderText("메시지를 입력하세요 (Enter로 전송, Shift+Enter로 줄바꿈)")

    def set_send_button(self, button):
        """send_btn을 이 MyPlainTextEdit 인스턴스에 연결합니다."""
        self._send_button = button

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter) and \
           not (event.modifiers() & Qt.ShiftModifier):
            if self._send_button:
                self._send_button.click()
            return
        super().keyPressEvent(event)