import os
import threading

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader, DirectoryLoader
# from langchain_teddynote.document_loaders import HWPLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

class DefaultRetriever:
    def __init__(self, folder_path, api_key):
        self.folder_path = folder_path
        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=api_key, 
            model="text-embedding-3-small"
        )
        # self.embedding_model = HuggingFaceEmbeddings(
        #     model_name="BAAI/bge-m3",
        #     model_kwargs={'device': 'cuda'},
        #     encode_kwargs={'normalize_embedding': True}
        # )
        # self.embedding_model = OpenAIEmbeddings(
        #     model="Qwen/Qwen3-Embedding-8B",
        #     openai_api_base="http://192.168.0.108:8001/v1",
        #     openai_api_key="em"
        # )
        self.text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", ".", " ", ""],
            chunk_size=2000,
            chunk_overlap=250
        )
        self.retriever = None

    def get_loader(self, filename):
        loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader,
            'csv': CSVLoader,
            'json': JSONLoader,
            # 'hwp': HWPLoader
        }

        _, file_extension = os.path.splitext(filename)
        file_extension = file_extension.lstrip('.')

        loader_class = loader_classes.get(file_extension)

        if not loader_class:
            raise ValueError(f"No loader available for file extension '{file_extension}'")
        
        # JSON 파일인 경우 jq_schema 인자를 추가하여 반환
        if file_extension == 'json':
            return loader_class(filename, jq_schema='.', text_content=False)
        else:
            # 그 외의 경우 일반적인 방식으로 로더 반환
            return loader_class(filename)
        
    def run(self, cancel_flag: threading.Event):
        try:
            flag = 1    #0:생성, 1:로드
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

            # 확인용 출력 (["파일1", "파일2", ...] 형태로 출력됨)
            print(f"처리할 파일 목록 (files): {files}")
            total_files = len(files)

            # save_vector = "./test_faiss_embedding"
            save_vector = "./src/my_battlefield_crew/data/doctrine_data/faiss_default"

            if total_files == 0:
                print("[default_retriever]선택한 폴더에 파일이 없습니다.")
                yield "CANCELLED\n"
            
            progress_step = 100 / total_files
            print(f"게이지 분할 값: {progress_step}")

            for i, file in enumerate(files):
                if cancel_flag.is_set():
                    print("[DefaultRetriever Worker Thread] 취소 신호 감지, 동기 루프 탈출")
                    return
                # file_path = os.path.join(input_path, file_name)
                try:
                    loader = self.get_loader(file)
                    print(f"선택된 로더: {loader}")
                    chunks = self.text_splitter.split_documents(loader.load())

                    if flag == 0:
                        if self.retriever:
                            self.retriever.add_documents(chunks)
                        else:
                            self.retriever = FAISS.from_documents(chunks, self.embedding_model)
                    
                    curr_progress = (i + 1) * progress_step
                    yield f"{curr_progress}\n"
                    
                except Exception as e:                    
                    print(f"[default_retriever]: {file} 파일 임베딩 중 오류 발생: {e}")

            if flag == 0:
                self.retriever.save_local(save_vector)
                print("FAISS 벡터스토어 생성 및 저장 완료")
            else:
                self.retriever = FAISS.load_local(save_vector, self.embedding_model, allow_dangerous_deserialization=True)
                print("FAISS 벡터스토어 로드 완료")

            yield "COMPLETE\n"

        except Exception as e:
            print(f"오류: {e}")
            yield "CANCELLED\n"

    def copy_vectorstore(self):
        if self.retriever is None:
            print("vectorDB가 없습니다")
            return
        return self.retriever
        
    
    def copy_retriever(self):
        if self.retriever is None:
            print("vectorDB가 없습니다")
            return
        retriever = self.retriever.as_retriever(search_kwargs={"k": 4})
        return retriever
        

    def query(self, question: str) -> str:
        retriever = self.retriever.as_retriever(search_kwargs={"k": 4})
        query_res = retriever.invoke(question)
        return query_res