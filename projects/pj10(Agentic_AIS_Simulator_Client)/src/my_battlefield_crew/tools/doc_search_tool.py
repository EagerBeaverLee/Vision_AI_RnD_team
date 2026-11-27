import os
import asyncio
from typing import List
from crewai.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.documents import Document
from my_battlefield_crew.setting.rag_config import RAGConfig, IndexingType, QuestionTransformType
from langchain_community.vectorstores import FAISS
# from tools.default_retriever import DefaultDocumentRetriever
from my_battlefield_crew.RAG.Retriever.parent_keyword_retriever import ParentKeywordRetrieverPipeline
# from my_battlefield_crew.RAG.Multiple_questions_Gen import MultipleQuestionGenerator
from my_battlefield_crew.chainlit_app.schemas import SimulationContext

from my_battlefield_crew.RAG.Generator.Default_Gen import DefaultGenerator
from my_battlefield_crew.RAG.Generator.Rewrite_Retrieve_Read_Gen import RewriteRetrieveReadQuestionGenerator
from my_battlefield_crew.RAG.Generator.Step_Back_Question_Gen import StepBackQuestionGenerator
from my_battlefield_crew.RAG.Generator.Multiple_Questions_Gen import MultipleQuestionGenerator
from my_battlefield_crew.setting.LLM_model_set import vllm_llm
# retriever = DefaultDocumentRetriever()
# retriever.load_folder()

# retriever=ParentKeywordRetrieverPipeline()
# retriever.load_folder()

#기본  retriever 추출
# base_retriever = retriever.default_db.as_retriever(search_kwargs={"k":3}) #this is for DefaultDocumentRetriever
# base_retriever = retriever.retriever
# multi_query_gen = MultipleQuestionGenerator()

def _run_document_search(context: SimulationContext) -> str:
     try:
        # print(f">>> [RAG TOOL] {context.rag_pipe.retriever}\n{context.rag_pipe.vector_store}")
        
        key = context.rag_pipe.rag_config.question_transform
        selected_key = key.value if hasattr(key, "value") else str(key)
        
        if context.ui_handler:
            context.ui_handler.on_tool_progress("VectorDB 검색", "사내 문서/데이터베이스에서 질문에 필요한 내용을 검색합니다.")

        generator_map = {
            QuestionTransformType.DEFAULT.value: lambda: DefaultGenerator(
                llm=vllm_llm
            ),
            QuestionTransformType.REWRITE_RETRIEVE_READ.value: lambda: RewriteRetrieveReadQuestionGenerator(
                llm=vllm_llm
            ),
            QuestionTransformType.MULTIPLE_QUESTIONS.value: lambda: MultipleQuestionGenerator(
                llm=vllm_llm
            ),
            QuestionTransformType.STEP_BACK.value: lambda: StepBackQuestionGenerator(
                llm=vllm_llm
            ),
        }

        generator_creator = generator_map.get(selected_key, generator_map[QuestionTransformType.DEFAULT.value])
        selected_gen = generator_creator()
        docs = selected_gen.search_docs(context)
        # docs = generator_map[context.rag_pipe.rag_config.question_transform].search_docs(context)

        # print("#" * 10 + "[RAGCrew]문서검색 결과" + "#" * 10)
        # print(docs)
        if not docs:
            return "관련 문서를 찾을 수 없습니다."

        if context.ui_handler:
            context.ui_handler.on_tool_complete("VectorDB 검색")
            context.ui_handler.on_tool_result("VectorDB 검색")
        return "\n\n".join(doc.page_content for doc in docs)

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



