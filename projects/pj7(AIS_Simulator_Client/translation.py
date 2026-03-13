import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)

prompt_template = """
    너는 최고의 번역가야
    {content}로 들어오는 영어 문장을 최대한 똑같이 생략없도록 한글로 번역해주고
    포맷을 최대한 똑같이 유지해줘 그리고 그 번역이 정확한지 검증도 한번 해줘
    
    답변:
"""
prompt = ChatPromptTemplate.from_template(prompt_template)

llm = ChatOpenAI(
    api_key="ai",
    model="openai/gpt-oss-20b",
    base_url="http://192.168.0.108:8000/v1",
    temperature=0.1,
)

trans_chain = (
    RunnableLambda()
    | prompt
    | llm
    | StrOutputParser
)
pdfres = []
path = "D:\\AI_team\\github\\데이터 생성\\영어\\1\\seperate"
folder = os.listdir(path)
for i in folder:
    file = os.path.join(path, folder[0])
    read = PyPDFLoader(file)
    chunk = splitter.split_documents(read.load())
    for i, doc in enumerate(chunk):
        lst = {"content": doc.page_content}
        res = trans_chain.invoke(lst)
        pdfres.append(res)
        print(f"{i+1} : {doc.page_content}")