from langchain_classic.agents.agent import AgentExecutor
from langchain_classic.agents.openai_tools.base import create_openai_tools_agent
from langchain_classic import hub

from langchain_community.utilities import ArxivAPIWrapper
from langchain_community.tools import ArxivQueryRun

from langchain_core.tools.retriever import create_retriever_tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import WebBaseLoader

from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import WikipediaQueryRun

from langchain_openai import ChatOpenAI

import os

from dotenv import load_dotenv
load_dotenv()

openai = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.1
)

prompt = hub.pull("hwchase17/openai-functions-agent")

api_wraper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=200)

wiki = WikipediaQueryRun(api_wrapper=api_wraper)

print(wiki.name)

loader = WebBaseLoader("https://news.naver.com/")
docs = loader.load()

documents = RecursiveCharacterTextSplitter(
    chunk_size=3000,
    chunk_overlap=200
).split_documents(docs)

vectordb = FAISS.from_documents(documents, OpenAIEmbeddings())
retriever = vectordb.as_retriever()

print(retriever)

retriever_tool = create_retriever_tool(
    retriever, "naver_news_search",
    "네이버 뉴스 정보가 저장된 벡터 DB, 당일 기사에 대해 궁금하면 이 툴을 사용하세요!"
)

print(retriever_tool.name)

arxiv_wrapper = ArxivAPIWrapper(
    top_k_results=1,
    doc_content_chars_max=200,
    load_all_available_meta=False,
)

arxiv = ArxivQueryRun(api_wrapper=arxiv_wrapper)

print(arxiv.name)

tools = [wiki, retriever_tool, arxiv]
agent = create_openai_tools_agent(
    llm=openai,
    tools=tools,
    prompt=prompt
)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

agent_result = agent_executor.invoke({"input": "오늘 부동산 관련 주요 소식을 알려줘"})
print(agent_result)