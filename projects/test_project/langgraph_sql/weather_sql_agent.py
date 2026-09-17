import time
from typing import TypedDict, Literal, Annotated
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.utils.pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_community.agent_toolkits import SQLDatabaseToolkit
# from langchain.chat_models import init_chat_model
from langchain_community.utilities import SQLDatabase

from sql_agent_prompt import verification_query_system_prompt
from sql_agent_prompt import gen_query_prompt
from sql_agent_prompt import answer_system_prompt
from sql_agent_prompt import end_system_prompt

db = SQLDatabase.from_uri("sqlite:///weather_db.db")

llm = ChatOpenAI(
    api_key="ai",
    model="openai/gpt-oss-20b",
    base_url="http://192.168.0.110:8000/v1",
    temperature=0,
    max_tokens=8192
)

toolkit = SQLDatabaseToolkit(db=db, llm=llm)
tools = toolkit.get_tools()

# binding_llm = llm.bind_tools(tools)
execute_tool = ToolNode(tools)

run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
run_query_node = ToolNode([run_query_tool], name="run_query")


class SqlAgentState(TypedDict):
    user_question : str
    generated_query : str
    table_schema : list
    verification_count : int
    verification_error_content : str
    messages : Annotated[list[AnyMessage], add_messages]

def get_Database_info(state: SqlAgentState):
    msg = state["messages"][-1]
    get_schema = {
            "name": "sql_db_schema",
            "args": {"table_names": "weather_data"},
            "id": "sql_info_01",
            "type": "tool_call",
        }

    get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
    db_schema = get_schema_tool.invoke(get_schema)

    return {"table_schema": [db_schema.content], "verification_count": 0, "user_question" : msg.content}

def generate_query(state: SqlAgentState):
    verification_count = state.get("verification_count")
    verification_error_message = state.get("verification_error_content") or ""
    table_schema = state.get("table_schema", [])

    # 검증노드에서 온 로직 처리
    if verification_count > 3:
        end_message = {"role": "system", "content": end_system_prompt}
        response = llm.invoke([end_message] + state["messages"])
        return {"messages": [response]}

    query_gen_template = ChatPromptTemplate.from_messages(
        [("system", gen_query_prompt)],
        template_format="jinja2",
    ).format_messages(
        dialect=db.dialect,
        table_schema = table_schema,
        verification_error_message = verification_error_message,
    )[0]
    binded_llm = llm.bind_tools([run_query_tool])
    print("gen 전")
    response = binded_llm.invoke([query_gen_template] + state["messages"])
    print("gen 후")
    # print("gen 결과" + "*" * 44)
    # print(response)
    # print("*" * 55)
    # print(type(response))

    if not response.tool_calls:
        print("응답결과 출력" + "*" * 33)
        print(response.content)
        print("*"*55)
        return {"messages" : [response]}
    else:
        return {"messages" : [response], "generated_query": response.tool_calls[0]["args"]["query"]}

