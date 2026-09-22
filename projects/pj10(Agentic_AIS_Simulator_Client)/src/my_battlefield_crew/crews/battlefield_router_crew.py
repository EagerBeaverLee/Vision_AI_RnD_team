from typing import List, Literal
from pydantic import BaseModel, Field
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task


################### TESTING STARTS (Trying various open source LLM models which could be utilized in a local environment)
import os
from crewai import LLM 
from dotenv import load_dotenv


import crewai.llms.cache as crewai_cache

crewai_cache.mark_cache_breakpoint = lambda msg: msg

load_dotenv()

# DeepInfra 설정 적용 모델
# tllm = LLM(
#     model="deepinfra/openai/gpt-oss-120b",  # deepinfra/조직명/모델명
#     base_url="https://api.deepinfra.com/v1/openai",       # DeepInfra OpenAI 호환 엔드포인트
#     api_key=os.getenv("DEEPINFRA_API_KEY"),              # DeepInfra API 키
#     max_retries=5,                                       # Rate Limit 대비 재시도 횟수 증대 추천
#     temperature=0
# )

#Fireworks 설정 적용 모델
# tllm = LLM(
#     model="fireworks_ai/accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
#     base_url="https://api.fireworks.ai/inference/v1",
#     api_key=os.getenv("FIREWORKS_API_KEY"),
#     max_retries=3,
#     temperature=0
# )

# tllm = LLM(
#     model="fireworks_ai/accounts/fireworks/models/muse-glimmer-30b",
#     base_url="https://api.fireworks.ai/inference/v1",
#     api_key=os.getenv("FIREWORKS_API_KEY"),
#     max_retries=3,
#     temperature=0
# )

# tllm = LLM(
#     model="fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
#     base_url="https://api.fireworks.ai/inference/v1",
#     api_key=os.getenv("FIREWORKS_API_KEY"),
#     max_retries=3,
#     temperature=0
# )

############################## TESTING ENDS



#이 기능은 battlefield_crew.py 내부에서 작동하며, 사용자의 질문을 의도에 맞게 라우팅하여 적합한 툴과 매칭시켜 주는 역할을 한다.

#-----------------------------------
# 1. routing을 위한 pydantic 모델 선언
#-----------------------------------

AnalysisCategory = Literal[
    '전체상황 요약',
    '밀집도 및 혼잡도',
    '구역별 속도',
    '주요 교통 흐름',
    '기동 상태별 현황',
    '주요 항만별 입출항',
    '특이 기동 선박 현황'
]

class QuestionRouterResult(BaseModel):
    needed_categories: List[AnalysisCategory] = Field(
        description = "사용자 질문에 완변히 답변하기 위해 반드시 분석해야 하는 기술 카테고리 목록(복수 선택가능)"
    )
    rationale: str = Field(description = "해당 분석 카테고리들을 선택한 전략적 의도 및 이유")

#-----------------------------------
# 2. @CrewBase RouterCrew 클래스 선언
#-----------------------------------
@CrewBase
class RouterCrew():

    """RouterCrew는 battlefield_crew.py 내부에서 작동하며, 
    사용자의 질문을 의도에 맞게 라우팅하여 적합한 툴과 매칭시켜 주는 역할을 함"""
    
    agents_config = 'config/battlefield_router_agents.yaml'
    tasks_config = 'config/battlefield_router_tasks.yaml'

    @agent
    def tactical_operations_router(self) -> Agent:
        return Agent(
            config=self.agents_config['tactical_operations_router'],
            # llm=tllm,
            verbose=True
        )
    @task
    def route_question_task(self) -> Task:
        return Task(
            config=self.tasks_config['route_question_task'],
            output_pydantic=QuestionRouterResult,
            agent=self.tactical_operations_router()
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )
