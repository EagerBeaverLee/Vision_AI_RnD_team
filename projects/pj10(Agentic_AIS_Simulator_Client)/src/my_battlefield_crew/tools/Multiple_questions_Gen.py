import os
from typing import List
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import BaseOutputParser, StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_classic.retrievers import MultiQueryRetriever
from langchain_openai import ChatOpenAI


#together api model testing purpose
# from langchain_together import ChatTogether 


import logging
logging.basicConfig()
logging.getLogger("langchain_classic.retrievers").setLevel(logging.INFO)

class LineListOutputParser(BaseOutputParser[List[str]]):
    """LLM 출력에서 각 줄별 질문을 파싱하여 리스트로 반환"""
    def parse(self, text:str) -> List[str]:
        lines = text.strip().split("\n")
        return [line.strip() for line in lines if line.strip()]


api_key = os.getenv("OPENAI_API_KEY")
model_name = os.getenv("MODEL")

if model_name.startswith("openai/"):
    model_name = model_name.replace("openai/", "")

vllm = ChatOpenAI(
    model=model_name, 
    api_key=api_key,
)


#Together AI API 모델 TEST
# vllm = ChatTogether(
#     model="openai/gpt-oss-120b",  # Together AI 전용 모델 ID (접두사 없음)
#     together_api_key=os.getenv("TOGETHER_API_KEY"),    # 발급받은 Together API Key 문자열 직접 입력
#     temperature=0
# )
#==========================================================================

class MultipleQuestionGenerator:
    def __init__(self, llm=vllm):
        self.llm = llm

        self.multi_query_gen_prompt_template ="""
            당신은 정보 검색(Information Retrieval) 시스템을 위한 쿼리 재작성 전문가입니다.
            사용자의 원본 질문을 바탕으로 '벡터 의미 검색(Dense)'과 '키워드 매칭 검색(Sparse/BM25)' 기반 하이브리드 검색에서 최상의 결과를 얻을 수 있도록 
            5개의 다각화된 검색 쿼리를 생성해 주세요.

            다음 규칙을 준수하여 쿼리를 다양화하세요:
            1. 문장 구조 변형 (Dense 최적화): 원본의 의미를 유지하되, 서술형·상황 설명형·목적 중심형 등 문장 표현을 다채롭게 구성하세요.
            2. 어휘 및 전문 용어 확장 (Sparse/BM25 최적화): 동의어, 유의어, 관련 표준 어휘 및 상위/하위 개념 단어로 대체하세요.
            3. 명사 키워드 조합 포함: 5개 중 1개 이상은 조사나 어미를 최소화하고 문서 표제어 형태의 핵심 '명사 키워드 조합'으로 작성하세요.
            4. 출력 형식: 대안 질문들은 줄바꿈으로 구분하여 제공해 주세요.
         
            원본 질문: {question} 
            """

        self.rag_prompt_template ="""
            검색된 컨텍스트(context)를 활용하여, 사용자의 질문에 답하세요.
            만약 답변을 모르겠으면, "잘 모르겠습니다"라고 답변하세요 
                    
            Context: {context}
            Question: {question} 
            """
        self.questions_parser = LineListOutputParser()
        self.init_prompts()
        self.init_chains()

    def init_prompts(self):
        self.multiple_question_prompt =ChatPromptTemplate.from_template(self.multi_query_gen_prompt_template)
        self.rag_prompt = ChatPromptTemplate.from_template(self.rag_prompt_template)

    def init_chains(self):
        self.multi_query_gen_chain = self.multiple_question_prompt | self.llm | self.questions_parser

    def get_multi_query_retriever(self, base_retriever):
        """기본 retriever를 전잘받아 MultiQueryRetriever로 확장하여 반환"""
        if not base_retriever:
            raise ValueError("Retriever가 필요합니다")

        multi_query_retriever = MultiQueryRetriever(
            retriever=base_retriever,
            llm_chain=self.multi_query_gen_chain,
            parser_key="lines"
        )
        return multi_query_retriever

    def build_rag_chain(self, base_retriever):
        """MultiQueryRetriever와 연결된 RAG 체인 구축"""
        if not base_retriever:
            raise ValueError("Retriever가 필요합니다")

        multi_retriever = self.get_multi_query_retriever(base_retriever)

        def format_docs(docs): #문서를 하나로 합쳐주는 도우미 함수
            return "\n\n".join(doc.page_content for doc in docs)

        rag_chain = (
            {
                "context": multi_retriever | format_docs,
                "question": RunnablePassthrough()
            }
            | self.rag_prompt
            | self.llm
            | StrOutputParser()
        )
        return rag_chain

    def generate_answer(self, user_question: str, base_retriever=None) -> str:
        """사용자의 질문을 입력받아 답변 생성 실행"""
        try:
            if not base_retriever:
                raise ValueError("Retriever가 필요합니다.")

            rag_chain = self.build_rag_chain(base_retriever)
            result = rag_chain.invoke(user_question)
            return result
        except Exception as e:
            print(f"답변 생성 중 오류 발생: {e}")
            return "" 
        
#testing 

# if __name__ == "__main__":

#     from tools.parent_keyword_retriever import ParentKeywordRetrieverPipeline

#     retriever_pipeline = ParentKeywordRetrieverPipeline() 
#     retriever_pipeline.load_folder()

#     #FAISS vectorstore에서 기본 retriever가져오기
#     base_retriever = retriever_pipeline.retriever()

#     generator = MultipleQuestionGenerator()

#     question = "고속단정 황천 항해"

#     answer = generator.generate_answer(user_question=question, base_retriever=base_retriever) 

#     print("\n====================== [ Multi_Query RAG 답변] ==========================")
#     print(answer)
