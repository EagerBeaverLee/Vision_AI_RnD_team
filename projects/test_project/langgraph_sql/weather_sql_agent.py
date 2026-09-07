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

db = SQLDatabase.from_uri("sqlite:///weather_db.db")

llm = ChatOpenAI(
    api_key="ai",
    model="openai/gpt-oss-20b",
    base_url="http://192.168.0.110:8000/v1",
    temperature=0
)

toolkit = SQLDatabaseToolkit(db=db, llm=llm)
tools = toolkit.get_tools()

binding_llm = llm.bind_tools(tools)
execute_tool = ToolNode(tools)

run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
run_query_node = ToolNode([run_query_tool], name="run_query")



class SqlAgentState(TypedDict):
    table_list : list
    table_schema : list
    check_query_count : int
    check_query_error_content : str
    verification_count : int
    verification_error_content : str
    messages : Annotated[list[AnyMessage], add_messages]

def get_Database_info(state: SqlAgentState):
    get_table_list = {
        "name": "sql_db_list_tables",
        "args": {},
        "id": "sql_info_01",
        "type": "tool_call",
    }

    list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
    db_table_list = list_tables_tool.invoke(get_table_list)    

    get_schema = {
            "name": "sql_db_schema",
            "args": {"table_names": "weather_data"},
            "id": "sql_info_02",
            "type": "tool_call",
        }

    get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
    db_schema = get_schema_tool.invoke(get_schema)

    return {"table_list": [db_table_list.content], "table_schema": [db_schema.content]}

def generate_query(state: SqlAgentState):
    check_query_count = state.get("check_query_count")
    check_query_error_message = state.get("check_query_error_content") or ""
    verification_count = state.get("verification_count")
    verification_error_message = state.get("verification_error_content") or ""
    table_list = state.get("table_list", [])
    table_schema = state.get("table_schema", [])

    # print("*" * 55)
    # print(table_list)
    # print("*" * 55)
    # print(table_schema)
    # print("*" * 55)

    gen_query_prompt = """
        # 목표
        당신은 SQL 데이터베이스와 상호 작용하도록 설계된 에이전트입니다.
        입력 질문이 주어지면 구문적으로 올바른 {{dialect}} 쿼리를 생성하여 실행하고, 쿼리 결과를 살펴보고 답변을 반환합니다. 

        # 테이블 리스트
        {{table_list}}
        - 쿼리를 생성할 때 테이블 이름을 정확하게 작성하세요

        # 테이블 구조
        {{table_schema}}

        # 중요 규칙
        - 특정 테이블의 모든 열을 쿼리하지 말고, 질문에 맞는 관련 열만 요청하십시오.
        - 쿼리를 다시 작성하는 경우, 원래 질문의 의도를 정확하게 반영하도록 작성하십시오(예: "인천 해안"을 "인천"으로 변경할 때 [AND date LIKE '2025-07-06 10%']와 같은 다른 조건을 생략하지 마십시오).
        - '지점명' 열을 참조할 때는 다음 목록을 참조하여 해당 지점 이름에 대한 쿼리를 정확하게 작성하십시오.
        '지점명' 리스트: {{zone_name}}
        - 시간 및 메트릭 처리: 사용자가 특정 타임스탬프나 시간 범위를 지정하지 않고 위치/개체 간의 수치 메트릭(예: 온도, 풍속)을 비교하도록 요청하는 경우, 원시 시계열 행을 가져오지 마십시오. 대신, 개체별로 그룹화하여 `AVG()` 함수를 사용하여 평균값을 계산하거나(또는 개체 간에 `AVG(metric)`을 비교하여) 데이터를 요약하십시오.
        - 날짜 필터링 규칙: 특정 날짜(예: 'YYYY-MM-DD')로 필터링할 때 `date(column) = 'YYYY-MM-DD'`와 같은 함수를 사용하지 마십시오. SQLite의 `date()` 함수는 형식/공백이 약간 다르면 NULL을 반환합니다. 항상 `column LIKE 'YYYY-MM-DD%'`와 같은 문자열 패턴 일치를 사용하십시오.
        - 숫자 유형 캐스팅: 숫자를 저장하는 열이 TEXT 유형일 수 있습니다. 집계 함수(MAX, MIN, AVG) 및 산술 연산(예: MAX(CAST(온도 AS REAL)) - MIN(CAST(온도 AS REAL)))) 내에서 숫자 열을 사용할 때는 항상 `CAST(column AS REAL)`를 사용하여 명시적으로 형변환하십시오. 이렇게 하면 문자열 기반 비교로 인한 오류를 방지할 수 있습니다.
        - 질문에 답할 수 없는 경우, sql_db_query를 사용하여 질문에 대한 자세한 정보를 얻으십시오.
        - 타임스탬프/시간 열(일시)을 기준으로 정렬할 때는 항상 `ORDER BY datetime(column)`을 사용하고, 문자열로 직접 정렬하지 마십시오. 이렇게 하면 시간 순서대로 정렬되는 것을 보장할 수 있습니다.
        - 데이터베이스에 DML 문(INSERT, UPDATE, DELETE, DROP 등)을 실행하지 마십시오.

        {% if check_query_error_message %}
        [쿼리 문법 오류 검사 횟수]
        {{check_query_count}}
        [쿼리 문법 오류 검사 에러 내용]
        {{check_query_error_message}}
        쿼리 검증 횟수가 3회를 초과하지 않았을 경우 에러 메세지까지 참고해서 쿼리를 수정하세요
        {% endif %}

        {% if verification_error_message %}
        [쿼리 검증 횟수]
        {{verification_count}}
        [쿼리 검증 에러 내용]
        {{verification_error_message}}
        쿼리 검증 횟수가 3회를 초과하지 않았을 경우 에러 메세지까지 참고해서 쿼리를 수정하세요
        {% endif %}
    """

    query_gen_template = ChatPromptTemplate.from_messages(
        [("system", gen_query_prompt)],
        template_format="jinja2",
    ).format_messages(
        dialect=db.dialect,
        zone_name=db.run("SELECT DISTINCT 지점명 from weather_data"),
        table_list = table_list,
        table_schema = table_schema,
        check_query_count = check_query_count,
        check_query_error_message = check_query_error_message,
        verification_count = verification_count,
        verification_error_message = verification_error_message,
    )[0]
    binded_llm = llm.bind_tools([run_query_tool])
    # print("*" * 55)
    # print(query_gen_template)
    # print("*" * 55)
    response = binded_llm.invoke([query_gen_template] + state["messages"])
    return {"messages" : [response]}

