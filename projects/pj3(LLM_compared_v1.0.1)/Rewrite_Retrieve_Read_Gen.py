#############################
### Rewrite-Retrieve-Read ###
#############################

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
# from langchain_together.chat_models import ChatTogether
import os
from dotenv import load_dotenv

#vllm정의
# load_dotenv() # Load environment variables from a .env file if present
# api_key = os.getenv("TOGETHER_API_KEY") #api_key는 .env파일에 저장 함

# if not api_key:
#     #환경 변수가 없을 경우 예외 처리
#     print("TOGETHER_API_KEY가 환경 변수로 설정되지 않았습니다.")

# else: 
#     print("API KEY가 성공적으로 로드되었습니다")

# vllm = ChatTogether(model="openai/gpt-oss-20b", max_tokens=6000) #Together AI API사용 중...Local Vllm으로 대체되어야 함. 

#retriever는 class 밖에서 정의되어야 함; 
#그리고 클래스 내 build_rewrite_rag_chain & generate_answer 사용하려면, retriever를 입력 인자로 추가해야 함

class RewriteRetrieveReadQuestionGenerator:
    def __init__(self, llm):
        
        self.llm = llm
        
        #Prompt Template 
        self.rewriter_prompt_template = """
        Generate search query for the FAISS DB vector store from a user question, allowing for a more
        accurate response through semantic search. 
        Just return the revised FAISS DB query, with quotes around it. 
        User question: {question}
        Revised FAISS DB query:
        """
        self.rag_prompt_template = """
        Given a question and some context, answer the question.
        If you do not know the answer, just say I do not know. 
        Context: {context}
        Question: {question}"""

        self.init_prompts()
        self.init_chains()

    def init_prompts(self):
        self.rewriter_prompt = ChatPromptTemplate.from_template(self.rewriter_prompt_template)
        self.rag_prompt = ChatPromptTemplate.from_template(self.rag_prompt_template)

    def init_chains(self):
        self.rewriter_chain = self.rewriter_prompt | self.llm | StrOutputParser()

    def generate_query(self, question):
        res = self.rewriter_chain.invoke(question)
        return res

    def build_rag_chain(self, prompt, retriever = None):
        try:
            if not retriever:
                raise ValueError("Retriever is required to build RAG chain.")
            
            rewrite_retrieve_read_rag_chain = (
                {
                    "context": {"question": RunnablePassthrough()} | self.rewriter_chain | retriever,
                    "question": RunnablePassthrough(),
                }
                | prompt
                # | self.rag_prompt
                | self.llm
                )
            return rewrite_retrieve_read_rag_chain

        except Exception as e:
            print(f"Error while building rewrite-retrieve-read RAG chain: {e}")
            return None

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