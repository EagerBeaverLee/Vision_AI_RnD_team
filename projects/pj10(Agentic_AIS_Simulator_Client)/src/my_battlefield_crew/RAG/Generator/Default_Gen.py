#############################
### Default-Read ###
#############################

from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from my_battlefield_crew.RAG.DocumentPostProcessor import DocumentPostProcessor
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


class DefaultGenerator:
    def __init__(self, llm):        
        self.llm = llm

    def search_docs(self, context: SimulationContext):
        try:
            if context.rag_pipe.retriever is None:
                raise ValueError("Retriever is required to build RAG chain.")
            print("문서 검색 시작"+ "#" * 20)
            docs = context.rag_pipe.post_processor.post_processor(context.user_question, context.rag_pipe.rag_config.post_processing.similarity_threshold, context.rag_pipe.rag_config.post_processing.keywords)
            return docs
        
        except Exception as e:
            print(f"Error while building Default RAG chain: {e}")
            return None
        
    def print_retrieved_document(self, in_dict):
        print("\n--- [디버그] 검색된 문서 ---")
        for i, doc in enumerate(in_dict['context']):
            print(f"문서 #{i+1}: {doc.page_content}")
            if doc.metadata:
                print(f"출처: {doc.metadata.get('source', '알 수 없음')}")
        print("----------------------------\n")
        print(in_dict)
        print("----------------------------\n")
        # 다음 단계로 데이터를 전달하기 위해 받은 딕셔너리를 그대로 반환합니다.
        return in_dict

    def generate_answer(self, user_question: str, retriever=None):
        try:
            if not retriever:
                raise ValueError("Retriever is required to execute RAG chain")
            
            rag_chain = self.build_rewrite_rag_chain(retriever)
            result = rag_chain.invoke({"question": user_question})
            
            return result
        except Exception as e:
            print(f"Error while trying to answer user_question: {e}")



# ##사용예제
# #Initiating 클래스
# generator_testing = RewriteRetrieveReadQuestionGenerator()

# #사용할 Retriever 정의(ex. default, summary, hypothetical, granular_chunk_expansion, etc)
# retriever = default_pipeline.default_db.as_retriever()

# #Qeury 재생성기 사용예제
# re_written_query = generator_testing.rewriter_chain.invoke({"user_question": results[10]})
# re_written_query

# #Chain을 활용한 최종 답변 생성: retriever 입력변수로 입력 필요
# rewriter_chain_testing = generator_testing.build_rewrite_rag_chain(retriever=retriever)
# rewriter_chain_testing.invoke({"user_question":"north korean caste system"})

# #ask함수를 활용한 최종 답변 생성
# answer = generator_testing.generate_answer(user_question="north korean caste system", retriever=retriever)
# answer