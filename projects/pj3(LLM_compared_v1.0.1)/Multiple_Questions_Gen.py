######################################
### 2) Generating multiple queries ###
######################################
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_core.prompts import ChatPromptTemplate
from typing import List
from langchain_core.output_parsers import BaseOutputParser
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnablePassthrough
import os
from dotenv import load_dotenv
# from langchain_together.chat_models import ChatTogether

#vllm정의
# load_dotenv() # Load environment variables from a .env file if present
# api_key = os.getenv("TOGETHER_API_KEY") #api_key는 .env파일에 저장 함

# if not api_key:
#     #환경 변수가 없을 경우 예외 처리
#     print("TOGETHER_API_KEY가 환경 변수로 설정되지 않았습니다.")

# else: 
#     print("API KEY가 성공적으로 로드되었습니다")

# vllm = ChatTogether(model="openai/gpt-oss-20b", max_tokens=6000) #Together AI API사용 중...Local Vllm으로 대체되어야 함. 



class LineListOutputParser(BaseOutputParser[List[str]]):
    """Parse out a question from each output line"""
    
    def parse(self, text: str) -> List[str]:
        lines = text.strip().split("\n")
        return list(filter(None, lines))

    
class MultipleQuestionGenerator:
    def __init__(self, llm):
        
        self.llm = llm
        
        #Prompt Template 
        self.multi_query_gen_prompt_template = """
        You are an AI language model assistant. Your task is to generate five 
        different versions of the given user question to retrieve relevant documents from a vector 
        database. By generating multiple perspectives on the user question, your goal is to help
        the user overcome some of the limitations of the distance-based similarity search. 
        Provide these alternative questions separated by newlines.
        Original question: {question}
        """
        self.rag_prompt_template = """
        Given a question and some context, answer the question.
        If you do not know the answer, just say I do not know. 
        
        Context: {context}
        Question: {question}"""

        self.questions_parser = LineListOutputParser()
        self.init_prompts()
        self.init_chains()
        
    def init_prompts(self):
        self.multiple_question_prompt = ChatPromptTemplate.from_template(self.multi_query_gen_prompt_template)
        self.rag_prompt = ChatPromptTemplate.from_template(self.rag_prompt_template)

    def init_chains(self):
        # multi-query 생성 체인
        self.multi_query_gen_chain = self.multiple_question_prompt | self.llm | self.questions_parser

    def multi_query_retriever(self, retriever = None):
        try:
            if not retriever:
                raise ValueError("Retriever is required to execute this function")
           
            multi_query_retriever = MultiQueryRetriever(
                retriever = retriever, llm_chain = self.multi_query_gen_chain, parser_key = "lines")
            
            return multi_query_retriever

        except Exception as e:
            print(f"Error while building multi_query_generator: {e}")  
    
    def build_rag_chain(self, prompt, retriever = None):
        try:
            if not retriever:
                raise ValueError("Retriever is required to build RAG chain.")
            
            multiple_questions_rag_chain = (
                {
                    "context": {"question": RunnablePassthrough()} | self.multi_query_retriever(retriever),
                    "question": RunnablePassthrough(),
                }
                # | self.rag_prompt
                | prompt
                | self.llm
                )
            return multiple_questions_rag_chain

        except Exception as e:
            print(f"Error while building multiple question RAG chain: {e}")
            return None

    def generate_answer(self, user_question: str, retriever=None):
        try:
            if not retriever:
                raise ValueError("Retriever is required to execute RAG chain")
            
            rag_chain = self.build_multiple_question_rag_chain(retriever)
            result = rag_chain.invoke({"user_question": user_question})
            
            return result
        except Exception as e:
            print(f"Error while trying to answer user_question: {e}")


###사용예제
# MultipleQuestionGenerator활성화
# multiple_generator = MultipleQuestionGenerator()

# # 다중 질문 생성 방법
# user_question = results[12]
# generated_questions = multiple_generator.multi_query_gen_chain.invoke({"question": user_question})

# # 생성된 다중질문 결과확인
# print(f"Original Question: {user_question}\n")
# print("="*116,"\n")
# print(f"Multiple Questions Generated from Generator:\n\n{generated_questions}")

# # 사용할 검색기 활성화
# default_retriever = default_pipeline.default_db.as_retriever()
# # multiple_query_retriever 활성화
# testing_retriever = multiple_generator.multi_query_retriever(retriever=default_retriever)

# # 사용자 질문과 multi_query_retriever를 이용한 vector store 검색 및 결과값 리턴
# retrieved_results = testing_retriever.invoke({"user_question": results[10]})
# retrieved_results

# # build_multiple_question_rag_chain 함수를 이용한 최종 답변 생성
# multiple_question_RAG_chain = multiple_generator.build_multiple_question_rag_chain(retriever = retriever)
# final_answer = multiple_question_RAG_chain.invoke({"user_question": user_question})
# # multiple_question_RAG_chain
# final_answer

# # 다양한 고급 인덱싱 기법과 호완성 테스트
# # retriever = default_pipeline.default_db.as_retriever()
# # retriever = parent_pipeline.retriever
# # retriever = summary_pipeline_testing.retriever
# # retriever = hypothetical_pipe.retriever
# retriever = granular_exp_pipeline.retriever

# final_answer_2 = multiple_generator.generate_answer(user_question=results[10], retriever = retriever)
# final_answer_2