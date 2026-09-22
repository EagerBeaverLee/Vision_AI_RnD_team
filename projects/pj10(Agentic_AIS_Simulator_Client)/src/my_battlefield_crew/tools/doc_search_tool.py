import asyncio
from crewai.tools import tool
# from tools.default_retriever import DefaultDocumentRetriever
from tools.parent_keyword_retriever import ParentKeywordRetrieverPipeline
from tools.Multiple_questions_Gen import MultipleQuestionGenerator

# retriever = DefaultDocumentRetriever()
# retriever.load_folder()

retriever=ParentKeywordRetrieverPipeline()
retriever.load_folder()

#기본  retriever 추출
# base_retriever = retriever.default_db.as_retriever(search_kwargs={"k":3}) #this is for DefaultDocumentRetriever
base_retriever = retriever.retriever
multi_query_gen = MultipleQuestionGenerator()

def _run_document_search(query: str) -> str:
     try:
        multi_retriever = multi_query_gen.get_multi_query_retriever(base_retriever)
        docs = multi_retriever.invoke(query) 

        if not docs:
            return "관련 문서를 찾을 수 없습니다."
        return retriever.format_docs(docs)

     except Exception as e:
             return f"문서 검색 중 오류가 발생했습니다: {str(e)}"   

@tool("Document Search Tool")
async def search_document_tool(query: str) -> str:
    """사내 문서/데이터베이스에서 질문에 필요한 내용을 검색합니다."""
    output = await asyncio.to_thread(_run_document_search, query)
    return output



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



