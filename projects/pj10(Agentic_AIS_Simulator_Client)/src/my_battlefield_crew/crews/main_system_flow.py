import asyncio
from pydantic import BaseModel
from crewai.flow.flow import Flow, listen, router, start

from crews.master_router_crew import MasterRouterCrew
from crews.marine_weather_flow import MarineWeatherFlow
from crews.battlefield_crew import BattlefieldCrew
from crews.battlefield_router_crew import RouterCrew
from crews.rag_crew import RAGCrew

# from master_router_crew import MasterRouterCrew
# from marine_weather_flow import MarineWeatherFlow
# from battlefield_crew import BattlefieldCrew
# from battlefield_router_crew import RouterCrew
# from rag_crew import RAGCrew


class MainSystemState(BaseModel):
    user_query: str = ""
    target_crew: str = ""
    final_answer: str = ""


class MainSystemFlow(Flow[MainSystemState]):

    @start()
    def route_at_entry(self):
        print(f"\n🧭 [초입 라우팅] 질문 분석 중: '{self.state.user_query}'")

        # 1. 최상단 라우터 실행
        router_crew = MasterRouterCrew()
        result = router_crew.crew().kickoff(
            inputs={"user_question": self.state.user_query}
        )

        # Pydantic 결과 저장
        self.state.target_crew = result.pydantic.target_crew
        print(f"[할당된 하위 크루]: {self.state.target_crew}")
        print(f"[판단 이유]: {result.pydantic.rationale}")

    @router(route_at_entry)
    def dispatch(self):
        if self.state.target_crew == "MarineWeatherCrew":
            return "weather_path"
        elif self.state.target_crew == "BattlefieldCrew":
            return "battlefield_path"
        elif self.state.target_crew == "RagCrew":
            return "rag_path"
        else: 
            return "unknown"

    @listen("weather_path")
    def run_weather(self):
        print("Weather Path 실행 시작")
        weather_flow = MarineWeatherFlow()
        weather_flow.state.user_query = self.state.user_query
        return weather_flow.kickoff()

    @listen("battlefield_path")
    async def run_battlefield(self):
        print("Battlefield Path 실행 시작")
        #Battlefield Router Crew 실행
        router_crew = RouterCrew()
        router_output = await router_crew.crew().kickoff_async(
                inputs={"user_question": self.state.user_query}
            )
        actual_categories = router_output.pydantic.needed_categories

        #Router Crew셜과를 바탕으로 Battlefield Crew 실행
        bf_crew = BattlefieldCrew(needed_categories=actual_categories)
        result = await bf_crew.crew().kickoff_async(inputs={"user_question": self.state.user_query})
        return result.raw 

    @listen("rag_path")
    async def run_rag(self):
        print("Rag Path 실행 시작")
        rag_crew = RAGCrew()
        result = await rag_crew.crew().kickoff_async(
            inputs={"user_question": self.state.user_query}
            )
        return result.raw
    
    @listen("unknown") #this is temporary function for now
    def handle_unknown(self):
        print("⚠️ 알 수 없는 의도 처리")
        return "요청하신 질문은 해상 날씨 또는 전장상황 분석 범위에 포함되지 않습니다."


