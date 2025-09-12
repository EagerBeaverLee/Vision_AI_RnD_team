import os
import sys

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QProgressBar
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal

# Import the necessary LangChain and ChromaDB components
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

# 1. EmbeddingWorker 클래스: 백그라운드에서 임베딩 작업을 수행합니다.
class EmbeddingWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, folder_path, api_key, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.api_key = api_key

    def get_loader(self, filename):
        loader_classes = {
            'docx': Docx2txtLoader, 'pdf': PyPDFLoader, 'txt': TextLoader,
            'csv': CSVLoader, 'json': JSONLoader
        }
        _, file_extension = os.path.splitext(filename)
        file_extension = file_extension.lstrip('.')
        loader_class = loader_classes.get(file_extension)
        if not loader_class:
            raise ValueError(f"No loader available for file extension '{file_extension}'")
        if file_extension == 'json':
            return loader_class(filename, jq_schema='.', text_content=False)
        else:
            return loader_class(filename)

    def run(self):
        try:
            # 워커 스레드 내에서 모델과 DB 객체를 생성합니다.
            embedding_model = OpenAIEmbeddings(openai_api_key=self.api_key)
            vector_db = Chroma("tourist_info", embedding_model, persist_directory="./chroma_db")
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)

            files = os.listdir(self.folder_path)
            total_files = len(files)

            if total_files == 0:
                self.error.emit("선택한 폴더에 파일이 없습니다.")
                self.finished.emit()
                return

            progress_step = 100 / total_files
            
            for i, file_name in enumerate(files):
                file_path = os.path.join(self.folder_path, file_name)
                try:
                    loader = self.get_loader(file_path)
                    chunks = text_splitter.split_documents(loader.load())
                    vector_db.add_documents(chunks)
                    
                    current_progress = (i + 1) * progress_step
                    self.progress.emit(int(current_progress))
                except Exception as e:
                    self.error.emit(f"{file_name} 파일 처리 중 오류 발생: {e}")
            
            self.progress.emit(100)
            self.finished.emit()

        except Exception as e:
            self.error.emit(f"임베딩 작업 중 치명적인 오류 발생: {e}")
            self.finished.emit()

# 2. 메인 위젯 클래스: UI를 구성하고 스레드를 관리합니다.
class EmbeddingApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("임베딩 테스트")
        layout = QVBoxLayout()
        
        self.start_button = QPushButton("폴더 선택 및 임베딩 시작")
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        
        layout.addWidget(self.start_button)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)
        
        self.start_button.clicked.connect(self.start_embedding)

    def start_embedding(self):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if path:
            self.start_button.setEnabled(False)
            self.progress_bar.setValue(0)

            # QThread 인스턴스 생성
            self.threading = QThread()
            # Worker 객체 인스턴스 생성
            self.worker = EmbeddingWorker(
                folder_path=path,
                api_key="api_key" # 보안을 위해 실제 API 키를 여기에 직접 입력하세요.
            )
            # Worker를 스레드로 이동
            self.worker.moveToThread(self.threading)

            # 시그널과 슬롯 연결
            self.threading.started.connect(self.worker.run)
            self.worker.progress.connect(self.progress_bar.setValue)
            self.worker.finished.connect(self.threading.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.threading.finished.connect(self.threading.deleteLater)

            self.worker.finished.connect(lambda: self.start_button.setEnabled(True))
            self.worker.finished.connect(lambda: QMessageBox.information(self, "완료", "임베딩이 완료되었습니다"))
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "오류", msg))

            # 스레드 시작
            self.threading.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = EmbeddingApp()
    ex.show()
    sys.exit(app.exec_())