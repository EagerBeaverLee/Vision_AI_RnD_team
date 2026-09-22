### 최상위단에서 사용자의 질문을 BattlefieldCrew로 보낼지 아니면 MarineWeatherCrew로 보낼지 결정하는 ROUTER 기능 ###

from typing import Literal
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



#최상위단에서 사용자 질문에 가장 적합한 크루 줄 하나를 선택하도록 매핑

#---------------------------------------------
# 1.최상위단 라우터 1:1 맵핑을 위한 데이터 모델 정의 
#---------------------------------------------

TargetCrew = Literal[
    'BattlefieldCrew', #전장상황분석 (선박 위치, 항적, 정박, 기동상태, 전술보고)
    'MarineWeatherCrew', #해상 기상 분석(기온, 수온, 파고, 풍속, 관측 데이터)
    'RagCrew', # 교리 교범 관련 질문 응답(선박 운항 매뉴얼, 비상 대응 수칙, 해양 사고 사례, 비상단계 및 초치사항 등등)
    'unknown' #의도가 불명확한 경우; 이러한 경우 LLM이 Crew를 거치지 않고 직접 답변하도록 설계 되어야 함 
]

class MaterRouterResult(BaseModel):
    target_crew: TargetCrew = Field(
        description = "사용자 질문에 답변하기 위해 가동해야 하는 Crew 지정"
    )
    rationale: str = Field(description="해당 Crew를 선택한 판단 근거 및 이유")

