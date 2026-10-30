import os
import asyncio
from typing import List
from crewai.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.documents import Document
from my_battlefield_crew.setting.rag_config import RAGConfig
from langchain_community.vectorstores import FAISS
# from tools.default_retriever import DefaultDocumentRetriever
from my_battlefield_crew.RAG.Retriever.parent_keyword_retriever import ParentKeywordRetrieverPipeline
from my_battlefield_crew.RAG.Multiple_questions_Gen import MultipleQuestionGenerator
from my_battlefield_crew.chainlit_app.schemas import SimulationContext

# retriever = DefaultDocumentRetriever()
# retriever.load_folder()

retriever=ParentKeywordRetrieverPipeline()
retriever.load_folder()

#기본  retriever 추출
# base_retriever = retriever.default_db.as_retriever(search_kwargs={"k":3}) #this is for DefaultDocumentRetriever
base_retriever = retriever.retriever
multi_query_gen = MultipleQuestionGenerator()

def _run_document_search(context: SimulationContext) -> str:
     try:
        print(f">>> [RAG TOOL] RAG 설정이 tool까지 잘 전달됨:\n {context.rag_config.question_transform}\n{context.rag_config.indexing.strategy}\n{context.rag_config.post_processing}")
        
        if not context.vector_store:
            return f"[검색 오류] FAISS 인덱스 파일이 존재하지 않습니다. Qt에서 먼저 폴더를 로드해주세요."

        if context.ui_handler:
            context.ui_handler.on_tool_progress("VectorDB 검색", "사내 문서/데이터베이스에서 질문에 필요한 내용을 검색합니다.")

        
        multi_retriever = multi_query_gen.get_multi_query_retriever(base_retriever)
        docs = multi_retriever.invoke(context.user_question)

        if not docs:
            return "관련 문서를 찾을 수 없습니다."

        if context.ui_handler:
            context.ui_handler.on_tool_complete("VectorDB 검색")
            context.ui_handler.on_tool_result("VectorDB 검색")
        return retriever.format_docs(docs)

     except Exception as e:
             return f"문서 검색 중 오류가 발생했습니다: {str(e)}"   

def search_document_tool(context: SimulationContext):
    @tool("Document Search Tool")
    async def _search_document_tool() -> str:
        """사내 문서/데이터베이스에서 질문에 필요한 내용을 검색합니다."""
        if context.ui_handler:
            context.ui_handler.on_tool_start("VectorDB 검색", "사내 문서/데이터베이스에서 질문에 필요한 내용을 검색합니다.")
        output = await asyncio.to_thread(_run_document_search, context)
        return output
    return _search_document_tool



    # try:
    #     multi_retriever = multi_query_gen.get_multi_query_retriever(base_retriever)
    #     docs = await asyncio.to_thread(multi_retriever.invoke, query)

    #     if not docs:
    #         return "관련 문서를 찾을 수 없습니다."
    #     return retriever.format_docs(docs)

    # except Exception as e:
    #     return f"문서 검색 중 오류가 발생했습니다: {str(e)}"   

# if __name__ == "__main__":
#     r_docs = asyncio.run(search_document_tool(query = "태풍 권역 인근을 항해할 예정인 화물선에서 갑판장에게 상갑판 배수구(Scupper) 주변 적재물을 정리"))    
#     print(r_docs) 



