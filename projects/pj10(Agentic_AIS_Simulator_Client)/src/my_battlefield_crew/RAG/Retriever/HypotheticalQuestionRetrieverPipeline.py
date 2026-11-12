###################################################
### HypotheticalQuestionRetrieverPipeline Class ###
###################################################
import os, time, concurrent.futures
from PyQt6.QtCore import pyqtSignal, QObject
import threading

# from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_classic.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.stores import InMemoryByteStore
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from concurrent.futures import ThreadPoolExecutor
import uuid
from typing import List
from pydantic import BaseModel, Field
import os

class InMemoryByteStoreWithId(InMemoryByteStore):
    
    def get(self, keys):
        docs = super().get(keys)
        for d in docs:
            d.id = d.metadata.get("doc_id")
        return docs

class HypotheticalQuestionRetrieverPipeline:    
    def __init__(self,folder_path: str, openai_api_key: str, llm_model, 
                 parent_chunk_size: int = 3000):
        print(f"hypo_chunk_size:{parent_chunk_size}\n")
        self.folder_path = folder_path
        #defining splitter
        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size=parent_chunk_size)
        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=openai_api_key, 
            model="text-embedding-3-small"
        )

        # self.dummy_doc = Document(page_content="dummy")
        # self.dummy_doc_id = "DUMMY_DOC"  # 임의의 doc_id 지정
        # self.dummy_doc.metadata = {"id": self.dummy_doc_id}
        
        self.dummy_doc_id = "DUMMY_DOC"
        self.dummy_doc = Document(page_content="dummy", metadata={"id": self.dummy_doc_id}, id=self.dummy_doc_id) ##revised!!

        #When using FAISS DB
        self.hypothetical_question_collection = FAISS.from_documents([self.dummy_doc], self.embedding_model)

        self.doc_byte_store = InMemoryByteStore()
        self.doc_key = "doc_id"

        self.retriever = MultiVectorRetriever(
            vectorstore = self.hypothetical_question_collection, 
            byte_store = self.doc_byte_store
        )

        self.coarse_chunks = []
        self.coarse_chunks_ids = []

        class HypotheticalQuestions(BaseModel):
            """Generate hypothetical questions for given text."""
            questions: List[str] = Field(..., description="List of hypothetical questions for given text")

        self.llm_with_structured_output = llm_model.with_structured_output(HypotheticalQuestions)
        
        #defining hypothetical question generation chain
        self.hypothetical_questions_chain = (
            {"document_text": lambda x: x.page_content}
            | ChatPromptTemplate.from_template(
                "Generate a list of exactly 4 hypothetical questions that the below text could be used to answer:\n\n{document_text}"
            )
            | self.llm_with_structured_output
            | (lambda x: x.questions)
        )

        #supported loaders
        self.loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader
        }

    def remove_dummy_doc(self):
        # docstore 내부 dict에서 doc_id 확인
        doc_ids = [doc_id for doc_id in self.hypothetical_question_collection.docstore._dict
                   if self.hypothetical_question_collection.docstore._dict[doc_id].metadata.get("id") == self.dummy_doc_id]
        if doc_ids:
            self.hypothetical_question_collection.delete(doc_ids)
            print(f"Removed dummy doc with id {self.dummy_doc_id}")
        else:
            print("No dummy doc found")    

    def get_loader(self, filename: str):
        _, file_extension = os.path.splitext(filename)
        file_extension = file_extension.lstrip('.').lower()
        loader_class = self.loader_classes.get(file_extension)
        if not loader_class:
            raise ValueError(f"No loader available for file extension '{file_extension}'")
        return loader_class(filename)

    def data_loading_chunking(self):
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

        for filename in files:
            loader = self.get_loader(filename)
            print(f"Loader for {filename}: {loader}")
            docs = loader.load()
            chunks = self.parent_splitter.split_documents(docs)
            chunks_ids = [str(uuid.uuid4()) for _ in chunks]

            self.coarse_chunks.extend(chunks)
            self.coarse_chunks_ids.extend(chunks_ids)
            print(f"Chunking and id_assignment for {filename} has been completed")

    # Parallelization Function 
    def run(self, cancel_flag: threading.Event, max_workers=100):
        print("hypothetical_retriever 시작")
        self.data_loading_chunking()
        """
        Generating hypothetical questions for a list of chunks in parallel.

        Args:
            coarse_chunks (list): 입력 문서 청크들
            coarse_chunks_ids (list):  각 청크 조각의 ID
            max_workers (int): 동시 실행 가능한 thread 개수 (기본값 100으로 설정 vllm 기준)

        returns: Document 객체 리스트
        """
        if max_workers is None:
            max_workers = self.max_workers

        def hypotheticalQs_chunk(coarse_chunk, coarse_chunk_id):
            if cancel_flag.is_set():
                return None
            hypothetical_questions = self.hypothetical_questions_chain.invoke(coarse_chunk)
            return [Document(
                page_content = question,
                metadata = {self.doc_key: coarse_chunk_id, "source": coarse_chunk.metadata.get("source")},
                id = str(uuid.uuid4()),
                )
                for question in hypothetical_questions]

        max_workers=100
        results = []
        total_tasks = len(self.coarse_chunks)
        completed_count = 0
        
        executor = ThreadPoolExecutor(max_workers=max_workers)
        tasks = {}

        try:
            tasks = {
                executor.submit(hypotheticalQs_chunk, chunk, chunk_id): chunk_id
                for chunk, chunk_id in zip(self.coarse_chunks, self.coarse_chunks_ids)
            }

            completed_count = 0
            total_tasks = len(self.coarse_chunks)

            for res in concurrent.futures.as_completed(tasks):
                if cancel_flag.is_set():
                    print("[HypotheticalRetriever] 취소 신호 감지: 대기 중인 퓨처 전체 취소")
                    # 아직 스레드에 할당되지 않고 큐에 대기 중인 작업들 취소
                    for t in tasks:
                        t.cancel()
                    break

                query = tasks[res]
                try:
                    result = res.result()
                    # 💡 취소되었거나(None) 생성된 질문이 없는 빈 리스트([])인 경우 스킵
                    if not result:
                        continue

                    results.extend(result)
                    completed_count += 1
                    percent = int((completed_count / total_tasks)*100)

                    yield f"{percent}\n"
                    # 💡 result가 비어있지 않을 때만 안전하게 첫 번째 질문 출력
                    first_q_preview = result[0].page_content[:60] if len(result) > 0 else ""
                    print(f"[{completed_count}/{total_tasks}] 완료: {first_q_preview}")
                except Exception as e:
                    print(f"쿼리 {query} 실행 중 오류 발생: {e}")

        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if cancel_flag.is_set():
            print("[HypotheticalRetriever] 임베딩 작업 취소 완료")
            yield "CANCELLED\n"
            return
        
        #Adding summaries to vectorstore    
        # self.retriever.vectorstore.add_documents(i for i in all_documents)
        self.retriever.vectorstore.add_documents(results)

        for chunk, chunk_id in zip(self.coarse_chunks, self.coarse_chunks_ids):
            chunk.metadata[self.doc_key] = chunk_id
            chunk.id = chunk_id

        #Adding coarse_chunks to docstore along with IDs
        self.retriever.docstore.mset(list(zip(self.coarse_chunks_ids, self.coarse_chunks)))
        print("[HypotheticalRetriever] FAISS 및 Docstore 적재 완료")
        yield "COMPLETE\n"
 
    def format_docs(self, docs):
        """Format retrieved docs into a single string."""
        return "\n\n".join(doc.page_content for doc in docs)
    
    def copy_retriever(self):
        return self.retriever

    def query(self, question: str) -> str:
        retrieved_summary_doc = self.retriever.invoke(question)
        return retrieved_summary_doc #if you wnat to format doc, then use self.format_docs(retrieved_summary_doc) 
    



## 사용 예제
# hypothetical_pipe = HypotheticalQuestionRetrieverPipeline(openai_api_key=openai_api_key, llm_model=vllm)
# hypothetical_pipe.remove_dummy_doc()

# file_path = "documents/tactic_north_korea"
# chunks, ids = hypothetical_pipe.data_loading_chunking(file_path)

# all_questions = hypothetical_pipe.hypotheticalQs_chunks_parallel(chunks, ids, max_workers=200)

# question = 'What are the eight operational variables that define a North Korean operational environment according to the Department of Defense?'

# retrieved_texts = hypothetical_pipe.query(question)
# retrieved_texts
# retrieved_questions = hypothetical_pipe.retriever.vectorstore.similarity_search(question)
# retrieved_questions