import os 
from dotenv import load_dotenv

# 1. 파일이 로드되는 시점에 .env 환경변수를 자동으로 로딩
load_dotenv()

from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader

project_root = Path(__file__).resolve().parent.parent
default_index_path = str(project_root / "data" / "doctrine_data" /"faiss_index")
default_data_path = str(project_root / "data" / "doctrine_data" /"raw_documents")

class DefaultDocumentRetriever:
    def __init__(self, 
                #  openai_api_key: str = None, 
                 index_path: str = default_index_path, 
                 chunk_size: int = 2000,
                 chunk_overlap: int = 250
                 ):

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API Key가 필요합니다.")

        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=api_key,
            model="text-embedding-3-small"
        )
        self.index_path = index_path

        self.recursive_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", ".", " ", ""],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        self.loader_classes = {'docx': Docx2txtLoader, 'pdf': PyPDFLoader, 'txt': TextLoader}

        if os.path.exists(self.index_path):
            print(f"기존 FAISS DB 로드 중: {self.index_path}")
            self.default_db = FAISS.load_local(
                folder_path=self.index_path, 
                embeddings=self.embedding_model,
                allow_dangerous_deserialization=True
            )
        else:
            print("기존 FAISS DB가 없습니다. 새로 인덱싱해야 합니다")
            self.default_db = None

    def get_loader(self, filename: str):
        _, ext = os.path.splitext(filename)
        loader_class = self.loader_classes.get(ext.lstrip('.').lower())
        if not loader_class:
            raise ValueError(f"지원하지 않는 파일 형식: {ext}")
        return loader_class(filename)

    def load_folder(self, folder_path: str = default_data_path):
        """raw_documents 폴더의 파일들을 읽어 doctrine_data/faiss_index 에 저장"""
        if self.default_db is not None:
            print("FAISS DB가 이미 메모리에 로드되어 있어 생성 과정을 스킵합니다.")
            return

        all_chunks = []
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                try:
                    loader = self.get_loader(file_path)
                    chunks = self.recursive_splitter.split_documents(loader.load())
                    all_chunks.extend(chunks)
                except Exception as e:
                    print(f"파일 로드 실패 ({filename}): {e}")

        if all_chunks:
            self.default_db = FAISS.from_documents(all_chunks, self.embedding_model)
            # doctrine_data/faiss_index에 저장
            self.default_db.save_local(self.index_path)
            print(f" FAISS DB 저장 완료: {self.index_path}")

    def format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def query(self, question: str, k=3):
        if not self.default_db:
            raise ValueError("VectorDB가 로딩되지 않았습니다.")
        return self.default_db.similarity_search(question, k=k)

        
# if __name__ == "__main__":
#     default_retriever_pipeline =  DefaultDocumentRetriever()
#     default_retriever_pipeline.load_folder()

#     retrieved_texts = default_retriever_pipeline.query("저시정 항해시 조치사항")
#     print(default_retriever_pipeline.format_docs(retrieved_texts))