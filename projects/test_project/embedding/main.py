from langchain_community.document_loaders import WikipediaLoader, Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader, JSONLoader
from langchain_community.document_loaders import DirectoryLoader
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

import os, sys, time
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QSplitter, QTextEdit, QSizePolicy, QPushButton
from PyQt5.QtCore import Qt

import os

class test(QWidget):
    def split_and_import(self, loader):
        #텍스트 분할
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
        #엠베딩보델
        embedding_model = OpenAIEmbeddings(openai_api_key="api_key")
        #벡터스토어 생성
        vector_db = Chroma("tourist_info", embedding_model)
        
        print(loader)
        chunks = text_splitter.split_documents(loader.load())
        vector_db.add_documents(chunks)
        print(f"Ingested chunks created by {loader}")


    def get_loader(self, filename):
        loader_classes = {
            'docx': Docx2txtLoader,
            'pdf': PyPDFLoader,
            'txt': TextLoader,
            'csv': CSVLoader,
            'json': JSONLoader
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
        
    def run(self):
        path  = "D:/AI_team/github/데이터 생성/1/seperate"
        lst = os.listdir(path)
        print(lst)
        for i in lst:
            if not i.startswith('.'):
                print(i)

                file = os.path.join(path, i)
                print(file)        
                self.split_and_import(self.get_loader(file))

if __name__ == '__main__':
    # app = QApplication(sys.argv)
    ex = test()
    ex.show()
    ex.run()
    # sys.exit(app.exec_())
    
# results = vector_db.search(
#     query="what is chapter 1?",
#     search_type="similarity"
# )
# print(results)
