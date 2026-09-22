#------------------------------------
# Parent Child  + TF-IDF Retriever 
#-----------------------------------
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

from kiwipiepy import Kiwi

load_dotenv()

from langchain_classic.retrievers import ParentDocumentRetriever, EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_classic.storage import LocalFileStore, create_kv_docstore
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document


project_root = Path(__file__).resolve().parent.parent
default_index_path = str(project_root / "data" / "doctrine_data" / "parent_faiss_index")
default_docstore_path = str(project_root / "data" / "doctrine_data" / "parent_docstore")
default_data_path = str(project_root / "data" / "doctrine_data" / "raw_documents")


kiwi = Kiwi()

def kiwi_tokenize(text: str) -> list[str]:
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

        # Parent Document 저장소
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

        # 이미 데이터가 저장되어 있는 경우 BM25 리트리버 자동 구축
        self._init_bm25_from_docstore()

    def _init_bm25_from_docstore(self):
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
            self._update_ensemble_retriever()

    def _update_ensemble_retriever(self, k: int = 3):
        """Vector Retriever와 BM25 Retriever를 결합한 Ensemble Retriever 구축"""
        if self.bm25_retriever:
            self.parent_retriever.search_kwargs = {"k": k}
            self.bm25_retriever.k = k

            # weights=[0.5, 0.5]: 벡터 검색 50% + 키워드 검색 50% 반영
            self.ensemble_retriever = EnsembleRetriever(
                retrievers=[self.parent_retriever, self.bm25_retriever],
                weights=[0.3, 0.7]
            )

            self.retriever = self.ensemble_retriever

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

    def load_folder(self, folder_path: str = default_data_path):
        """raw_documents 폴더 문서 저장 및 BM25 + FAISS 빌드"""
        if os.path.exists(os.path.join(self.index_path, "index.faiss")) and self.bm25_retriever:
            print("FAISS DB 및 BM25가 이미 준비되어 생성을 스킵합니다.")
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

        self.parent_retriever.vectorstore.save_local(self.index_path)
        # 새로 임베딩 후 BM25 리트리버 재구성
        self._init_bm25_from_docstore()
        print(f"Parent FAISS & BM25 하이브리드 DB 저장 완료")

    def format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def query(self, question: str, k: int = 3):
        # BM25가 준비되어 있다면 하이브리드 검색, 없으면 벡터 단독 검색
        if self.ensemble_retriever:
            self._update_ensemble_retriever(k=k)
            return self.ensemble_retriever.invoke(question)
        else:
            self.parent_retriever.search_kwargs = {"k": k}
            return self.parent_retriever.invoke(question)



































# if __name__ == "__main__":
#     parent_retriever_pipeline = ParentRetrieverPipeline()
#     parent_retriever_pipeline.load_folder()

#     retrieved_texts = parent_retriever_pipeline.query("저시정 항해시 조치사항", k=3)
#     print(parent_retriever_pipeline.format_docs(retrieved_texts))