#------------------------
# 2. MasterRouterCrew 정의
#------------------------
@CrewBase
class MasterRouterCrew:
    """최상단 전용 라우팅 CrewBase"""

    agents_config = 'config/master_router_agents.yaml'
    tasks_config = 'config/master_router_tasks.yaml'

    @agent
    def master_operations_router(self) -> Agent:
        return Agent(
            config=self.agents_config['master_operations_router'],
            # llm=tllm,
            verbose=True
        )

    @task
    def master_route_task(self) -> Task:
        return Task(
            config=self.tasks_config['master_route_task'],
            output_pydantic=MaterRouterResult,
            agent=self.master_operations_router()
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
    router_crew = MasterRouterCrew()

    user_query = "12월 9일 하루 동안 기온의 일교차(최고 기온 - 최저 기온)가 가장 컸던 지역은 어디인가요?"
    result = router_crew.crew().kickoff(
        inputs={"user_question": user_query}
    )

    routing_decision = result.pydantic.target_crew
    routing_reason = result.pydantic.rationale
    print(f"할당된 하위 크루 결과: {routing_decision}")
    print(f"하위 크루 할당 이유: {routing_reason}")


#BattlefieldCrew관련 질문

# "구역별 선박 밀집 현황에 대해서 알려줘!": ["밀집도 및 혼잡도"],
# "구역별 선박 정박 밀도에 대해서 알려줘!": ["밀집도 및 혼잡도"],
# "현재 혼잡구역 정보에 대해 알고 싶어!": ["밀집도 및 혼잡도"],
# "현재 우리 작전 해역 내에서 선박 밀도가 가장 높은 혼잡 구역은 어디인가요?": ["밀집도 및 혼잡도"],
# "현재 해상 교통망 내의 밀집 구역과 체류지수가 높은 해역 목록을 알려줘": ["밀집도 및 혼잡도"],
# "해역 내에서 선박들의 대기 시간이 길어지는 밀도가 증가하는 혼잡 구역이 어디인지 알려줘": ["밀집도 및 혼잡도"],
# "아군 군사 작전에 위협이 될 수 있는 체류 밀집도 상위 해역 목록을 보고해 주십시오": ["밀집도 및 혼잡도"],
# "해상 정박 밀도가 비정상적으로 조밀하게 형성된 집중 체류 구역 현황을 파악해줘": ["밀집도 및 혼잡도"],
# "해상 구역 내에서 해상 정박 대기 상태가 유독 집중되고 있는 정박 밀도 우려 구역이 어딘가요?": ["밀집도 및 혼잡도"],
# "밀집 현황과 정박 밀도를 기준으로 최근 감시 정찰 우선순위를 조정해야 할 혼잡 구역을 식별하십시오": ["밀집도 및 혼잡도"],
# "현재 주요 작전 해역 중에서 선박 체류 지수 점수가 가장 높게 잡히는 밀집 집중 구역 목록을 보고하십시오.": ["밀집도 및 혼잡도"],
# "정박 및 대기 상태의 선박들이 가장 많이 몰려 있는 해상 정박 밀도 밀집 해역을 추출해라": ["밀집도 및 혼잡도"],

#MarineWeatherCrew관련 질문

# Q1. 오늘 울릉도(지점 21229) 부이에서 관측된 기온은 몇 도인가요?
# Q2. 2022년 12월 8일 오전 10시 기준으로 마라도 해역의 풍속과 풍향을 알려주세요.
# Q3. 인천 앞바다의 현재 수온은 기온보다 높게 기록되어 있나요?
# Q4. 가거도 지점의 최근 유의파고와 평균파고는 각각 얼마인가요?
# Q5. 현재 시간 기준으로 포항 앞바다의 습도가 가장 낮았던 시각은 몇 시인가요?
# Q6. 12월 15일 오후 3시에 거문도 부이에서 관측된 GUST풍속은 얼마였나요?
# Q7. 현재시점 기준 동해57 부이의 기압 변화 추이를 알고 싶습니다. 기압이 계속 상승하고 있나요? 
# Q8. 현재 삼척 해역의 파주기(Wave Period)와 파향 상태를 알려주세요.
# Q9. 현재 시점 기준 부이 관측 데이터 중에서 수온이 21°C를 넘는 지점이 존재하나요? 
# Q10. 현재 시점 기준 울진 부이에서 측정된 최대파고가 가장 높았던 시각은 언제인가요?


#RagCrew관련 질문
# "출항 전 2항사가 일부 고속 고박(lashing) 장치가 마모되어 화물의 쏠림이 우려된다고 보고했습니다. 선사는 항만 일정을 이유로 출항을 독촉하고 있습니다. 이때 선장이 매뉴얼상 복원력 유지 대원칙을 근거로 선사와 조타실 요원들에게 내려야 할 즉각적인 의사결정은 무엇입니까?":["RagCrew"],
# "출항 시 복원성 계산서상의 KG(무게중심 높이) 수치는 안전 범위를 만족했습니다. 하지만 일등항해사가 장기 항해 도중 연료와 청수가 절반 이하로 소모되면 선박이 뒤집힐 위험이 있다고 우려합니다. 매뉴얼에서 경고하는 어떤 물리적 감축 현상 때문이며, 이를 방지하기 위한 대안은 무엇입니까?":["RagCrew"],
# "태풍 권역 인근을 항해할 예정인 화물선에서 갑판장에게 상갑판 배수구(Scupper) 주변 적재물을 정리하고 물길을 터놓으라고 긴급 지시하는 선장의 명령서입니다. 매뉴얼 상 상갑판 배수장치 상태가 복원성 소실과 어떻게 직접적으로 연관되는지 그 인과관계를 설명해 보세요.":["RagCrew"],
# "선박 복원성이 무너지는 임계점을 현장에서 신속히 구분하고자 합니다. 매뉴얼 상 선박이 좌우로 기울어져 결국 뒤집히는 '전복(Capsize)'의 물리적 경계 기준과, 해수 유입으로 가라앉는 '침몰(Sinking)'의 기하학적 판단 기준은 각각 무엇입니까?":["RagCrew"],
# "선령 23년인 화물선을 인수한 신임 선장입니다. 최근 거친 황천 항해 이후 외판 용접부 주변 미세한 부식이 관찰되었습니다. 선장으로서 매뉴얼상 선령 요건에 근거해 선사와 본선 안전관리를 위해 취해야 할 구체적인 행동은 무엇입니까?":["RagCrew"],
# "우리 배에 탑재된 '적하지침기기(Loading Computer)'와 '손상복원자료집(Damage Stability Booklet)'을 평상시 항해사들과 선장이 반드시 정기적으로 검토하고 숙지해야 하는 의무적 이유는 무엇입니까?":["RagCrew"],
# "거친 저기압 해역 통과를 앞두고 일등항해사가 선체 쏠림을 막고자 일부 평형수 탱크(Ballast Tank)를 절반만 채우는 방식으로 트림(Trim)을 조정하려 합니다. 매뉴얼 상 노후선이나 대형선에서 이러한 불충분한 평형수 주입이 황천에서 왜 치명적인 손상을 초래할 수 있는지 경고해 주세요.":["RagCrew"],
# "항해 중 원인을 즉각 파악하기 어려운 횡경사(Heeling)가 12도 발생하여 자동 복구되지 않고 서서히 기울기가 늘어나고 있습니다. 이 상황은 매뉴얼에 명시된 비상 등급 단계 중 어디에 해당하며, 선교에서 조타수와 기관원들에게 즉시 명령해야 할 구체적 행동은 무엇입니까?":["RagCrew"],
# "우현 격벽부에서 둔탁한 충격음이 들린 후 흘수가 깊어지는 느낌이 듭니다. 현재 높은 파도로 인해 대원들을 외부 현장에 보내 파공 유무를 육안 조사하는 것이 불가능한 야간 상황입니다. 이때 선장은 현장 점검 결과가 올 때까지 대기해야 합니까, 아니면 어떤 행동 강령을 우선 취해야 합니까?":["RagCrew"],
# "화물창 내 미세 침수가 확인되었으나 빌지 펌프 가동으로 수위가 통제되고 있으며, 추가 침수 확산 징후가 없고 선박 복원성에 큰 지장을 주지 않는 감항성이 입증되었습니다. 이 상황의 비상 단계 명칭과 이때 당직 사관들이 유지해야 할 핵심 안전 조치 2가지는 무엇입니까?":["RagCrew"],
# "선미 부근 다수 수밀 구역이 침수되어 흘수가 비정상적으로 빠르게 내려앉고 있습니다. 이미 건현이 물에 잠기기 시작했다면 선장이 고민하고 주저하지 말아야 할 치명적인 해양 사고 교훈과 즉각 실행해야 하는 조치는 무엇입니까?":["RagCrew"],
# "격벽 균열로 일부 구획에 침수가 발생했습니다. 기관장이 임시 수리를 시도하고 있으나 침수 차단 성공 여부를 보장할 수 없고 침수 속도가 다소 정체되어 있습니다. 이 상황에서 선장이 지정해야 할 매뉴얼상 비상 단계와 이에 따라 구명뗏목 부근 대원들이 완료해 두어야 할 준비 동작은 무엇입니까?":["RagCrew"],
# "침수가 개시되어 ERS 및 구조 당국에 긴급 조난 신호를 송신하려 하자, 일등항해사가 "나중에 자력 수습되면 섣부른 오판으로 회사로부터 과도한 오버 대응 비난을 받을 수 있다"며 만류합니다. 매뉴얼 상 선장은 이 항해사의 망설임에 대해 어떤 명확한 지침을 바탕으로 구조 요청을 단행해야 합니까?":["RagCrew"],
# "비상상황 시 선박 복원성을 실시간으로 직접 연산하기 힘든 긴박한 위기 속에서, 매뉴얼이 추천하는 외부 전문 검사 기관의 원격 복원성 지원 서비스 명칭과 이를 상황 판단에 연계하는 요령은 무엇입니까?":["RagCrew"],
# "화물창 1개가 파손되어 침수되기 시작한 단일선체 벌크선(Single-side Skin Bulk Carrier)의 선교입니다. 일반 컨테이너 화물선과 달리 벌크선은 왜 침수 초기부터 'BLACK단계(조기 퇴선)'를 극도로 빠르게 검토해야 합니까? 매뉴얼의 구조적 원인을 설명해 주세요.":["RagCrew"],
# "철광석과 철재를 가득 실은 벌크선의 선수 해치커버가 파손되어 침수가 개시되었습니다. 매뉴얼 상 철광석과 같은 중량화물(고비중 화물) 적재 선박이 침수 사고를 만났을 때 전형적으로 매우 취약한 이유 2가지는 무엇입니까?":["RagCrew"],
# "남해안을 항해 중인 광탄선 일등항해사가 "기상예보 상 비가 오지 않았고 화물 자체의 외관이 건조해 보여 액상화 우려는 전혀 없다"며 복원성 복도 순찰을 건너뛰려 합니다. 매뉴얼 상 IMSBC Code가 규정하는 A그룹 화물(철광석 등)의 수분액상화 위험성에 대한 정확한 사실 판단 기준을 설명해 주세요.":["RagCrew"],
# "겨울철 황천 속을 가로지르는 대형 벌크선에서 선수창탱크(FPT) 부근 침수 경보가 연속 발생했습니다. 매뉴얼 상 선수 방수 격벽(Collision Bulkhead) 손상으로 인한 앞 구역 침수가 궁극적으로 해치커버 탈락 및 선체 침몰로 이어지는 역학적 인과관계를 서술해 주세요.":["RagCrew"],