if __name__ == "__main__": 
    async def run_single_query(user_query: str):
        main_flow = MainSystemFlow()
        main_flow.state.user_query = user_query

        final_result = await main_flow.kickoff_async()
        return final_result


    async def run_test_cases(test_cases: list[str]):
        results={}

        print(f"총 {len(test_cases)}개의 테스트 케이스 실행을 시작합니다. \n")

        for idx, user_query in enumerate(test_cases, 1):
            print(f"[{idx}/{len(test_cases)}] 테스트 실행 중: '{user_query}'")
            try:
                result = await run_single_query(user_query) 
                results[user_query] =  result
                print(f"[Final Answer]\n{result}\n")
            except Exception as e:
                print(f"[ERROR] 테스트 실패 ('{user_query}'): {e}\n")
                results[user_query] = f"Error: {e}"

        print("=" * 40)
        print("모든 프로세스 및 테스트케이스 종료")
        print("=" * 40)

        return results

    test_cases = [
        #BattleCrew 관련 질문
      
        # "선박들의 이동 방향 데이터와 함께 트래픽 가중치 분포가 편중되어 있는 주요 항로 구간을 식별해 주십시오.",
        # "구역별 주 이동 침로 방향과 주요 항로 흐름 세부 현황을 알려줘.",
        #  "현재시점 기준 동해57 부이의 기압 변화 추이를 알고 싶습니다. 기압이 계속 상승하고 있나요?", 
        #  "현재 삼척 해역의 파주기(Wave Period)와 파향 상태를 알려주세요.",
        #  "현재 시점 기준 부이 관측 데이터 중에서 수온이 21°C를 넘는 지점이 존재하나요?", 
        #  "현재 시점 기준 울진 부이에서 측정된 최대파고가 가장 높았던 시각은 언제인가요?",

        #MarineWeather 관련 질문
        # "오늘 울릉도(지점 21229) 부이에서 관측된 기온은 몇 도인가요?",
        # "2022년 12월 8일 오전 10시 기준으로 마라도 해역의 풍속과 풍향을 알려주세요.",
        # "인천 앞바다의 현재 수온은 기온보다 높게 기록되어 있나요?",

        #RagCrew 관련 질문
        "출항 전 2항사가 일부 고속 고박(lashing) 장치가 마모되어 화물의 쏠림이 우려된다고 보고했습니다. 선사는 항만 일정을 이유로 출항을 독촉하고 있습니다. 이때 선장이 매뉴얼상 복원력 유지 대원칙을 근거로 선사와 조타실 요원들에게 내려야 할 즉각적인 의사결정은 무엇입니까?",
        "출항 시 복원성 계산서상의 KG(무게중심 높이) 수치는 안전 범위를 만족했습니다. 하지만 일등항해사가 장기 항해 도중 연료와 청수가 절반 이하로 소모되면 선박이 뒤집힐 위험이 있다고 우려합니다. 매뉴얼에서 경고하는 어떤 물리적 감축 현상 때문이며, 이를 방지하기 위한 대안은 무엇입니까?",
        "태풍 권역 인근을 항해할 예정인 화물선에서 갑판장에게 상갑판 배수구(Scupper) 주변 적재물을 정리하고 물길을 터놓으라고 긴급 지시하는 선장의 명령서입니다. 매뉴얼 상 상갑판 배수장치 상태가 복원성 소실과 어떻게 직접적으로 연관되는지 그 인과관계를 설명해 보세요.",
        # "선박 복원성이 무너지는 임계점을 현장에서 신속히 구분하고자 합니다. 매뉴얼 상 선박이 좌우로 기울어져 결국 뒤집히는 '전복(Capsize)'의 물리적 경계 기준과, 해수 유입으로 가라앉는 '침몰(Sinking)'의 기하학적 판단 기준은 각각 무엇입니까?",
        # "선령 23년인 화물선을 인수한 신임 선장입니다. 최근 거친 황천 항해 이후 외판 용접부 주변 미세한 부식이 관찰되었습니다. 선장으로서 매뉴얼상 선령 요건에 근거해 선사와 본선 안전관리를 위해 취해야 할 구체적인 행동은 무엇입니까?",
        # "우리 배에 탑재된 '적하지침기기(Loading Computer)'와 '손상복원자료집(Damage Stability Booklet)'을 평상시 항해사들과 선장이 반드시 정기적으로 검토하고 숙지해야 하는 의무적 이유는 무엇입니까?"
    ]

    asyncio.run(run_test_cases(test_cases))

    

# 1. 특정 지점 및 시간대별 기상/해상 상태 조회 (단순 조회 패턴)
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

