# import os
from crewai import Agent, Task, Crew, Process
from tools.doc_search_tool import search_document_tool
from crewai.project import CrewBase, agent, task, crew


################### TESTING STARTS (Trying various open source LLM models which could be utilized in a local environment)
import os
from crewai import LLM 
from dotenv import load_dotenv

import crewai.llms.cache as crewai_cache

crewai_cache.mark_cache_breakpoint = lambda msg: msg

load_dotenv()


tllm = LLM(
    model="fireworks_ai/accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    # model="fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    # model="fireworks_ai/accounts/fireworks/models/muse-glimmer-30b",
    # model="fireworks_ai/accounts/fireworks/models/deepseek-v4p1-flash",
    base_url="https://api.fireworks.ai/inference/v1",
    api_key=os.getenv("FIREWORKS_API_KEY"),
    max_retries=3,
    temperature=0
)
############################## TESTING ENDS

@CrewBase
class RAGCrew:
    """해상 안전 매뉴얼 및 교리교범을 검색하여 사용자의 의도에 맞는 답변을 생성하는 Crew 클래스"""

    agents_config = 'config/rag_agents.yaml'
    tasks_config = 'config/rag_tasks.yaml'  

    @agent
    def document_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['document_researcher'],
            tools=[search_document_tool],
            # llm=tllm, #this is for testing open source models; if wanting to use open AI models, deactivate this line!
            verbose=True
            )
    
    @task
    def document_researching_task(self) -> Task:
        return Task(
            config=self.tasks_config['document_researching_task'],
            agent=self.document_researcher()
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )

if __name__ == "__main__":
    question = "출항 전 2항사가 일부 고속 고박(lashing) 장치가 마모되어 화물의 쏠림이 우려된다고 보고했습니다. 선사는 항만 일정을 이유로 출항을 독촉하고 있습니다. 이때 선장이 매뉴얼상 복원력 유지 대원칙을 근거로 선사와 조타실 요원들에게 내려야 할 즉각적인 의사결정은 무엇입니까?"


    result = RAGCrew().crew().kickoff(inputs={"user_question": question})
    
    print("\n===================== [최종 결과] ======================")
    print(result)