check_query_prompt  = """
    당신은 꼼꼼한 SQL 전문가입니다

    # 역할
    다음과 같은 일반적인 오류를 포함하여 {dialect} 쿼리를 다시 한번 확인하세요
    - NOT IN을 NULL 값과 함께 사용
    - UNION ALL을 사용해야 할 때 UNION 사용
    - BETWEEN을 배타적 범위로 사용
    - 조건자에서 데이터 형식 불일치
    - 식별자를 올바르게 따옴표로 묶음
    - 함수에 올바른 개수의 인수 사용
    - 올바른 데이터 형식으로 캐스팅
    - 조인에 적절한 열 사용

    사용자 쿼리:
    {user_query}

"""

check_query_template = ChatPromptTemplate.from_messages([
    ("system", check_query_prompt),
    ("human", "{user_query}")
]).partial(
    dialect=db.dialect
)

execute_prompt = """
    당신은 SQL 전문가입니다
    제공된 도구를 이용해서 쿼리를 실행하세요
"""

class CheckQuery(BaseModel):
    """사용자의 쿼리가 실행 가능한지 아닌지 판단합니다"""
    query_execute: bool = Field(
        description="쿼리가 실행 가능한지 아닌지 판단하세요. 쿼리가 그대로 실행 가능하다고 판단되면 True, 아닐경우 False로 답하세요"
    )
    reason: str = Field(
        description="쿼리의 실행 가능여부를 True나 False로 평가한 이유에 대해 최대 2줄 이내로 한글로 설명하세요"
    )

def check_query(state: SqlAgentState):
    # generat_query에서 생성한 쿼리 주입을 위한 작업
    tool_call = state["messages"][-1].tool_calls[0]
    user_message = {"role": "user", "content": tool_call["args"]["query"]}

    query_checker = llm.with_structured_output(CheckQuery)

    query_check_chain = check_query_template | query_checker
    result = query_check_chain.invoke({"user_query": user_message})
    isExecutable = result.query_execute

    print("디버깅" + "*" * 45)
    print(result.query_execute)
    print(result.reason)
    print("*" * 55)

    if isExecutable:
        #True
        llm_with_tools = llm.bind_tools([run_query_tool], tool_choice="any")
        response = llm_with_tools.invoke([execute_prompt, user_message])
        response.id = state["messages"][-1].id
        return {"messages" : [response]}
    else:
        return {
            "check_query_count": state.get("check_query_count", 0) + 1,
            "check_query_error_content": result.reason
        }

def route_check_query(state: SqlAgentState) -> Literal["run_query", "generate_query"]:
    if state["messages"][-1].tool_calls:
        return "run_query"
    return "generate_query"
    

answer_system_prompt = """
    당신은 유용한 날씨 데이터를 바탕으로 응답을 생성하는 전문가입니다

    사용자의 원래 질문과 메세지에 제공된 SQL 쿼리 결과를 분석하여
    명확하고 자연스럽고 정중한 한국어 답변을 제공하세요

    규칙:
    - 수치 데이터는 적절한 단위(e.g., ℃, m/s)를 사용하여 명확하게 표시하세요
    - 관련성이 있는 경우 주요 정보(예: 최대/최소 차이, 평균)를 요약하세요.
    - SQL 쿼리를 생성하지 마세요. 사용자에게 일반 텍스트로 답변만 제공하세요.
"""

def generate_answer(state: MessagesState):
    system_message = {"role": "system", "content": answer_system_prompt}
    # 도구를 바인딩하지 않고 일반 LLM으로 호출하여 친절한 답변만 생성하게 함
    response = llm.invoke([system_message] + state["messages"])
    return {"messages": [response]}


builder = StateGraph(SqlAgentState)
builder.add_node("get_db_info", get_Database_info)
builder.add_node("generate_query", generate_query)
builder.add_node("check_query", check_query)
builder.add_node("run_query", run_query_node)
builder.add_node("generate_answer", generate_answer)

builder.add_edge(START, "get_db_info")
builder.add_edge("get_db_info", "generate_query")
builder.add_edge("generate_query", "check_query")
builder.add_conditional_edges(
    "check_query",
    route_check_query,
)
builder.add_edge("run_query", "generate_answer")
builder.add_edge("generate_answer", END)

sql_agent = builder.compile()


# result = sql_agent.invoke({"messages": [{"role": "user", "content": "25년 5월 5일 3시에 울릉도에서 관측된 기온은 몇도인가요?"}]})
# print(result["messages"][-1])

# question = "25년 1월 2일 16시에 울릉도에서 관측된 기온은 몇도인가요?"
question = "25년 1월 2일 16시에 울진에서 관측된 기온은 몇도인가요?"


for step in sql_agent.stream(
    {"messages": [{"role": "user", "content": question}]},
    stream_mode="values",
):
    step["messages"][-1].pretty_print()



