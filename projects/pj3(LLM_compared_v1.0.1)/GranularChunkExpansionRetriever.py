from PyQt5.QtCore import pyqtSignal, QObject

from langchain.storage import InMemoryByteStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain.retrievers.multi_vector import MultiVectorRetriever
import uuid
import os

class GranularChunkExpansionRetriverPipeline(QObject):
    finished = pyqtSignal()
    progresses = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self,folder_path: str, openai_api_key: str, granular_chunk_size: int = 500, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        #Defining Splitter
        self.granular_chunk_splitter = RecursiveCharacterTextSplitter(chunk_size=granular_chunk_size)
        self.embedding_model = OpenAIEmbeddings(openai_api_key=openai_api_key)

        self.dummy_doc = Document(page_content="dummy")
        self.dummy_doc_id = "DUMMY_DOC"  # 임의의 doc_id 지정
        self.dummy_doc.metadata = {"id": self.dummy_doc_id}
        #When using FAISE DB
        self.granular_chunks_collection = FAISS.from_documents([self.dummy_doc], self.embedding_model)
        
        #Expanded Chunks docstore
        self.expanded_chunk_store = InMemoryByteStore() #D
        self.doc_key = "doc_id"

        #retriever linking granular and expanded
        self.retriever = MultiVectorRetriever(
            vectorstore=self.granular_chunks_collection,
            byte_store=self.expanded_chunk_store
        )

        #supported loaders
        self.loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader
        }
        
    def remove_dummy_doc(self):
        # docstore 내부 dict에서 doc_id 확인
        doc_ids = [doc_id for doc_id in self.granular_chunks_collection.docstore._dict
                   if self.granular_chunks_collection.docstore._dict[doc_id].metadata.get("id") == self.dummy_doc_id]
        if doc_ids:
            self.granular_chunks_collection.delete(doc_ids)
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

    def run(self):
        files = os.listdir(self.folder_path)
        total_files = len(files)

        progress_step = 100 / total_files

        """Load all documents from a folder into the retriever pipeline"""
        for j, filename in enumerate(files):
            file_path = os.path.join(self.folder_path, filename)
            if os.path.isfile(file_path):
                try:
                    loader = self.get_loader(file_path)
                    print(f"Loader for {filename}:{loader}")
                    docs = loader.load() 
                    granular_chunks = self.granular_chunk_splitter.split_documents(docs)
            
                    expanded_chunk_store_items = []
                    for i, granular_chunk in enumerate(granular_chunks):
                        try:
                            this_chunk_num = i
                            previous_chunk_num = i-1
                            next_chunk_num = i+1
                    
                            if i==0:
                                previous_chunk_num = None
                            elif i==(len(granular_chunks)-1):
                                next_chunk_num = None
                    
                            expanded_chunk_text = ""
                            if previous_chunk_num:
                                expanded_chunk_text += granular_chunks[previous_chunk_num].page_content
                                expanded_chunk_text += "\n"
                            
                            expanded_chunk_text += granular_chunks[this_chunk_num].page_content #G
                            expanded_chunk_text += "\n"
                            if next_chunk_num: #G
                                expanded_chunk_text += granular_chunks[next_chunk_num].page_content
                                expanded_chunk_text += "\n"
                            
                            expanded_chunk_id = str(uuid.uuid4())
                            expanded_chunk_doc = Document(page_content=expanded_chunk_text)
                    
                            expanded_chunk_store_item = (expanded_chunk_id, expanded_chunk_doc)
                            expanded_chunk_store_items.append(expanded_chunk_store_item)
                    
                            granular_chunk.metadata[self.doc_key] = expanded_chunk_id # link each granular chunk to its related expanded chunk 
                        except Exception as e:
                            self.error.emit(f"{granular_chunk} 청크 처리중 오류 발생: {e}")
                            print(e)
            
                    print(f'Ingesting{filename}')
                    curr_progress = (j + 1) * progress_step
                    self.progresses.emit(int(curr_progress))

                    self.retriever.vectorstore.add_documents(granular_chunks)
                    self.retriever.docstore.mset(expanded_chunk_store_items)

                except Exception as e:
                    self.error.emit(f"{filename} 파일 임베딩 중 오류 발생: {e}")
                    print(e)
        print(f"ALL PROCESSING FOR GRANULAR CHUNK EXPANSION COMPLETED")

        self.progresses.emit(100)
        self.finished.emit()
    
    def format_docs(self, docs):
        """Format retrieved docs into a single string."""
        return "\n\n".join(doc.page_content for doc in docs)
    
    def copy_retriever(self):
        return self.retriever

    def query(self, question: str) -> str:
        retrieved_parent_doc = self.retriever.invoke(question)
        return retrieved_parent_doc        # self.format_docs(retrieved_parent_doc) #<- if you want to format final output. 
    
## GranularChunkExpansionRetriever 사용 예제 ###

# granular_exp_pipeline = GranularChunkExpansionRetriverPipeline(openai_api_key=openai_api_key, granular_chunk_size=500)
# granular_exp_pipeline.remove_dummy_doc()

# folder_path = "documents/tactic_north_korea"
# granular_exp_pipeline.load_folder(folder_path)

# #### Retrievding granular chunks
# question = "north korean caste system"
# granular_chunk = granular_exp_pipeline.retriever.vectorstore.similarity_search_with_score(question)
# granular_chunk

# #### Retrievding expanded chunks
# expanded_chunks = granular_exp_pipeline.retriever.invoke(question)
# expanded_chunks

# #### Rrtrieving text chunks with internal .query function
# retrieved_texts = granular_exp_pipeline.query(question)
# retrieved_texts