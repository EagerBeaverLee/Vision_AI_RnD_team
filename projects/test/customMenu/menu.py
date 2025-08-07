import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QMenu, QAction
from PyQt5.QtCore import Qt, QPoint

class TableContextMenu(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QTableWidget Context Menu Example")
        self.setGeometry(100, 100, 600, 400)

        self.tableWidget = QTableWidget(self)
        self.setCentralWidget(self.tableWidget)
        self.tableWidget.setRowCount(5)
        self.tableWidget.setColumnCount(3)
        self.tableWidget.setHorizontalHeaderLabels(["Name", "Age", "City"])
        
        for row in range(5):
            for col in range(3):
                item = QTableWidgetItem(f"Item ({row}, {col})")
                self.tableWidget.setItem(row, col, item)

        self.tableWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tableWidget.customContextMenuRequested.connect(self.on_context_menu)
        self.tableWidget.itemChanged.connect(self.on_item_changed)
        
        # 오른쪽 클릭된 아이템을 저장할 멤버 변수
        self.clicked_item = None

    def on_item_changed(self, item: QTableWidgetItem):
        """
        QTableWidgetItem의 내용이 변경될 때 호출되는 슬롯
        """
        row = item.row()
        col = item.column()
        new_text = item.text()
        
        print(f"항목 내용 변경 감지!")
        print(f"  행: {row}, 열: {col}")
        print(f"  새로운 내용: '{new_text}'")
        
    def on_context_menu(self, point: QPoint):
        # 오른쪽 클릭된 위치의 아이템을 가져와 멤버 변수에 저장
        self.clicked_item = self.tableWidget.itemAt(point)
        
        if self.clicked_item is None:
            return

        menu = QMenu(self)

        action_add = QAction("Add Row", self)
        action_remove = QAction("Remove Row", self)
        
        # --- 핵심 코드 ---
        action_rename = QAction("Rename", self)
        action_rename.triggered.connect(self.rename_item)
        # -----------------
        
        action_add.triggered.connect(self.add_row)
        action_remove.triggered.connect(self.remove_row)
        
        menu.addAction(action_rename)
        menu.addSeparator() # 구분선 추가
        menu.addAction(action_add)
        menu.addAction(action_remove)

        menu.exec_(self.tableWidget.mapToGlobal(point))

    def rename_item(self):
        """
        저장된 아이템의 편집 모드를 시작하는 함수
        """
        if self.clicked_item:
            self.tableWidget.editItem(self.clicked_item)

    def add_row(self):
        print("Add Row clicked")
        row_count = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row_count)
        
    def remove_row(self):
        print("Remove Row clicked")
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TableContextMenu()
    window.show()
    sys.exit(app.exec_())