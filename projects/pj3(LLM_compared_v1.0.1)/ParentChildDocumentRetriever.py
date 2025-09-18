###############################
### ParentDocumentRetriever ###
###############################
import os
from PyQt5.QtCore import pyqtSignal

from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader

class ParentRetriverPipeline:
    done = pyqtSignal()
    
    def __init__(self, openai_api_key: str,
                parent_chunk_size: int = 3000, child_chunk_size: int = 500):

        #Defining Splitter
        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size = parent_chunk_size)
        self.child_splitter = RecursiveCharacterTextSplitter(chunk_size = child_chunk_size)
        self.embedding_model = OpenAIEmbeddings(openai_api_key=openai_api_key)

        self.dummy_doc = Document(page_content="dummy")
        self.dummy_doc_id = "DUMMY_DOC"  # 임의의 doc_id 지정
        self.dummy_doc.metadata = {"id": self.dummy_doc_id}
        #When using FAISE DB
        self.child_chunks_collection = FAISS.from_documents([self.dummy_doc], self.embedding_model)
        
        #Parent docstore
        self.doc_store = InMemoryStore()

        #retriever linking parent andchild
        self.retriever = ParentDocumentRetriever(
            vectorstore = self.child_chunks_collection,
            docstore = self.doc_store,
            child_splitter = self.child_splitter, 
            parent_splitter = self.parent_splitter
        )

        #supported loaders
        self.loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader
        }
     
    def remove_dummy_doc(self):
        # docstore 내부 dict에서 doc_id 확인
        doc_ids = [doc_id for doc_id in self.child_chunks_collection.docstore._dict
                   if self.child_chunks_collection.docstore._dict[doc_id].metadata.get("id") == self.dummy_doc_id]
        if doc_ids:
            self.child_chunks_collection.delete(doc_ids)
            print(f"Removed dummy doc with id {self.dummy_doc_id}")
        else:
            print("No dummy doc found")
            
    # def reset(self):
    #     """reset collections and document store"""
    #     self.child_chunks_collection.reset_collection()
    #     self.doc_store = InMemoryStore()

    def get_loader(self, filename: str):
        _, file_extension = os.path.splitext(filename)
        file_extension = file_extension.lstrip('.').lower()
        loader_class = self.loader_classes.get(file_extension)
        if not loader_class:
            raise ValueError(f"No loader available for file extension '{file_extension}'")
        return loader_class(filename)

    def add_document(self, loader):
        docs = loader.load()
        self.retriever.add_documents(docs, ids=None)
        print(f"Ingested chunks created by {loader}")

    def load_folder(self, folder_path: str):      # db_reset: bool = True):
        """Load all documents from a folder into the retriever pipeline"""
        # if db_reset:
        #     self.reset()

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                try:
                    loader = self.get_loader(file_path)
                    print(f"Loader for {filename}: {loader}")
                    self.add_document(loader)
                    self.done.emit()
                except ValueError as e:
                    print(e)
    
    def format_docs(self, docs):
        """Format retrieved docs into a single string."""
        return "\n\n".join(doc.page_content for doc in docs)

    def query(self, question: str) -> str:
        retrieved_parent_doc = self.retriever.invoke(question)
        return self.format_docs(retrieved_parent_doc)

##실행예제
#### ParentDocumentRetriever 사용 예제 ###
#parent_pipeline = ParentRetriverPipeline(openai_api_key=OPENAI_API_KEY)

#더미 문서 제거
#parent_pipeline.remove_dummy_doc()

#폴더 내 문서 로드
#parent_pipeline.load_folder("documents/tactic_north_korea")

#parent_docs = parent_pipeline.retriever.invoke("north korean caste system")
#child_docs = parent_pipeline.child_chunks_collection.similarity_search("north korean caste system")
#print(f"Parent_docs: {parent_docs[1].page_content[:1000]}\n\nChild_docs:{child_docs}")