from qgis_setup import init_qgis_env

init_qgis_env()
from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import pyqtSignal

class MyTextEditor(QTextEdit):
    call_OutFocus = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)

        self.text_change = None
    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.call_OutFocus.emit()
        