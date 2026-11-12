######################################
### 2) Generating multiple queries ###
######################################
# from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_core.prompts import ChatPromptTemplate
from typing import List
from langchain_core.output_parsers import BaseOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from my_battlefield_crew.RAG.DocumentPostProcessor import DocumentPostProcessor
from my_battlefield_crew.RAG.Reciprocal_Rank_Fusion_Post_Processing import ReciprocalRankFusionClass
from my_battlefield_crew.chainlit_app.schemas import SimulationContext

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

        self.prompt = PromptTemplate.from_template(
            """당신은 AI 검색 어시스턴트입니다. 사용자의 질문을 다양한 관점에서 문서를 검색할 수 있도록 
3개의 서로 다른 검색 쿼리로 재작성하거나 세분화해 주세요.
각 질문은 반드시 줄바꿈으로만 구분하여 출력하고, 번호나 따옴표, 부연 설명은 붙이지 마세요.

원래 질문: {question}"""
        )
        self.query_chain = self.prompt | self.llm | StrOutputParser()
        
        #Prompt Template 
        self.multi_query_gen_prompt_template = """
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

    def generate_queries(self, question: str) -> list[str]:
        """원래 질문 + 다각화된 3개 질문 생성 (총 4개 쿼리)"""
        try:
            res = self.query_chain.invoke({"question": question})
            generated = [line.strip("- 1234567890.").strip() for line in res.split("\n") if line.strip()]
            # 원본 질문을 맨 앞에 포함하고 중복 제거
            all_queries = [question] + generated
            return list(dict.fromkeys(all_queries))
        except Exception as e:
            print(f"[MultipleQuestionGenerator] 질문 분할 실패 (원문 사용): {e}")
            return [question]

    def search_docs(self, context: SimulationContext):
        try:
            print("Multiple_Question_Generator")
            retriever = context.rag_pipe.retriever
            if not context.rag_pipe or not context.rag_pipe.retriever:
                raise ValueError("Retriever가 준비되지 않았습니다.")
            
            if context.rag_pipe.rag_config.post_processing.use_rrf:
                print("RRF is worked")
                docs = ReciprocalRankFusionClass(self.llm, self.multi_query_gen_chain).rrf_docs(retriever)
                print(docs)
                print("#"*55)
                return docs
            else:
                # 후처리 파라미터 추출
                post_cfg = context.rag_pipe.rag_config.post_processing
                threshold = post_cfg.similarity_threshold if post_cfg.use_similarity and post_cfg.similarity_threshold > 0 else None
                
                # 문자열 키워드를 set 형태로 변환하여 전달
                keywords = None
                if post_cfg.use_keywords and post_cfg.keywords:
                    keywords = {k.strip() for k in post_cfg.keywords.split(",") if k.strip()}

                # 1. 다중 질문 생성
                queries = self.generate_queries(context.user_question)
                print(f"[MultipleQuestionGenerator] 생성된 쿼리 목록 ({len(queries)}개): {queries}")

                # 2. 각 질문마다 post_processor 실행 (Threshold & Keyword 필터링 일괄 처리)
                all_docs = []
                seen_contents = set()

                for q in queries:
                    docs = context.rag_pipe.post_processor.post_processor(
                        user_question=q,
                        score_threshold=threshold,
                        required_keywords=keywords
                    )
                    
                    # 3. 문서 병합 및 내용(page_content) 기준 중복 제거
                    if docs:
                        for doc in docs:
                            if doc.page_content not in seen_contents:
                                seen_contents.add(doc.page_content)
                                all_docs.append(doc)

                print(f"[MultipleQuestionGenerator] 최종 통합 문서 수: {len(all_docs)}개")
                return all_docs

        except Exception as e:
            print(f"[MultipleQuestionGenerator] Error while building Multiple Questions RAG: {e}")
            return None


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