def should_continue(state: MessagesState) -> Literal["run_query", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "run_query"
    
    return "__end__"

class isAnswerable(BaseModel):
    """제공되는 쿼리 실행 결과를 바탕으로 질문에 대한 답변 생성이 가능한지 판단합니다"""
    query_check: bool = Field(
        description="'제공된 질문', '생성한 SQL 쿼리'를 바탕으로 제공된 질문에 답변이 가능한 쿼리가 잘 생성됐는지 판단하세요. 생성한 쿼리가 질문에서 요구하는 조건이나 값을 잘 반영하고 있으면 True, 아닐 경우 False로 답하세요"
    )
    query_check_reason: str = Field(
        description="query_check 판단 이유 (한 문장으로 간결히 한글로 작성)"
    )
    answerable: bool = Field(
        description="'제공된 질문', 'SQL 쿼리 실행 결과'를 바탕으로 제공된 질문에 대한 답변이 가능한지 판단하세요. 제공된 질문에 대한 답변이 가능하면 True, 아닐 경우 False로 답하세요."
    )
    answerable_reason: str = Field(
        description="answerable 판단 이유 (한 문장으로 간결히 한글로 작성)"
    )

def execute_verification(state: SqlAgentState):
    messages = state["messages"]
    last_message = messages[-1] # run_query가 추가한 ToolMessage
    
    # 1.쿼리 실행 간 에러 발생 시 쿼리 다시 생성
    content = str(last_message.content).lower()
    if "error" in content or "exception" in content or "operationalerror" in content:
        print("쿼리 실행 오류 디버깅" + "*" * 22)
        print(content)
        print("*" * 55)
        return{"verfication_count": state.get("verification_count", 0) + 1, "verification_error_content": content}

    answerable_checker = llm.with_structured_output(isAnswerable)

    verification_human_prompt = """
    [질문]
    {question}

    [생성된 SQL 쿼리]
    {generated_query}

    [쿼리 실행 결과]
    {execute_result}
    """

    verification_template = ChatPromptTemplate.from_messages([
        ("system", verification_query_system_prompt),
        ("human", verification_human_prompt)
    ]).partial(
        generated_query = state["generated_query"],
        execute_result = last_message.content
    )
    print("ver 전")
    chain = verification_template | answerable_checker
    result = chain.invoke({
        "question" : state["user_question"],
        "generate_query": state["generated_query"],
        "execute_result": last_message.content
    })
    print("ver 후")

    print("Answerable 결과" + "*" * 33)
    print(result)
    # print(result.query_check)
    # print(result.answerable)
    print("*" * 55)

    # 2.쿼리 실행 간 문제x, 빈값이 반환될 경우
    if not result.query_check:
        return{"verification_count": state.get("verification_count", 0) + 1, "verification_error_content": result.query_check_reason}

    # 3.쿼리 실행 간 문제x, 값도 반환되지만 질문에 답할 수 없는 경우
    if not result.answerable:
        return{"verification_count": state.get("verification_count", 0) + 1, "verification_error_content": result.answerable_reason}
    ai_msg = AIMessage(content=result.model_dump_json())
    return {"messages" : [ai_msg], "verification_count": 0, "verification_error_content": ""}

    # verified_prompt = verification_query_system_prompt.format(
    #     dialect=db.dialect,
    #     generated_query = state["generated_query"]
    # )    
    # system_message = {
    #     "role": "system",
    #     "content": verified_prompt,
    # }
    # user_message = {"role": "user", "content": state["generated_query"]}
    # response = llm.invoke([system_message, user_message])
    # return {"messages" : [response], "verfication_count": 0, "verification_error_content": ""}

def route_verified_query(state: SqlAgentState) -> Literal["generate_query", "generate_answer"]:
    count = state.get("verification_count", 0)
    if count > 0:
        print(f"ver_count: {state["verification_count"]}")
        return "generate_query"
    return "generate_answer"    

def generate_answer(state: MessagesState):
    system_message = {"role": "system", "content": answer_system_prompt}
    # 도구를 바인딩하지 않고 일반 LLM으로 호출하여 친절한 답변만 생성하게 함
    response = llm.invoke([system_message] + state["messages"])
    return {"messages": [response]}


builder = StateGraph(SqlAgentState)
builder.add_node("get_db_info", get_Database_info)
builder.add_node("generate_query", generate_query)
builder.add_node("run_query", run_query_node)
builder.add_node("execute_verification", execute_verification)
builder.add_node("generate_answer", generate_answer)

builder.add_edge(START, "get_db_info")
builder.add_edge("get_db_info", "generate_query")
builder.add_conditional_edges(
    "generate_query",
    should_continue
)
builder.add_edge("run_query", "execute_verification")
builder.add_conditional_edges(
    "execute_verification",
    route_verified_query
)
builder.add_edge("generate_answer", END)

sql_agent = builder.compile()


# result = sql_agent.invoke({"messages": [{"role": "user", "content": "25년 5월 5일 3시에 울릉도에서 관측된 기온은 몇도인가요?"}]})
# print(result["messages"][-1])

"""
1. 특정 지점 및 시간대별 기상/해상 상태 조회 (단순 조회 패턴)
Q1. 오늘 울릉도(지점 21229) 부이에서 관측된 기온은 몇 도인가요?
Q2. 2026년 3월 8일 오전 10시 기준으로 마라도 해역의 풍속과 풍향을 알려주세요.
Q3. 인천 앞바다의 현재 수온은 기온보다 높게 기록되어 있나요?
Q4. 가거도 지점의 최근 유의파고와 평균파고는 각각 얼마인가요?
Q5. 포항 앞바다의 습도가 가장 낮았던 시각은 몇 시인가요?
Q6. 3월 8일 오후 3시에 거문도 부이에서 관측된 GUST풍속은 얼마였나요?
Q7. 동해57 부이의 기압 변화 추이를 알고 싶습니다. 기압이 계속 상승하고 있나요?
Q8. 삼척 해역의 파주기(Wave Period)와 파향 상태를 알려주세요.
Q9. 구엄 부이 관측 데이터 중에서 수온이 15°C를 넘는 시간대가 존재하나요?
Q10. 울진 부이에서 측정된 최대파고가 가장 높았던 시각은 언제인가요?
2. 여러 해역 간 기상 및 해상 조건 비교 (비교 패턴)
Q11. 울릉도 해역과 동해 해역 중 어느 곳의 수온이 더 높나요?
Q12. 인천 앞바다와 울산 앞바다의 유의파고를 비교했을 때 어디의 파도가 더 높나요?
Q13. 남해의 거제도와 서해의 덕적도 중 어느 해역의 풍속(바람)이 더 강하게 부나요?
Q14. 마라도와 추자도 부이의 기온 편차는 얼마나 발생하고 있나요?
Q15. 동해 부이와 서해170 부이의 기압 값을 비교해서 고기압 영향권에 더 가까운 곳을 알려주세요.
Q16. 강릉 부이와 삼척 부이의 수온 추세가 서로 비슷하게 움직이고 있나요?
Q17. 칠발도와 거문도 중 평균파고를 기준으로 어디가 더 바다가 잔잔한가요?
Q18. 내륙 해안과 먼 서해206 부이와 내만 지역 부이의 습도 차이는 얼마나 되나요?
3. 극값 및 기상 위험 단계 탐지 (통계 및 임계값 패턴)
Q19. 전체 부이 관측소 중에서 오늘 가장 강한 Gust풍속이 기록된 곳은 어디인가요?
Q20. 전체 관측 데이터 중 수온이 가장 낮게 기록된 부이의 이름과 수온을 알려주세요.
Q21. 3월 8일 하루 동안 **기온의 일교차(최고 기온 - 최저 기온)**가 가장 컸던 지역은 어디인가요?
Q22. 유의파고가 1.5m를 초과하여 소형 선박 운항이 위험할 것으로 예상되는 부이 목록을 뽑아주세요.
Q23. 오늘 현지기압이 1030 hPa 이상으로 가장 높게 측정된 지점은 어디인가요?
Q24. 풍향이 북풍 계열(315도~45도 사이)로만 지속적으로 불고 있는 해역이 있나요?
Q25. 기온과 수온의 차이(기온 - 수온)가 가장 크게 벌어진 지점과 시간은 언제인가요?
Q26. 유의파고 대비 최대파고의 비율이 가장 높게 나타난 변칙적인 해역이 있나요?

4. 관리관서 및 위치 메타데이터 결합 (공간 결합 패턴)
Q27. **'부산지방기상청'**에서 관리하는 부이 중 유의파고가 가장 높은 지점명은 무엇인가요?
Q28. '강릉' 관리관서 소속 부이들의 실시간 평균 기온은 현재 몇 도인가요?
Q29. 위도 37도 이상의 북쪽 해역에 위치한 부이들의 수온 분포를 알려주세요.
Q30. **'목포기상대'**가 관리하는 관할 해역 부이들 중 풍속이 가장 센 곳은 어디인가요?
Q31. 제주지방기상청 소속 부이들의 위경도 좌표와 해당 지점들의 평균파고를 같이 보여주세요.
Q32. 관측을 개시한 지 가장 오래된(시작일이 가장 빠른) 역사적인 부이 지점은 어디이고, 현재 날씨는 어떤가요?

5. 실생활 조업 및 해상 안전 시나리오 (맥락적 패턴)
Q33. 지금 소매물도 부근으로 낚시를 가려고 하는데, 바람과 파고가 안전한 수준인가요?
Q34. 오늘 가거도 근해에서 어업 조업을 하기에 파주기와 파향이 적절한 상태인가요?
Q35. 최근 몇 시간 동안 기압이 급격히 떨어지면서 풍속이 강해지는 등 풍랑주의보 징후를 보이는 곳이 있나요?
Q36. 이수도와 지심도 인근 거제 양식장의 수온이 물고기들이 활동하기에 적절한 온도를 유지하고 있나요?
Q37. 인천, 풍도, 연평도 등 서해 중부 해역의 습도 상태를 볼 때 해무(바다 안개)가 발생할 가능성이 높나요?
Q38. 바람 방향(풍향)과 파도의 방향(파향)이 거의 일치하여 파도가 거세질 위험이 있는 지점은 어디인가요?
Q39. 태풍이나 풍랑에 대비하기 위해 **동해 해안선과 가장 멀리 떨어진 먼바다 부이(외해 부이)**의 기압 상태를 확인해 주세요.
Q40. 수온이 급격히 변화하는 조경수역(물덩어리가 만나는 곳)을 예측하기 위해 인접한 부이 중 수온 차가 가장 심한 구역을 알려주세요.
"""
# question =[
#     "25년 1월 2일 울릉도(지점 21229) 부이에서 관측된 기온은 몇 도인가요?",
#     "2025년 3월 8일 오전 10시 기준으로 마라도 해역의 풍속과 풍향을 알려주세요.",
#     "25년 1월 2일 인천 앞바다의 현재 수온은 기온보다 높게 기록되어 있나요?",
#     "25년 1월 2일 가거도 지점의 최근 유의파고와 평균파고는 각각 얼마인가요?",
#     "25년 1월 2일 포항 앞바다의 습도가 가장 낮았던 시각은 몇 시인가요?",
#     "3월 8일 오후 3시에 거문도 부이에서 관측된 GUST풍속은 얼마였나요?",
#     "25년 5월 13일 동해57 부이의 기압 변화 추이를 알고 싶습니다. 기압이 계속 상승하고 있나요?",
#     "25년 1월 2일 삼척 해역의 파주기(Wave Period)와 파향 상태를 알려주세요.",
#     "25년 1월 2일 구엄 부이 관측 데이터 중에서 수온이 15°C를 넘는 시간대가 존재하나요?",
#     "25년 1월 2일 울진 부이에서 측정된 최대파고가 가장 높았던 시각은 언제인가요?"
# ]

# question = [
#     "25년 1월 2일 울릉도 해역과 동해 해역 중 어느 곳의 수온이 더 높나요?",
#     "25년 1월 2일 인천 앞바다와 울산 앞바다의 유의파고를 비교했을 때 어디의 파도가 더 높나요?",
#     "25년 1월 2일 남해의 거제도와 서해의 덕적도 중 어느 해역의 풍속(바람)이 더 강하게 부나요?",
#     "25년 1월 2일 마라도와 추자도 부이의 기온 편차는 얼마나 발생하고 있나요?",
#     "25년 1월 2일 동해 부이와 서해170 부이의 기압 값을 비교해서 고기압 영향권에 더 가까운 곳을 알려주세요.",
#     "25년 1월 2일 강릉 부이와 삼척 부이의 수온 추세가 서로 비슷하게 움직이고 있나요?",
#     "25년 1월 2일 칠발도와 거문도 중 평균파고를 기준으로 어디가 더 바다가 잔잔한가요?",
#     "25년 1월 2일 내륙 해안과 먼 서해206 부이와 내만 지역 부이의 습도 차이는 얼마나 되나요?"
# ]

# question = [
#     "전체 부이 관측소 중에서 25년 1월 2일 가장 강한 Gust풍속이 기록된 곳은 어디인가요?",
#     "25년 1월 2일 전체 관측 데이터 중 수온이 가장 낮게 기록된 부이의 이름과 수온을 알려주세요.",
#     "3월 8일 하루 동안 **기온의 일교차(최고 기온 - 최저 기온)**가 가장 컸던 지역은 어디인가요?",
#     "25년 1월 2일 유의파고가 1.5m를 초과하여 소형 선박 운항이 위험할 것으로 예상되는 부이 목록을 뽑아주세요.",
#     "25년 1월 2일 현지기압이 1030 hPa 이상으로 가장 높게 측정된 지점은 어디인가요?",
#     "25년 1월 2일 풍향이 북풍 계열(315도~45도 사이)로만 지속적으로 불고 있는 해역이 있나요?",
#     "25년 1월 2일 기온과 수온의 차이(기온 - 수온)가 가장 크게 벌어진 지점과 시간은 언제인가요?",
#     "25년 1월 2일 유의파고 대비 최대파고의 비율이 가장 높게 나타난 변칙적인 해역이 있나요?"
# ]

question = [
    "7월 28일 소매물도 부근으로 낚시를 가려고 하는데, 바람과 파고가 안전한 수준인가요?",
    "7월 28일 가거도 근해에서 어업 조업을 하기에 파주기와 파향이 적절한 상태인가요?",
    "7월 28일 최근 몇 시간 동안 기압이 급격히 떨어지면서 풍속이 강해지는 등 풍랑주의보 징후를 보이는 곳이 있나요?",
    "7월 28일 이수도와 지심도 인근 거제 양식장의 수온이 물고기들이 활동하기에 적절한 온도를 유지하고 있나요?",
    "7월 28일 인천, 풍도, 연평도 등 서해 중부 해역의 습도 상태를 볼 때 해무(바다 안개)가 발생할 가능성이 높나요?",
    "7월 28일 바람 방향(풍향)과 파도의 방향(파향)이 거의 일치하여 파도가 거세질 위험이 있는 지점은 어디인가요?",
    "7월 28일 태풍이나 풍랑에 대비하기 위해 **동해 해안선과 가장 멀리 떨어진 먼바다 부이(외해 부이)**의 기압 상태를 확인해 주세요.",
    "7월 28일 수온이 급격히 변화하는 조경수역(물덩어리가 만나는 곳)을 예측하기 위해 인접한 부이 중 수온 차가 가장 심한 구역을 알려주세요."
]

# question = "2025년 3월 8일 오전 10시 기준으로 마라도 해역의 풍속과 풍향을 알려주세요."
# question = "2025년 3월 8일 오전 10시 기준으로 강릉 부이와 삼척 부이의 수온 추세가 서로 비슷하게 움직이고 있나요?"
# question = "25년 1월 2일 동해 부이와 서해170 부이의 기압 값을 비교해서 더 큰 곳을 알려주세요"
# question = "전체 부이 관측소 중에서 25년 1월 2일 가장 강한 Gust풍속이 기록된 곳은 어디인가요?"
# question = "25년 1월 2일 15시 기준 최근 몇 시간 동안 기압이 급격히 떨어지면서 풍속이 강해지는 등 풍랑주의보 징후를 보이는 곳이 있나요?"
# question = "25년 1월 2일 강릉 부이와 삼척 부이의 수온 추세가 서로 비슷하게 움직이고 있나요?"
# question = "25년 5월 15일 동해57 부이의 기압 변화 추이를 알고 싶습니다. 기압이 계속 상승하고 있나요?"

# question = "오늘 현지기압이 1030 hPa 이상으로 가장 높게 측정된 지점은 어디인가요?"
# question = "전체 부이 관측소 중에서 1월 21일 가장 강한 Gust풍속이 기록된 곳은 어디인가요?"
# question = "25년 1월 2일 풍향이 북풍 계열(315도~45도 사이)로만 지속적으로 불고 있는 해역이 있나요?"
# question = "25년 1월 2일 기온과 수온의 차이(기온 - 수온)가 가장 크게 벌어진 지점과 시간은 언제인가요?"
# question = "25년 1월 2일 유의파고 대비 최대파고의 비율이 가장 높게 나타난 변칙적인 해역이 있나요?"



for q in question:
    start_time = time.perf_counter()
    for step in sql_agent.stream(
        {"messages": [{"role": "user", "content": q}]},
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()
    total_duration = time.perf_counter() - start_time
    print(f"\n⏱️ 전체 실행 소요 시간: {total_duration:.2f}초")


# start_time = time.perf_counter()
# for step in sql_agent.stream(
#     {"messages": [{"role": "user", "content": question}]},
#     stream_mode="values",
# ):
#     step["messages"][-1].pretty_print()

# total_duration = time.perf_counter() - start_time
# print(f"\n⏱️ 전체 실행 소요 시간: {total_duration:.2f}초")
