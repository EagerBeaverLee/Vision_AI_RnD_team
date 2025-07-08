import sys
from PyQt5.QtWidgets import QApplication, QDialog, QPushButton, QLabel, QVBoxLayout, QMessageBox

class MyDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("My Dialog")
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.success_label = QLabel("Success!")
        self.success_label.setStyleSheet("color: green; font-size: 24px; font-weight: bold;")
        layout.addWidget(self.success_label)

        self.ok_button = QPushButton("확인")
        self.ok_button.clicked.connect(self.close)
        layout.addWidget(self.ok_button)

        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

class MainWindow(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Main Window")
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.dialog = MyDialog()
        self.layout.addWidget(self.dialog)

        self.show_button = QPushButton("Show Dialog")
        self.layout.addWidget(self.show_button)
        self.show_button.clicked.connect(lambda: self.dialog.exec_())

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