# 2. 여러 해역 간 기상 및 해상 조건 비교 (비교 패턴)
# Q11. 현재 시점 기준 울릉도 해역과 동해 해역 중 어느 곳의 수온이 더 높나요?
# Q12. 인천 앞바다와 울산 앞바다의 유의파고를 비교했을 때 어디의 파도가 더 높나요?
# Q13. 남해의 거제도와 서해의 덕적도 중 어느 해역의 풍속(바람)이 더 강하게 부나요?
# Q14. 마라도와 추자도 부이의 기온 편차는 얼마나 발생하고 있나요?
# Q15. 동해 부이와 서해170 부이의 기압 값을 비교해서 고기압 영향권에 더 가까운 곳을 알려주세요.
# Q16. 강릉 부이와 삼척 부이의 수온 추세가 어떻게 움직이고 있나요?
# Q17. 칠발도와 거문도, 동해57 중 평균파고를 기준으로 어느 바다가 더 잔잔한가요?

# 3. 극값 및 기상 위험 단계 탐지 (통계 및 임계값 패턴)
# Q19. "현재 시간 기준 전체 부이 관측소 중에서 오늘 가장 강한 Gust풍속이 기록된 곳은 어디인가요?"
# Q20. 현재 시간 기준 데이터 중 수온이 가장 낮게 기록된 부이의 이름과 수온을 알려주세요.
# Q21. 12월 9일 하루 동안 **기온의 일교차(최고 기온 - 최저 기온)**가 가장 컸던 지역은 어디인가요?
# Q22. 현재 시간 기준 유의파고가 3m를 초과하여 소형 선박 운항이 위험할 것으로 예상되는 부이 목록을 뽑아주세요.
# Q23. 오늘 현지기압이 1025 hPa 이상으로 가장 높게 측정된 지점은 어디인가요?
# Q24. 현재 시점 기준 풍향이 북풍 계열(315도~45도 사이)로 불고 있는 지점은 어디인가요?
# Q25. 12월 10일 기준 기온과 수온의 차이(기온 - 수온)가 가장 크게 벌어진 지점과 시간은 언제인가요?
# Q26. 12월 3일 기준 유의파고 대비 최대파고의 비율이 가장 높게 나타난 변칙적인 해역이 있나요?

# 4. 관리관서 및 위치 메타데이터 결합 (공간 결합 패턴)
# Q27. "**'부산지방기상청'**에서 관리하는 부이 중 유의파고가 가장 높은 지점명 3개를 알려줘?"
# Q28."현재 시간 기준 '강릉' 관리관서 소속 부이들의 실시간 기온 현황을 알려줘"
# Q29. 12월 4일 기준 위도 37도 이상의 북쪽 해역에 위치한 부이들의 수온 분포를 알려주세요.
# Q30. **'목포기상대'**가 관리하는 관할 해역 부이들 중 풍속이 가장 센 곳은 어디인가요?
# Q31. 제주지방기상청 소속 부이들의 위경도 좌표와 해당 지점들의 현재 시간 평균파고를 같이 보여주세요.
# Q32. 관측을 개시한 지 가장 오래된(시작일이 가장 빠른) 역사적인 부이 지점은 어디이고, 현재 날씨는 어떤가요?

# 5. 실생활 조업 및 해상 안전 시나리오 (맥락적 패턴)
# Q33. 지금 소매물도 부근으로 낚시를 가려고 하는데, 바람과 파고가 안전한 수준인가요?
# Q34. 오늘 가거도 근해에서 어업 조업을 하기에 파주기와 파향이 적절한 상태인가요?
# Q35. 최근 3~6시간 동안 지점(spot_id)별로 기압 변화량과 풍속 변화량을 산출해줘. 그리고 변화량 기준으로 관심을 가져야 할 지점들을 요약해서 알려줘.
# Q36. 이수도와 지심도 인근 거제 양식장의 수온이 물고기들이 활동하기에 적절한 온도를 유지하고 있나요?
# Q37. 인천, 풍도, 연평도 등 서해 중부 해역의 습도 상태를 볼 때 해무(바다 안개)가 발생할 가능성이 높나요?
# Q38. 바람 방향(풍향)과 파도의 방향(파향)이 거의 일치하여 파도가 거세질 위험이 있는 지점은 어디인가요?
# Q39. 태풍이나 풍랑에 대비하기 위해 **동해 해안선과 가장 멀리 떨어진 먼바다 부이(외해 부이)**의 기압 상태를 확인해 주세요.
# Q40. 수온이 급격히 변화하는 조경수역(물덩어리가 만나는 곳)을 예측하기 위해 인접한 부이 중 수온 차가 가장 심한 구역을 알려주세요.




