###################################################
### HypotheticalQuestionRetrieverPipeline Class ###
###################################################
import os, time, concurrent.futures
from PyQt5.QtCore import pyqtSignal, QObject

from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryByteStore
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

class HypotheticalQuestionRetrieverPipeline(QObject):
    finished = pyqtSignal()
    progresses = pyqtSignal(int)
    error = pyqtSignal(str)
    changeUi = pyqtSignal()
    
    def __init__(self,folder_path: str, openai_api_key: str, llm_model, 
                 parent_chunk_size: int = 3000, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        #defining splitter
        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size=parent_chunk_size)
        self.embedding_model = OpenAIEmbeddings(openai_api_key=openai_api_key)

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
        for filename in os.listdir(self.folder_path):
            file_path = os.path.join(self.folder_path, filename)
            if os.path.isfile(file_path):
                loader = self.get_loader(file_path)
                print(f"Loader for {filename}: {loader}")
                docs = loader.load()
                chunks = self.parent_splitter.split_documents(docs)
                chunks_ids = [str(uuid.uuid4()) for _ in chunks]

                self.coarse_chunks.extend(chunks)
                self.coarse_chunks_ids.extend(chunks_ids)
                print(f"Chunking and id_assignment for {filename} has been completed")

        print(f"ALL PROCESS COMPLETED!!")

    # Parallelization Function 
    def run(self, max_workers=100):
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
            hypothetical_questions = self.hypothetical_questions_chain.invoke(coarse_chunk)
            return [Document(
                page_content = question,
                metadata = {self.doc_key: coarse_chunk_id, "source": coarse_chunk.metadata.get("source")},
                id = str(uuid.uuid4()),
                )
                for question in hypothetical_questions]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            all_documents = []

            # for docs in executor.map(hypotheticalQs_chunk, coarse_chunks, coarse_chunks_ids):
            #     #docs는 list[Document], extend로 평탄화
            #     all_documents.extend(docs)

            tasks = {
                executor.submit(hypotheticalQs_chunk, chunk, chunk_id): chunk_id
                for chunk, chunk_id in zip(self.coarse_chunks, self.coarse_chunks_ids)
            }

            completed_count = 0
            total_tasks = len(self.coarse_chunks)

            for res in concurrent.futures.as_completed(tasks):
                query = tasks[res]
                try:
                    result = res.result()
                    all_documents.extend(result)

                    completed_count += 1
                    percent = int((completed_count / total_tasks)*100)
                    self.progresses.emit(percent)
                    # print(f"[{completed_count}/{total_tasks}] 완료: {result[0].page_content[:100]}")
                    print(f"[{completed_count}/{total_tasks}] 완료: {result[0].page_content[:100]}")
                except Exception as e:
                    self.error.emit(f"쿼리{query} 실행 중 오류 발생: {e}")
                    print(f"쿼리 {query} 실행 중 오류 발생: {e}")
                    self.finished.emit()
        
        #Adding summaries to vectorstore    
        # self.retriever.vectorstore.add_documents(i for i in all_documents)
        self.retriever.vectorstore.add_documents(all_documents)

        for chunk, chunk_id in zip(self.coarse_chunks, self.coarse_chunks_ids):
            chunk.metadata[self.doc_key] = chunk_id
            chunk.id = chunk_id

        #Adding coarse_chunks to docstore along with IDs
        self.retriever.docstore.mset(list(zip(self.coarse_chunks_ids, self.coarse_chunks)))
        self.finished.emit()
        self.changeUi.emit()
        return all_documents
 
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