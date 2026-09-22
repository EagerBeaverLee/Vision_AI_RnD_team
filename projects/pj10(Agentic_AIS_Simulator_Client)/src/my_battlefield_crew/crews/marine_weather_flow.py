from crewai import Crew, Process
from crewai.flow.flow import Flow, listen, router, start
from marine_weather_models import SqlFlowState
from marine_weather_crew import MarineWeatherCrew

class MarineWeatherFlow(Flow[SqlFlowState]):
    """해상 날씨 분석 오케스트레이션 Flow"""

    def __init__(self):
        super().__init__()
        self.weather_crew = MarineWeatherCrew()

    @start()
    def generate_sql(self):
        print(
            f"\n [Step 1] SQL 생성 시도({self.state.retry_count + 1}회차)"
        )

        # 피드백이 존재하는 경우 Task 프롬프트에 동적 추가
        feedback_prompt = ""
        if self.state.feedback:
            feedback_prompt = f"""
            \n ⚠️ [이전 시도 실행 실패 피드백]:
            {self.state.feedback}
            위의 피드백/오류 원인을 정확히 반영하여 올바른 SQLite SELECT 쿼리로 수정하세요!
            """     

        crew = Crew(
            agents=[self.weather_crew.sql_generator_agent()], 
            tasks=[self.weather_crew.generate_sql_task()], 
            process=Process.sequential
        )

        result = crew.kickoff(
            inputs={
                "current_time": self.state.current_time,
                "user_query": self.state.user_query,
                "feedback_prompt": feedback_prompt
            }
        )

        self.state.generated_sql = result.raw
        self.state.retry_count += 1

    @listen(generate_sql)
    def validate_and_execute_sql(self):
        print("\n⚙️ [Step 2] 생성된 SQL 검증 및 DB 실행 중...") 

        crew = Crew(
            agents=[self.weather_crew.sql_executor_agent()],
            tasks=[self.weather_crew.validate_and_execute_sql_task()],
            process=Process.sequential
        )

        result = crew.kickoff(inputs={
            "generated_sql":self.state.generated_sql
        })

        raw_result = result.raw

        # SQL Error 발생할 경우 예외처리(2026/08/26)
        if "SQL Error:" in raw_result:
            self.state.is_valid = False
            self.state.retry_count += 1
            self.state.feedback = f"SQL 구분 오류 발생: {raw_result}"
            self.state.execution_result = "SQL 실행 에러"
            print(f"❌ DB 실행 에러 감지 (시도 횟수: {self.state.retry_count}/3)")

        # 검증 통과
        else:
            self.state.is_valid = True
            self.state.execution_result = (result.pydantic.model_dump_json(indent=2) if result.pydantic else raw_result)
            self.state.feedback = "" # 성공시 피드백 초기화
        
    @router(validate_and_execute_sql)
    def check_validation_result(self):
        if self.state.is_valid:
            print("[Validation Passed] SQL 실행 성공")
            return "success"
        elif self.state.retry_count >= 3:
            print("[Validation Failed] 최대 재시도 횟수(3회) 초과!")
            return "max_retries_exceeded"
        else:
            print(f"[ValidationFailed] SQL 재생성 진행. 이유: {self.state.feedback}")
            return "retry"

    @listen("retry")
    def handle_retry(self):
        """실패 시 피드백을 유지한 채 다시 SQL 생성으로 복귀"""
        print("[루프순환]: 피드백을 전달하며 generate_sql 단계로 돌아갑니다.")
        return self.generate_sql()

    @listen("success")
    def generate_final_answer(self):
        print("\n [Step 3] 검증된 데이터를 기반으로 최종 자연어 답변 생성 중...")

        crew = Crew(
            agents=[self.weather_crew.data_analyst_agent()],
            tasks=[self.weather_crew.generate_final_answer_task()],
            process=Process.sequential
        )

        result = crew.kickoff(inputs={
            "user_query": self.state.user_query,
            "execution_result": self.state.execution_result
        })

        self.state.final_answer = result.raw
        return self.state.final_answer

    @listen("max_retries_exeeded")
    def handle_max_retries(self):
        failure_msg = (
            "죄송합니다. 데이터 베이스 조회에 실패했습니다."
            f" (마지막 오류: {self.state.feedback})"
        )
        self.state.final_answer = failure_msg
        return failure_msg

def run_flow_pipeline(user_query: str):
    flow = MarineWeatherFlow()

    # 초기 user_query 주입
    flow.state.user_query = user_query

    # Flow 시작
    final_result = flow.kickoff()
    print(f"\n========================================")
    print(f"User Query: {flow.state.user_query}")
    print(f"Mock Current Time: {flow.state.current_time}")
    print(f"==========================================\n\n")

    print("\n===================[최종 출력 리포트]==================")
    print(f"\n[Generated SQL]\n{flow.state.generated_sql}")
    print(f"\n[Extracted Data]\n{flow.state.execution_result}")
    print(f"\n[Final Answer]\n {final_result}")

    return final_result
      
if __name__ == "__main__":
     user_query = "현재 시점 기준 부이 관측 데이터 중에서 수온이 21°C를 넘는 지점이 존재하나요?"
     run_flow_pipeline(user_query)
    




#------------
# TEST CASES 
#------------

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