#BattlefieldCrew 관련 질문
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

# RagCrew 관련 질문
# "출항 전 2항사가 일부 고속 고박(lashing) 장치가 마모되어 화물의 쏠림이 우려된다고 보고했습니다. 선사는 항만 일정을 이유로 출항을 독촉하고 있습니다. 이때 선장이 매뉴얼상 복원력 유지 대원칙을 근거로 선사와 조타실 요원들에게 내려야 할 즉각적인 의사결정은 무엇입니까?":["RagCrew"],
# "출항 시 복원성 계산서상의 KG(무게중심 높이) 수치는 안전 범위를 만족했습니다. 하지만 일등항해사가 장기 항해 도중 연료와 청수가 절반 이하로 소모되면 선박이 뒤집힐 위험이 있다고 우려합니다. 매뉴얼에서 경고하는 어떤 물리적 감축 현상 때문이며, 이를 방지하기 위한 대안은 무엇입니까?":["RagCrew"],
# "태풍 권역 인근을 항해할 예정인 화물선에서 갑판장에게 상갑판 배수구(Scupper) 주변 적재물을 정리하고 물길을 터놓으라고 긴급 지시하는 선장의 명령서입니다. 매뉴얼 상 상갑판 배수장치 상태가 복원성 소실과 어떻게 직접적으로 연관되는지 그 인과관계를 설명해 보세요.":["RagCrew"],
# "선박 복원성이 무너지는 임계점을 현장에서 신속히 구분하고자 합니다. 매뉴얼 상 선박이 좌우로 기울어져 결국 뒤집히는 '전복(Capsize)'의 물리적 경계 기준과, 해수 유입으로 가라앉는 '침몰(Sinking)'의 기하학적 판단 기준은 각각 무엇입니까?":["RagCrew"],
# "선령 23년인 화물선을 인수한 신임 선장입니다. 최근 거친 황천 항해 이후 외판 용접부 주변 미세한 부식이 관찰되었습니다. 선장으로서 매뉴얼상 선령 요건에 근거해 선사와 본선 안전관리를 위해 취해야 할 구체적인 행동은 무엇입니까?":["RagCrew"],
# "우리 배에 탑재된 '적하지침기기(Loading Computer)'와 '손상복원자료집(Damage Stability Booklet)'을 평상시 항해사들과 선장이 반드시 정기적으로 검토하고 숙지해야 하는 의무적 이유는 무엇입니까?":["RagCrew"],
# "거친 저기압 해역 통과를 앞두고 일등항해사가 선체 쏠림을 막고자 일부 평형수 탱크(Ballast Tank)를 절반만 채우는 방식으로 트림(Trim)을 조정하려 합니다. 매뉴얼 상 노후선이나 대형선에서 이러한 불충분한 평형수 주입이 황천에서 왜 치명적인 손상을 초래할 수 있는지 경고해 주세요.":["RagCrew"],
# "항해 중 원인을 즉각 파악하기 어려운 횡경사(Heeling)가 12도 발생하여 자동 복구되지 않고 서서히 기울기가 늘어나고 있습니다. 이 상황은 매뉴얼에 명시된 비상 등급 단계 중 어디에 해당하며, 선교에서 조타수와 기관원들에게 즉시 명령해야 할 구체적 행동은 무엇입니까?":["RagCrew"],
# "우현 격벽부에서 둔탁한 충격음이 들린 후 흘수가 깊어지는 느낌이 듭니다. 현재 높은 파도로 인해 대원들을 외부 현장에 보내 파공 유무를 육안 조사하는 것이 불가능한 야간 상황입니다. 이때 선장은 현장 점검 결과가 올 때까지 대기해야 합니까, 아니면 어떤 행동 강령을 우선 취해야 합니까?":["RagCrew"],
