###############################
### ParentDocumentRetriever ###
###############################
import os, uuid
import threading
from PyQt6.QtCore import pyqtSignal, QObject

# from langchain.retrievers import ParentDocumentRetriever
from langchain_classic.retrievers import ParentDocumentRetriever
from langchain_core.stores import InMemoryStore
# from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader, DirectoryLoader
# from langchain_teddynote.document_loaders import HWPLoader

class ParentRetriverPipeline:
    def __init__(self, folder_path: str, openai_api_key: str,
                parent_chunk_size: int = 3000, child_chunk_size: int = 500):
        
        print(f"parent_chunk_size:{parent_chunk_size}\n")
        print(f"child_chunk_size:{child_chunk_size}\n")
        self.folder_path = folder_path
        #Defining Splitter
        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size = parent_chunk_size)
        self.child_splitter = RecursiveCharacterTextSplitter(chunk_size = child_chunk_size)
        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=openai_api_key, 
            model="text-embedding-3-small"
        )

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
            parent_splitter = self.parent_splitter,
        )

        #supported loaders
        self.loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader,
            'csv': CSVLoader,
            'json': JSONLoader,
            # 'hwp': HWPLoader
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
        # docs = loader.load()
        # self.retriever.add_documents(docs, ids=None)
        # print(f"Ingested chunks created by {loader}")

        docs = loader.load()
    
        parent_docs = self.parent_splitter.split_documents(docs)
        all_child_docs = []
    
        for parent_doc in parent_docs:
            parent_id = f"parent-{uuid.uuid4().hex}"
            parent_doc.metadata["doc_id"] = parent_id
            parent_doc.id = parent_id
    
            # child split
            child_docs = self.child_splitter.split_documents([parent_doc])
            for child_doc in child_docs:
                child_doc.metadata["parent_doc_id"] = parent_id
    
            all_child_docs.extend(child_docs)
    
        # 한 번에 vectorstore에 저장
        self.retriever.vectorstore.add_documents(all_child_docs)
    
        # parent_doc은 docstore에 한 번에 저장
        self.retriever.docstore.mset([(doc.metadata["doc_id"], doc) for doc in parent_docs])


    def run(self, cancel_flag: threading.Event):      # db_reset: bool = True):
        """Load all documents from a folder into the retriever pipeline"""
        try:
            files = []
            input_path = None

            if isinstance(self.folder_path, list):
                if len(self.folder_path) > 0:
                    input_path = self.folder_path[0]
                else:
                    print("빈 리스트가 입력되었습니다.")
                    return

            if os.path.isfile(input_path):
                # 단일 파일인 경우 리스트에 바로 추가
                files.append(input_path)
                
            elif os.path.isdir(input_path):
                # 폴더인 경우 내부의 모든 파일 경로를 리스트에 추가
                for file_name in os.listdir(input_path):
                    file_path = os.path.join(input_path, file_name)
                    # 하위 폴더는 제외하고 '파일'만 담기 위해 조건 추가
                    if os.path.isfile(file_path):
                        files.append(file_path)
            else:
                print(f"유효하지 않은 경로입니다: {input_path}")
                return []

            
            print(f"처리할 파일 목록 (files): {files}")
            total_files = len(files)
            
            if total_files == 0:
                print("[default_retriever]선택한 폴더에 파일이 없습니다.")
                yield "CANCELLED\n"

            progress_step = 100 / total_files
            print(f"게이지 분할 값: {progress_step}")

            for i, filename in enumerate(files):
                if cancel_flag.is_set():
                    print("[ParentChildRetriever Worker Thread] 취소 신호 감지, 동기 루프 탈출")
                    return
                # file_path = os.path.join(self.folder_path, filename)
                try:
                    loader = self.get_loader(filename)
                    print(f"Loader for {filename}: {loader}")
                    self.add_document(loader)

                    curr_progress = (i + 1) * progress_step
                    yield f"{curr_progress}\n"
                except ValueError as e:
                    print(f"오류: {e}")
                    yield "CANCELLED\n"

            yield "COMPLETE\n"
            print("Parent Child 벡터스토어 생성 및 로드 완료")
        except Exception as e:
            print(f"오류: {e}")
            yield "CANCELLED\n"
    
    def format_docs(self, docs):
        """Format retrieved docs into a single string."""
        return "\n\n".join(doc.page_content for doc in docs)
    
    def copy_retriever(self):
        return self.retriever

    def query(self, question: str) -> str:
        retrieved_parent_doc = self.retriever.invoke(question)
        return retrieved_parent_doc
    
    def query_merge(self, question: str) -> str:
        retrieved_parent_doc = self.retriever.invoke(question)
        return self.format_docs(retrieved_parent_doc)

##실행예제
#### ParentDocumentRetriever 사용 예제 ###
# parent_pipeline = ParentRetriverPipeline(openai_api_key=OPENAI_API_KEY)

#더미 문서 제거
# parent_pipeline.remove_dummy_doc()

#폴더 내 문서 로드
# parent_pipeline.load_folder("documents/tactic_north_korea")

# parent_docs = parent_pipeline.retriever.invoke("north korean caste system")
# child_docs = parent_pipeline.child_chunks_collection.similarity_search("north korean caste system")
# print(f"Parent_docs: {parent_docs[1].page_content[:1000]}\n\nChild_docs:{child_docs}")