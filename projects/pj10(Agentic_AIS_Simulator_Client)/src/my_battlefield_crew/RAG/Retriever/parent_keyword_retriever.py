#------------------------------------
# Parent Child  + TF-IDF Retriever 
#-----------------------------------
import os
import uuid
import threading
from pathlib import Path
from dotenv import load_dotenv

from kiwipiepy import Kiwi

load_dotenv()
from langchain_core.stores import InMemoryStore
from langchain_classic.retrievers import ParentDocumentRetriever, EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_classic.storage import LocalFileStore, create_kv_docstore
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document


def kiwi_tokenize(text: str) -> list[str]:
    kiwi = Kiwi()
    """한국어 문장에서 의미 있는 명사/동사/형용사 단어만 추출하는 토크나이저"""
    tokens = kiwi.tokenize(text)
    # N(명사), V(용언: 동사/형용사), SL(외래어) 계열의 단어만 키워드로 추출
    return [
        token.form for token in tokens 
        if token.tag.startswith(('N', 'V', 'SL'))
    ]

class ParentKeywordRetrieverPipeline:
    def __init__(
        self,
        folder_path: str,
        openai_api_key: str,
        k: int = 4,
        weight: int = 30,
        parent_chunk_size: int = 3000,
        child_chunk_size: int = 500,
    ):
        self.folder_path = folder_path
        self.k = k
        self.weight = weight / 100

        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=openai_api_key, 
            model="text-embedding-3-small"
        )

        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size=parent_chunk_size)
        self.child_splitter = RecursiveCharacterTextSplitter(chunk_size=child_chunk_size)

        self.loader_classes = {
            'docx': Docx2txtLoader, 
            'pdf': PyPDFLoader, 
            'txt': TextLoader
        }

        # Parent Document 저장소
        # fs = LocalFileStore(self.docstore_path)
        # self.doc_store = create_kv_docstore(fs)
        self.doc_store = InMemoryStore()

        dummy_doc = Document(page_content="init", metadata={"id": "init"})
        self.vectorstore = FAISS.from_documents([dummy_doc], self.embedding_model)

        # 1. Base Dense Retriever (ParentDocumentRetriever)
        self.parent_retriever = ParentDocumentRetriever(
            vectorstore=self.vectorstore,
            docstore=self.doc_store,
            child_splitter=self.child_splitter,
            parent_splitter=self.parent_splitter
        )

        # 2. BM25 키워드 리트리버 초기화 변수
        self.bm25_retriever = None
        self.ensemble_retriever = None

        self.retriever = None

    def check_file(self):
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
            return
        
        return files, input_path

    def run(self, cancel_flag: threading.Event):
        files, input_path = self.check_file()

        if not files or not input_path:
            print("문서 로드에 실패했습니다")
            return

        # 확인용 출력 (["파일1", "파일2", ...] 형태로 출력됨)
        print(f"처리할 파일 목록 (files): {files}")
        total_files = len(files)

        if total_files == 0:
            print("[parent_keyword_retriever]선택한 폴더에 파일이 없습니다.")
            yield "CANCELLED\n"

        progress_step = 100 / total_files
        print(f"게이지 분할 값: {progress_step}")

        for i, filename in enumerate(files):
            if cancel_flag.is_set():
                print("[ParentKeywordRetriever Worker Thread] 취소 신호 감지, 동기 루프 탈출")
                return
            try:
                loader = self.get_loader(filename)
                print(f"Loader for {filename}: {loader}")
                self.add_document(loader)

                curr_progress = (i + 1) * progress_step
                yield f"{curr_progress}\n"
            except ValueError as e:
                print(f"오류: {e}")
                yield "CANCELLED\n"

        self._init_bm25_from_docstore(self.k, self.weight)
        
        yield "COMPLETE\n"
        print("Parent keyword 벡터스토어 생성 및 로드 완료")

    def _init_bm25_from_docstore(self, k, weight):
            """저장소에 보관된 Parent 문서들을 불러와 BM25 키워드 인덱스 구축"""
            all_parent_docs = []
            try:
                for key in self.doc_store.yield_keys():
                    doc = self.doc_store.mget([key])[0]
                    if doc:
                        all_parent_docs.append(doc)
            except Exception as e:
                print(f"BM25 로딩 중 예외 발생: {e}")
    
            if all_parent_docs:
                # ★ 핵심 수정 부분: preprocess_func에 kiwi_tokenize 전달
                self.bm25_retriever = BM25Retriever.from_documents(
                    all_parent_docs,
                    preprocess_func=kiwi_tokenize
                )
                self._update_ensemble_retriever(k, weight)
    
    def _update_ensemble_retriever(self, k, weight):
        """Vector Retriever와 BM25 Retriever를 결합한 Ensemble Retriever 구축"""
        if self.bm25_retriever:
            self.parent_retriever.search_kwargs = {"k": k}
            self.bm25_retriever.k = k

            # weights=[0.5, 0.5]: 벡터 검색 50% + 키워드 검색 50% 반영
            self.ensemble_retriever = EnsembleRetriever(
                retrievers=[self.parent_retriever, self.bm25_retriever],
                weights=[weight, 1 - weight]
            )

            self.retriever = self.ensemble_retriever
            print("Vector Retriever와 BM25 Retriever를 결합한 Ensemble Retriever 구축 성공!!")

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

        self.parent_retriever.vectorstore.add_documents(all_child_docs)
        self.parent_retriever.docstore.mset([(doc.metadata["doc_id"], doc) for doc in parent_docs])

    
    def format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def copy_retriever(self):
        return self.retriever

    def query(self, question: str, k: int = 3):
        # BM25가 준비되어 있다면 하이브리드 검색, 없으면 벡터 단독 검색
        if self.ensemble_retriever:
            self._update_ensemble_retriever(k=k)
            return self.ensemble_retriever.invoke(question)
        else:
            self.parent_retriever.search_kwargs = {"k": k}
            return self.parent_retriever.invoke(question)

