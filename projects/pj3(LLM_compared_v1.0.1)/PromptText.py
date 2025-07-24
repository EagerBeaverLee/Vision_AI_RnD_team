from PyQt5.QtWidgets import QTextEdit, QMessageBox
from PyQt5.QtCore import pyqtSignal

class MyTextEditor(QTextEdit):
    call_OutFocus = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)

        self.text_change = None
    def focusOutEvent(self, e):
        self.call_OutFocus.emit()
        super().focusOutEvent(e)