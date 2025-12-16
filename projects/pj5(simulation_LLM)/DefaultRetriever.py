import os

from PyQt6.QtCore import QObject, pyqtSignal

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader, DirectoryLoader
from langchain_teddynote.document_loaders import HWPLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface.embeddings import HuggingFaceEmbeddings

class DefaultRetriever(QObject):
    finished = pyqtSignal()
    progresses = pyqtSignal(int)
    error = pyqtSignal(str)
    changeUi = pyqtSignal()

    def __init__(self, folder_path, api_key, parent=None):
        super().__init__(parent)

        self.folder_path = folder_path
        self.embedding_model = OpenAIEmbeddings(
            api_key=api_key
        )
        # self.embedding_model = HuggingFaceEmbeddings(
        #     model_name="BAAI/bge-m3",
        #     model_kwargs={'device': 'cuda'},
        #     encode_kwargs={'normalize_embedding': True}
        # )
        # self.embedding_model = OpenAIEmbeddings(
        #     model="Qwen/Qwen3-Embedding-8B",
        #     openai_api_base="http://192.168.0.108:8001/v1",
        #     openai_api_key="em"
        # )
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
        self.vector_db = None

    def get_loader(self, filename):
        loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader,
            'csv': CSVLoader,
            'json': JSONLoader,
            'hwp': HWPLoader
        }

        _, file_extension = os.path.splitext(filename)
        file_extension = file_extension.lstrip('.')

        loader_class = loader_classes.get(file_extension)

        if not loader_class:
            raise ValueError(f"No loader available for file extension '{file_extension}'")
        
        # JSON 파일인 경우 jq_schema 인자를 추가하여 반환
        if file_extension == 'json':
            return loader_class(filename, jq_schema='.', text_content=False)
        else:
            # 그 외의 경우 일반적인 방식으로 로더 반환
            return loader_class(filename)
        
    def run(self):
        try:
            flag = 0    #0:생성, 1:로드
            files = os.listdir(self.folder_path)
            total_files = len(files)
            # save_vector = "./test_faiss_embedding"
            save_vector = "./faiss_default"

            if total_files == 0:
                self.error.emit("선택한 폴더에 파일이 없습니다.")
                self.finished.emit()
                return
            
            progress_step = 100 / total_files

            for i, file_name in enumerate(files):
                file_path = os.path.join(self.folder_path, file_name)
                try:
                    loader = self.get_loader(file_path)
                    chunks = self.text_splitter.split_documents(loader.load())

                    if flag == 0:
                        if self.vector_db:
                            self.vector_db.add_documents(chunks)
                        else:
                            self.vector_db = FAISS.from_documents(chunks, self.embedding_model)
                    
                    curr_progress = (i + 1) * progress_step
                    self.progresses.emit(int(curr_progress))
                    
                except Exception as e:
                    self.error.emit(f"{file_name} 파일 임베딩 중 오류 발생: {e}")

            if flag == 0:
                self.vector_db.save_local(save_vector)
                print("FAISS 벡터스토어 생성 및 저장 완료")
            else:
                self.vector_db = FAISS.load_local(save_vector, self.embedding_model, allow_dangerous_deserialization=True)
                print("FAISS 벡터스토어 로드 완료")

            self.progresses.emit(100)
            self.finished.emit()
            self.changeUi.emit()

        except Exception as e:
            self.error.emit(f"임베딩 작업 중 치명적인 오류 발생: {e}")
            self.finished.emit()

    def copy_retriever(self):
        retriever = self.vector_db.as_retriever(search_kwargs={"k": 2})
        return retriever

    def query(self, question: str) -> str:
        retriever = self.vector_db.as_retriever(search_kwargs={"k": 2})
        query_res = retriever.invoke(question)
        return query_res