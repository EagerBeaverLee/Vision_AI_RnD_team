import os
from crewai import Agent, Task, Crew, Process
from crewai.project import CrewBase, agent, task, crew
from tools.maritime_density_async import analyze_maritime_density
from tools.maritime_speed_async import analyze_mean_speed
from tools.maritime_flow_async import analyze_traffic_flow
from tools.maritime_direction_async import get_direction_analysis
from tools.maritime_major_ports_status_async import get_major_ports_status
from tools.maritime_ships_voyage_status_async import ship_status_extraction
from tools.maritime_unusual_ships_detection_async import unusual_ships_detector
from crews.battlefield_models import MaritimeSituationReport
# from battlefield_models import MaritimeSituationReport
from typing import List


################### TESTING STARTS (Trying various open source LLM models which could be utilized in a local environment)
# import os
# from crewai import LLM 
# from dotenv import load_dotenv


# import crewai.llms.cache as crewai_cache

# crewai_cache.mark_cache_breakpoint = lambda msg: msg

# load_dotenv()

# DeepInfra 설정 적용 모델
# tllm = LLM(
#     model="deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",  # deepinfra/조직명/모델명
#     base_url="https://api.deepinfra.com/v1/openai",       # DeepInfra OpenAI 호환 엔드포인트
#     api_key=os.getenv("DEEPINFRA_API_KEY"),              # DeepInfra API 키
#     max_retries=5,                                       # Rate Limit 대비 재시도 횟수 증대 추천
#     temperature=0
# )

# Fireworks 설정 적용 모델
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



@CrewBase
class BattlefieldCrew:
    """해상 전장상황 분석을 위한 Crew 클래스"""

    agents_config = 'config/battlefield_agents.yaml'
    tasks_config = 'config/battlefield_tasks.yaml'

    def __init__(self, needed_categories: List[str] = None): #newly added 08/12/2026 for 병렬처리
        self.needed_categories = needed_categories or []
     
    @agent
    def maritime_situation_analyst(self) -> Agent:

        needed_categories = getattr(self, 'needed_categories', [])

        category_to_tools_map = {
            '밀집도 및 혼잡도': [analyze_maritime_density],
            '구역별 속도': [analyze_mean_speed],
            '주요 교통 흐름': [analyze_traffic_flow, get_direction_analysis],
            '기동 상태별 현황': [ship_status_extraction],
            '주요 항만별 입출항': [get_major_ports_status],
            '특이 기동 선박 현황': [unusual_ships_detector]
        }

        active_tools = []

        if '전체상황 요약' in self.needed_categories:
             active_tools = [
                analyze_maritime_density, 
                analyze_mean_speed,
                analyze_traffic_flow, 
                get_direction_analysis,
                ship_status_extraction, 
                get_major_ports_status,
                unusual_ships_detector
                ]
        else: 
            for category in self.needed_categories:
                if category in category_to_tools_map:
                    active_tools.extend(category_to_tools_map[category])


        print(f"[분석 도구 식별] 해상 분석관에게 배정된 활성 툴 목록: {[t.name for t in active_tools]}")

        return Agent(
            config=self.agents_config['maritime_situation_analyst'],
            tools=active_tools,
            # llm=tllm,
            verbose=True,
            # cache=False,
            max_iter=2
        ) 

    @task 
    def analyze_maritime_situation_task(self) -> Task:
        return Task(
            config=self.tasks_config['analyze_maritime_situation_task'],
            expected_output= "정량 지표들과 함께 사용자의 질문에 완벽히 응답하는 final_answer가 포함된 MaritimeSituationReport",
            output_pydantic=MaritimeSituationReport 
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
    
    print("====================================")
    print("🛡️ BattlefieldCrew 단독 컴포넌트 테스트 시작")
    print("====================================")
    
    crew_instance = BattlefieldCrew()

#     # 1. 테스트용 질문 입력
#     # test_inputs = {'user_question': '구역별 밀집 현황에 대해서 알려줘!'}
    test_inputs = {'user_question': '구역별 평균 속도 통계에 대해서 알려줘!'}
    
    print(f"사용자 요청: {test_inputs}")
    
    report = crew_instance.crew().kickoff(inputs=test_inputs)
    report = report.pydantic

    print("\n\n [통합 크루 가동 완료] 최종 결과 출력")
    print("--------------------------------------------------")
    print(f"종합개요:\n{report.overview}")

    if report.zone_speeds:
        print("[구역별 속도 통계 데이터]")
        for zone in report.zone_speeds:
            print(f"해역: {zone.name} | 평균 속도: {zone.mean:.2f} kts | 최고 속도: {zone.max:.2f} kts (샘플 수: {zone.count})")

    if report.top_dense_zones:
        print("[구역별 밀집도 데이터]")
        for zone in report.top_dense_zones:
            print(f"해역: {zone.name} | 체류지수: {zone.total_stay_index}")
