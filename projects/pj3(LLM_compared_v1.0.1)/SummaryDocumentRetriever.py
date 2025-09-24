import os, time, concurrent.futures
from PyQt5.QtCore import pyqtSignal, QObject

from langchain_community.vectorstores import FAISS
from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryByteStore
# from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
# import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import uuid
import os
# import time


class SummaryDocumentRetrieverPipeline(QObject):
    finished = pyqtSignal()
    progresses = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, folder_path, openai_api_key: str, llm_model, 
                 parent_chunk_size: int = 3000, parent=None):
        super().__init__(parent)

        self.folder_path = folder_path

        #defining splitter
        self.parent_splitter = RecursiveCharacterTextSplitter(chunk_size=parent_chunk_size)
        self.embedding_model = OpenAIEmbeddings(openai_api_key=openai_api_key)

        self.dummy_doc = Document(page_content="dummy")
        self.dummy_doc_id = "DUMMY_DOC"  # 임의의 doc_id 지정
        self.dummy_doc.metadata = {"id": self.dummy_doc_id}
        
        #When using FAISE DB
        self.summaries_collection = FAISS.from_documents([self.dummy_doc], self.embedding_model)

        self.doc_byte_store = InMemoryByteStore()
        self.doc_key = "doc_id"

        self.retriever = MultiVectorRetriever(
            vectorstore = self.summaries_collection, 
            byte_store = self.doc_byte_store
        )

        self.coarse_chunks = []
        self.coarse_chunks_ids = []

        #defining summarization chain
        self.summarization_chain = (
            {"document": lambda x: x.page_content}
            | ChatPromptTemplate.from_template("Summarize the following document:\n\n{document}")
            | llm_model
            | StrOutputParser())

        #supported loaders
        self.loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader
        }

    def remove_dummy_doc(self):
        # docstore 내부 dict에서 doc_id 확인
        doc_ids = [doc_id for doc_id in self.summaries_collection.docstore._dict
                   if self.summaries_collection.docstore._dict[doc_id].metadata.get("id") == self.dummy_doc_id]
        if doc_ids:
            self.summaries_collection.delete(doc_ids)
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

        print(f"Chunking and id assignment completed for folder:{self.folder_path}")

    # Parallelization Function 
    def run(self):
        max_workers=100
        self.data_loading_chunking()
        """
        Summarize a list of chunks in parallel.

        Args:
            coarse_chunks (list): 입력 문서 청크들
            coarse_chunks_ids (list):  각 청크 조각의 ID
            max_workers (int): 동시 실행 가능한 thread 개수 (기본값 100으로 설정 vllm 기준)

        returns: Document 객체 리스트
        """

        def summarize_chunk(coarse_chunk, coarse_chunk_id):
            summary_text = self.summarization_chain.invoke(coarse_chunk)
            return Document(page_content = summary_text, metadata = {self.doc_key: coarse_chunk_id})

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = []

            tasks = {
                executor.submit(summarize_chunk, chunk, chunk_id): chunk_id
                for chunk, chunk_id in zip(self.coarse_chunks, self.coarse_chunks_ids)
            }

            completed_count = 0
            total_tasks = len(self.coarse_chunks)

            for res in concurrent.futures.as_completed(tasks):
                query = tasks[res]
                try:
                    result = res.result()
                    results.append(result)

                    completed_count += 1
                    percent = int((completed_count / total_tasks)*100)
                    self.progresses.emit(percent)
                    print(f"[{completed_count}/{total_tasks}] 완료: {result.page_content[:100]}")
                except Exception as e:
                    self.error.emit(f"쿼리{query} 실행 중 오류 발생: {e}")
                    print(f"쿼리 {query} 실행 중 오류 발생: {e}")
                    self.finished.emit()
        
        #Adding summaries to vectorstore    
        self.retriever.vectorstore.add_documents(results)
        
        #Adding coarse_chunks to docstore along with IDs
        self.retriever.docstore.mset(list(zip(self.coarse_chunks_ids, self.coarse_chunks)))
        self.finished.emit()
        return results
 
    def format_docs(self, docs):
        """Format retrieved docs into a single string."""
        return "\n\n".join(doc.page_content for doc in docs)

    def query(self, question: str) -> str:
        retrieved_summary_doc = self.retriever.invoke(question)
        return retrieved_summary_doc #self.format_docs(retrieved_summary_doc)
    

## 사용 예제

# vllm = ChatOpenAI(
#     api_key = "ai",
#     base_url = "http://192.168.0.108:8000/v1",
#     model = "openai/gpt-oss-20b",
#     # model_name = "unsloth/gemma-3-27b-it-bnb-4bit",
#     # model="meta-llama/Llama-3.1-8B-Instruct",
#     # model="unsloth/Mistral-Small-24B-Instruct-2501-bnb-4bit",
#     # model = "unsloth/Qwen3-14B-bnb-4bit",
#     # model = "unsloth/gemma-3-12b-it-bnb-4bit",
#     # model = "unsloth/gemma-2-9b-it-bnb-4bit",
#     max_tokens = 6000,
#     temperature = 0.2
# )

# summary_pipeline_testing = SummaryDocumentRetrieverPipeline(openai_api_key=OPENAI_API_KEY, llm_model=vllm)
# chunks, ids = pipeline.data_loading_chunking(file_path)
# all_summaries = pipeline.summarize_chunks_parallel(chunks, ids, max_workers)

# question = "north korean caste system"
# retrieved_text = summary_pipeline_testing.query(question)
# retrieved_summary = summary_pipeline_testing.retriever.vectorstore.similarity_search(question)

# print(retrieved_text)
# print("\n\n\n")
# print(retrieved_summary)