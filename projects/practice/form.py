import sys
from PyQt5.QtWidgets import *
from PyQt5 import uic

#form_class = uic.loadUiType("untitled.ui")[0]

class MyWindow(QWidget):
    def __init__(self):
        super().__init__()
        #self.setupUi(self)
        layout = QHBoxLayout()
        layout.addWidget(QPushButton('left-most'))
        layout.addWidget(QPushButton('Center'))
        layout.addWidget(QPushButton('right-most'))
        self.setLayout(layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    myWindow = MyWindow()
    myWindow.show()
    app.exec_()