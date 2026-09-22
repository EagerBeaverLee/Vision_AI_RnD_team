#-------------------------------
# 순수 Parent Child Retriever ##
#------------------------------

import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

# 1. 파일이 로드되는 시점에 .env 환경변수를 자동으로 로딩
load_dotenv()

from langchain_classic.retrievers import ParentDocumentRetriever
from langchain_classic.storage import InMemoryStore, LocalFileStore, create_kv_docstore
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

# 경로 설정 (DefaultDocumentRetriever와 동일한 구조)
project_root = Path(__file__).resolve().parent.parent
default_index_path = str(project_root / "data" / "doctrine_data" / "parent_faiss_index")
default_docstore_path = str(project_root / "data" / "doctrine_data" / "parent_docstore")
default_data_path = str(project_root / "data" / "doctrine_data" / "raw_documents")


class ParentRetrieverPipeline:
    def __init__(
        self,
        index_path: str = default_index_path,
        docstore_path: str = default_docstore_path,
        parent_chunk_size: int = 3000,
        child_chunk_size: int = 500,
    ):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API Key가 필요합니다.")

        self.index_path = index_path
        self.docstore_path = docstore_path

        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=api_key, 
            model="text-embedding-3-small"
        )

        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size=parent_chunk_size)
        self.child_splitter = RecursiveCharacterTextSplitter(chunk_size=child_chunk_size)

        self.loader_classes = {
            'docx': Docx2txtLoader, 
            'pdf': PyPDFLoader, 
            'txt': TextLoader
        }

        # Parent Document 저장용 디스크 기반 LocalFileStore 설정 (메모리 유실 방지)
        fs = LocalFileStore(self.docstore_path)
        self.doc_store = create_kv_docstore(fs)

        # FAISS DB 로드 또는 초기화
        if os.path.exists(self.index_path):
            print(f"기존 Parent-Child FAISS DB 로드 중: {self.index_path}")
            self.vectorstore = FAISS.load_local(
                folder_path=self.index_path,
                embeddings=self.embedding_model,
                allow_dangerous_deserialization=True
            )
        else:
            print("기존 FAISS DB가 없습니다. 새로 인덱싱해야 합니다.")
            # 초기 인덱스 생성을 위한 더미 생성 후 즉시 인덱스 초기화
            dummy_doc = Document(page_content="init", metadata={"id": "init"})
            self.vectorstore = FAISS.from_documents([dummy_doc], self.embedding_model)

        # ParentDocumentRetriever 연결
        self.retriever = ParentDocumentRetriever(
            vectorstore=self.vectorstore,
            docstore=self.doc_store,
            child_splitter=self.child_splitter,
            parent_splitter=self.parent_splitter
        )

    def get_loader(self, filename: str):
        _, ext = os.path.splitext(filename)
        loader_class = self.loader_classes.get(ext.lstrip('.').lower())
        if not loader_class:
            raise ValueError(f"지원하지 않는 파일 형식: {ext}")
        return loader_class(filename)

    def add_document(self, loader):
        docs = loader.load()
        
        parent_docs = self.parent_splitter.split_documents(docs)
        all_child_docs = []

        for parent_doc in parent_docs:
            parent_id = f"parent-{uuid.uuid4().hex}"
            parent_doc.metadata["doc_id"] = parent_id
            parent_doc.id = parent_id

            child_docs = self.child_splitter.split_documents([parent_doc])
            for child_doc in child_docs:
                child_doc.metadata["parent_doc_id"] = parent_id

            all_child_docs.extend(child_docs)

        self.retriever.vectorstore.add_documents(all_child_docs)
        self.retriever.docstore.mset([(doc.metadata["doc_id"], doc) for doc in parent_docs])

    def load_folder(self, folder_path: str = default_data_path):
        """raw_documents 폴더의 파일들을 읽어 저장 및 DB 인덱싱"""
        if os.path.exists(os.path.join(self.index_path, "index.faiss")):
            print("Parent FAISS DB가 이미 존재하여 생성 과정을 스킵합니다.")
            return

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                try:
                    loader = self.get_loader(file_path)
                    print(f"로딩 중: {filename}")
                    self.add_document(loader)
                except Exception as e:
                    print(f"파일 로드 실패 ({filename}): {e}")

        # 로컬 디스크에 VectorDB 저장
        self.retriever.vectorstore.save_local(self.index_path)
        print(f"Parent FAISS DB 저장 완료: {self.index_path}")

    def format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def query(self, question: str, k: int = 3):
        if not self.retriever:
            raise ValueError("VectorDB가 로딩되지 않았습니다.")
        # k개 search 지원
        self.retriever.search_kwargs = {"k": k}
        return self.retriever.invoke(question)



# if __name__ == "__main__":
#     parent_retriever_pipeline = ParentRetrieverPipeline()
#     parent_retriever_pipeline.load_folder()

#     retrieved_texts = parent_retriever_pipeline.query("저시정 항해시 조치사항", k=3)
#     print(parent_retriever_pipeline.format_docs(retrieved_texts))