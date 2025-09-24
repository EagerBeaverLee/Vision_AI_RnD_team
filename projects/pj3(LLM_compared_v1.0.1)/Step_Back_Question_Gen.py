#############################
### 3) Step-Back Question ###
#############################
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel, RunnableLambda
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

class StepBackQuestionGenerator:
    def __init__(self,llm):
        
        self.llm = llm
        
        #Prompt Template 
        self.stepback_prompt_template = """
        Generate a less specific question (aka Step-back question) for the following user question,
        so that a wider context can be retrieved. 
        User question: {question}
    
        Step-back question:
        Just return Step-back question itself."""
        
        self.rag_prompt_template = """
        {user_input}
        You are a helpful assistant. Use the following context to answer the question. 
        Original retrieved docs: {original_docs}
        Step-back retrieved docs: {step_back_docs}
        Question: {question}
        Answer:
        """

        self.init_prompts()
        self.init_chains()

    def init_prompts(self):
        self.step_prompt = ChatPromptTemplate.from_template(self.stepback_prompt_template)
        self.rag_prompt = ChatPromptTemplate.from_template(self.rag_prompt_template)

    def init_chains(self):
        self.stepback_chain = self.step_prompt | self.llm | StrOutputParser()

    def build_rag_chain(self, prompt, retriever = None, k=2):
        try:
            if not retriever:
                raise ValueError("Retriever is required to build RAG chain.")
            
            step_back_question_rag_chain = (
                RunnablePassthrough.assign(
                    step_back_question = self.stepback_chain
                )
                |RunnableParallel(
                    question = RunnableLambda(lambda x: x["question"]),
                    original_docs = RunnableLambda(lambda x: retriever.invoke(x["question"])[:k]),
                    step_back_docs = RunnableLambda(lambda x: retriever.invoke(x["step_back_question"])[:k]),
                )
                | self.rag_prompt
                | self.llm
            )
                
            return step_back_question_rag_chain

        except Exception as e:
            print(f"Error while building step_back_question RAG chain: {e}")
            return None

    def generate_answer(self, user_question: str, retriever=None, k=2):
        try:
            if not retriever:
                raise ValueError("Retriever is required to execute RAG chain")
            
            rag_chain = self.build_stepback_rag_chain(retriever, k=k)
            result = rag_chain.invoke({"user_question": user_question})
            
            return result
        except Exception as e:
            print(f"Error while trying to answer user_question: {e}")


###사용예제
# stepback_question_generator = StepBackQuestionGenerator()

# user_question = results[14]
# stepback_question = stepback_question_generator.stepback_chain.invoke({"user_question": user_question})
# print(f"ORIGINAL_QUESTION: {user_question}\n")
# print("="*117, "\n\n")
# print(f"STEPBACK QUESTION GENERATED: {stepback_question}")

# # 다양한 고급 인덱싱 기법과 stepback_rag_chain 호완성 TESTING

# # retriever = default_pipeline.default_db.as_retriever()
# # retriever = parent_pipeline.retriever
# retriever = summary_pipeline_testing.retriever
# # retriever = hypothetical_pipe.retriever
# # retriever = granular_exp_pipeline.retriever

# user_question = results[14]

# stepback_rag_chain = stepback_question_generator.build_stepback_rag_chain(retriever=retriever, k=2)
# final_answer = stepback_rag_chain.invoke({"user_question": user_question})
# final_answer

# # 다양한 고급 인덱싱 기법과 generate_answer 함수 호완성 TESTING

# # retriever = default_pipeline.default_db.as_retriever()
# # retriever = parent_pipeline.retriever
# # retriever = summary_pipeline_testing.retriever
# # retriever = hypothetical_pipe.retriever
# retriever = granular_exp_pipeline.retriever

# user_question = results[9]

# final_answer = stepback_question_generator.generate_answer(user_question, retriever)
# final_answer