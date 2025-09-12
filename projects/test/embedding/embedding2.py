import os
import sys

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QProgressBar
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader
from langchain_community.vectorstores import FAISS # <--- FAISS 임포트
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

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
            embedding_model = OpenAIEmbeddings(openai_api_key=self.api_key)
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)

            files = os.listdir(self.folder_path)
            total_files = len(files)
            save_vector = "./vectorDB"

            if total_files == 0:
                self.error.emit("선택한 폴더에 파일이 없습니다.")
                self.finished.emit()
                return

            progress_step = 100 / total_files
            
            # FAISS는 from_documents 메소드를 사용합니다.
            # 모든 문서를 처리한 후 한 번에 벡터 데이터베이스를 생성합니다.
            all_chunks = []
            for i, file_name in enumerate(files):
                file_path = os.path.join(self.folder_path, file_name)
                try:
                    loader = self.get_loader(file_path)
                    chunks = text_splitter.split_documents(loader.load())
                    print(i)
                    all_chunks.extend(chunks)
                    
                    current_progress = (i + 1) * progress_step
                    self.progress.emit(int(current_progress))
                except Exception as e:
                    self.error.emit(f"{file_name} 파일 처리 중 오류 발생: {e}")
            
            # 모든 청크를 임베딩하여 FAISS 벡터스토어 생성
            if all_chunks:
                vector_db = FAISS.from_documents(all_chunks, embedding_model)
                print("FAISS 벡터스토어 생성 완료")
                # save_path = os.path.join(self.folder_path, save_vector)
                vector_db.save_local(save_vector)
                print("FAISS 벡터스토어 저장 완료")

            retreiver = vector_db.as_retriever()

            query = "Leaders of IO units consider the following?"
            print(f"질문: {query}에 관한 문서 검색중...")
            # relevant_documents = retreiver.get_relevant_documents(query)
            relevant_documents = retreiver.invoke(query)

            print("--결과--")
            if relevant_documents:
                for i, doc in enumerate(relevant_documents):
                    print(f"[{i+1}] 문서내용: {doc.page_content[:150]}...")
                    if doc.metadata:
                        print(f"출처: {doc.metadata.get('source', '알 수 없음')}")
            else:
                print("관련 문서를 찾을 수 없습니다.")
            
            self.progress.emit(100)
            self.finished.emit()

        except Exception as e:
            self.error.emit(f"임베딩 작업 중 치명적인 오류 발생: {e}")
            self.finished.emit()

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

            self.threading = QThread()
            self.worker = EmbeddingWorker(
                folder_path=path,
                api_key="apikey",
            )
            self.worker.moveToThread(self.threading)

            self.threading.started.connect(self.worker.run)
            self.worker.progress.connect(self.progress_bar.setValue)
            self.worker.finished.connect(self.threading.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.threading.finished.connect(self.threading.deleteLater)

            self.worker.finished.connect(lambda: self.start_button.setEnabled(True))
            self.worker.finished.connect(lambda: QMessageBox.information(self, "완료", "임베딩이 완료되었습니다"))
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "오류", msg))

            self.threading.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = EmbeddingApp()
    ex.show()
    sys.exit(app.exec_())