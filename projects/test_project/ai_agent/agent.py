# -----------------------------------------------------------------------------
# Import libraries
# -----------------------------------------------------------------------------

import os, sqlite3, json, duckdb
import uuid
import asyncio
import operator

from typing import Annotated, Sequence, TypedDict, Literal, Optional, List, Dict
from dotenv import load_dotenv
import random
from enum import Enum
from pydantic import BaseModel, Field
import pandas as pd

from langfuse.langchain import CallbackHandler

from datetime import datetime, timedelta
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.managed.is_last_step import RemainingSteps
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


# from openinference.instrumentation.langchain import LangChainInstrumentor

# session = px.launch_app()

# LangChainInstrumentor().instrument()
from phoenix.otel import register
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = 'http://localhost:6006'

tracer_provider = register(
  project_name="default",
  auto_instrument=True
)

# load_dotenv()

# Prompt
ROUTER_SYSTEM_PROMPT = (
    "You are a router. Given the following user messages, decide if it is weather information question(about current weather info or more detail about weather info like temperature or humidity)" \
    "or ais trajectory question(about Current status of the vessel, such as its current location, status, and track.)\n" \
    "If it is a weather information question, respond with 'weather_info_agent'.\n" \
    "If it is ais trajectory question, respond with 'ais_trajectory_reporting_agent'"
)

WEATHER_AGENT_GUARDRAIL_SYSTEM_PROMPT = ( 
    """
    당신은 사용자 질문을 분류하는 엄격한 도메인 분류기입니다.

    당신의 임무는 질문에 답변하는 것이 아닙니다.
    실시간 데이터 접근 가능 여부, 도구 사용 가능 여부, 답변 가능 여부를 판단하지 마세요.
    오직 사용자 질문이 허용된 도메인에 속하는지만 판단하세요.

    허용 도메인:
    1. 현재 날씨 또는 해상 기상정보 관련 질문
    - 현재 날씨
    - 기온
    - 습도
    - 풍속
    - 풍향
    - 돌풍
    - 기압
    - 수온
    - 파고
    - 파주기
    - 파향
    - 해상 상태
    - 현재 기상정보에 대한 일반적인 질문 또는 세부 질문

    판정 규칙:
    - 질문에 AIS 또는 현재 날씨/해상 기상정보 관련 내용이 포함되어 있으면 반드시 is_AIS_report=True로 분류하세요.
    - "현재 날씨에 대해 묘사해줘"는 반드시 is_AIS_report=True입니다.
    - "날씨 알려줘", "지금 바다 상태 어때?", "파고는 어때?", "풍속 알려줘"도 반드시 True입니다.
    - 질문이 비어 있거나 의미 있는 질문이 없으면 False입니다.
    - 허용 도메인과 무관한 질문이면 False입니다.

    reason에는 짧게 분류 이유만 쓰세요.
    답변을 생성하려고 하지 마세요.
    실시간 데이터 접근 가능 여부를 언급하지 마세요.
    """
)

AIS_TRAJECTORY_GUARDRAIL_SYSTEM_PROMPT = (
    """
    당신은 사용자 질문을 분류하는 엄격한 도메인 분류기입니다.

    당신의 임무는 질문에 답변하는 것이 아닙니다.
    실시간 데이터 접근 가능 여부, 도구 사용 가능 여부, 답변 가능 여부를 판단하지 마세요.
    오직 사용자 질문이 허용된 도메인에 속하는지만 판단하세요.

    허용 도메인:
    1. AIS 관련 질문
    - 선박의 현재 상태
    - 선박 위치
    - 항적
    - 이동 속도
    - 선박 이동 방향
    - AIS 궤적에 대한 일반적인 질문 또는 세부 질문

    판정 규칙:
    - 질문에 AIS 또는 현재 항적, 이동패턴 등 관련 내용이 포함되어 있으면 반드시 is_AIS_report=True로 분류하세요.
    - "현재 항적에 대해 묘사해줘"는 반드시 is_AIS_report=True입니다.
    - "선박이 현재 어느 위치에 있어?", "항적의 이동방향은 어디야?", "선박의 최고속도 알려줘"도 반드시 True입니다.
    - 질문이 비어 있거나 의미 있는 질문이 없으면 False입니다.
    - 허용 도메인과 무관한 질문이면 False입니다.

    reason에는 짧게 분류 이유만 쓰세요.
    답변을 생성하려고 하지 마세요.
    실시간 데이터 접근 가능 여부를 언급하지 마세요.
    """
)

AGENT_REFUSAL_INSTRUCTION = ( 
    "You can only help with ais trajectory report-related questions (current status of the vessel, such as its current location, status, and track" \
    "or weather information like temperature, humidity). The user's request is not ais trajectory report-related. "
    "Or it might be a trajectory related question but not focusing AIS(Automatic Identification System) "
    "Politely refuse and briefly explain what topics you can help with."
)

GUARDRAIL_SYSTEM_PROMPT = (
    """
    당신은 사용자 질문을 분류하는 엄격한 도메인 분류기입니다.

    당신의 임무는 질문에 답변하는 것이 아닙니다.
    실시간 데이터 접근 가능 여부, 도구 사용 가능 여부, 답변 가능 여부를 판단하지 마세요.
    오직 사용자 질문이 허용된 도메인에 속하는지만 판단하세요.

    허용 도메인:
    1. AIS 관련 질문
    - 선박의 현재 상태
    - 선박 위치
    - 항적
    - 이동 속도
    - 선박 이동 방향
    - AIS 궤적에 대한 일반적인 질문 또는 세부 질문

    2. 현재 날씨 또는 해상 기상정보 관련 질문
    - 현재 날씨
    - 기온
    - 습도
    - 풍속
    - 풍향
    - 돌풍
    - 기압
    - 수온
    - 파고
    - 파주기
    - 파향
    - 해상 상태
    - 현재 기상정보에 대한 일반적인 질문 또는 세부 질문

    판정 규칙:
    - 질문에 AIS 또는 현재 날씨/해상 기상정보 관련 내용이 포함되어 있으면 반드시 is_AIS_report=True로 분류하세요.
    - "현재 날씨에 대해 묘사해줘"는 반드시 is_AIS_report=True입니다.
    - "날씨 알려줘", "지금 바다 상태 어때?", "파고는 어때?", "풍속 알려줘"도 반드시 True입니다.
    - 질문이 비어 있거나 의미 있는 질문이 없으면 False입니다.
    - 허용 도메인과 무관한 질문이면 False입니다.

    reason에는 짧게 분류 이유만 쓰세요.
    답변을 생성하려고 하지 마세요.
    실시간 데이터 접근 가능 여부를 언급하지 마세요.
    """
    # "You are a strict classifier. When the user's last question comes in, you must answer only questions following AIS report."
    # "The AIS report includes the AIS trajectory like current status of the vessel, such as its current location, status, track"
    # "and weather information question such as temperature, humidity, wind, wave."
    
)

llm_model = ChatOpenAI(
    model="openai/gpt-oss-20b",
    api_key="ai",
    base_url="http://192.168.0.110:8000/v1",
    # model="gpt-5", #A
    use_responses_api=True, #B                      
    use_previous_response_id=True,
    output_version="responses/v1"
    ) #C
llm_classifier = ChatOpenAI(
    model="openai/gpt-oss-20b",
    api_key="ai",
    base_url="http://192.168.0.110:8000/v1",
)

class AgentState(TypedDict): #A
    messages: Annotated[Sequence[BaseMessage], operator.add]
    remaining_steps: RemainingSteps #B

class AgentType(str, Enum):
    weather_info_agent = "weather_info_agent"
    ais_trajectory_reporting_agent = "ais_trajectory_reporting_agent"

class AgentTypeOutput(BaseModel): 
    agent: AgentType = Field(..., description="Which agent should handle the query?")

llm_router = llm_classifier.with_structured_output(AgentTypeOutput)

class GuardrailDecision(BaseModel): #A
    is_AIS_report: bool = Field(
        ...,
        description=(
            "사용자 질문이 AIS, 선박 상태/위치/항적/속도, "
            "또는 현재 날씨/해상 기상정보 도메인에 속하면 True. "
            "이외에 모든 질문은 False."
            "답변 가능 여부나 실시간 데이터 접근 가능 여부와는 무관하다." \
        ),
    )
    reason: str = Field(..., description="Brief justification for the decision.")

llm_guardrail = llm_classifier.with_structured_output(GuardrailDecision) #D

# -----------------------------------------------------------------------------
# Router Agent Node for LangGraph (with structured output)
# -----------------------------------------------------------------------------
def router_agent_node(state: AgentState) -> Command[AgentType]:
    """Router node: decides which agent should handle the user query."""
    messages = state["messages"] 
    last_msg = messages[-1] if messages else None 
    if isinstance(last_msg, HumanMessage):
        print("*"*20 + "사용자 입력" + "*"*20)
        print(last_msg.content)
        user_input = last_msg.content 

        # Guardrail classification at routing time
        classifier_messages = [
            SystemMessage(content=GUARDRAIL_SYSTEM_PROMPT), #A
            HumanMessage(content=user_input),
        ]
        decision = llm_guardrail.invoke(classifier_messages) #B
        print("*"*20 + "시작 classifier 디버깅" + "*"*20)
        print(decision)
        if not decision.is_AIS_report: #C
            # Return refusal directly as an AI message and shortcut to END via a dedicated node
            refusal_text = ( #D
                "Sorry, I can only help with weather information(current weather info, more detail about weather info like temperature or humidity) "
                "or ais trajectory report(current status of the vessel, such as its current location, status, and track.)"
            )
            return Command( #E
                # update={"messages": [AIMessage(content=refusal_text)]},
                update={
                    "messages": [
                        {
                            "role": "assistant", 
                            "content": refusal_text
                        }
                    ]
                },
                goto="guardrail_refusal",
            ) 

        router_messages = [ 
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_input)
        ]
        router_response = llm_router.invoke(router_messages) 
        agent_name = router_response.agent.value
        print("*"*20 + "라우팅 디버깅" + "*"*20)
        print(agent_name)
        return Command(update=state, goto=agent_name) 
    print("*"*20 + "isinstance none" + "*"*20)
    print(last_msg.content)
    return Command(update=state, goto=AgentType.weather_info_agent)


def refusal_command():
    refusal_text = (
        "Sorry, I can only help with weather information(current weather info, more detail about weather info like temperature or humidity) "
        "or ais trajectory report: current status of the vessel, such as its current location, status, and track. "
    )

    return Command(
        update={
            "messages": [
                {
                    "role": "assistant", 
                    "content": refusal_text
                }
            ]
        },
        goto="guardrail_refusal",
    )


def pre_model_weather_guardrail(state: dict):
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    if not isinstance(last_msg, HumanMessage): #A
        return {}

    user_input = last_msg.content
    classifier_messages = [ #B
        SystemMessage(content=WEATHER_AGENT_GUARDRAIL_SYSTEM_PROMPT),
        HumanMessage(content=user_input),
    ]
    decision = llm_guardrail.invoke(classifier_messages)
    print("*"*20 + "날씨 가드리얼 디버깅" + "*"*20)
    print(decision)
    if decision.is_AIS_report: #C
        # Allow normal flow; do not modify inputs
        return {}
    
    return refusal_command()
    

def pre_model_ais_trajectory_guardrail(state: dict):
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    if not isinstance(last_msg, HumanMessage): #A
        return {}

    user_input = last_msg.content
    classifier_messages = [ #B
        SystemMessage(content=AIS_TRAJECTORY_GUARDRAIL_SYSTEM_PROMPT),
        HumanMessage(content=user_input),
    ]
    decision = llm_guardrail.invoke(classifier_messages)
    print("*"*20 + "항적 가드리얼 디버깅" + "*"*20)
    print(decision)
    if decision.is_AIS_report: #C
        # Allow normal flow; do not modify inputs
        return {}
    
    return refusal_command()

def guardrail_refusal_node(state: AgentState): #A
    return {}

@tool(description="현재 날씨와 해상 상태를 조회")
def fetch_weather_information(question: str) -> str:
    """"""
    conn = sqlite3.connect('d:/LEE/AI_team/github/Vision_AI_RnD_team/projects/test_project/ais_weather/korea_weather.db', check_same_thread=False)
    weather_cursor = conn.cursor()

    query = """
            SELECT 
                b.지점명,
                b.latitude, 
                b.longitude, 
                w.*
            FROM 
                weather_buoy AS w
            JOIN 
                buoy_position AS b ON w.지점 = b.지점
            WHERE 
                w.일시 LIKE ?
        """

    # 3. 쿼리 실행
    current_hour_str = '2025-12-10 3'
    search_param = f"{current_hour_str}:%"
    weather_cursor.execute(query, (search_param,))
    rows = weather_cursor.fetchall()

    col_names = [desc[0] for desc in weather_cursor.description]
    df = pd.DataFrame(rows, columns=col_names)

    # 3. 컬럼 슬라이싱 (Pandas에서 처리)
    target_cols = [0, 1, 2] + list(range(5, len(df.columns)))
    final_df = df.iloc[:, target_cols]

    target_columns = [
        "풍속(m/s)", "풍향(deg)", "GUST풍속(m/s)", "현지기압(hPa)", 
        "습도(%)", "기온(°C)", "수온(°C)", "최대파고(m)", 
        "유의파고(m)", "평균파고(m)", "파주기(sec)", "파향(deg)"
    ]

    weather_avg = final_df[target_columns].mean().round(2)

    weather_data = json.dumps(weather_avg.to_dict(), ensure_ascii=False, indent=4, default=str)

    print("*"*20 + "날씨 데이터" + "*"*20)
    print(weather_data)

    
    weather_report_template = """
    # Context & Rules (필독)
    1. **[현재 날씨 요약]**: 1번 데이터를 활용하여 현재 기상날씨에 대해 요약하여 설명하세요.
        - Gust풍속은 순간풍속을 의미함.
        - 누락되는 column 없이 수치 명시.
    
    #Input Data
    1. [현재 날씨 요약]:
        {weather_data}

    # Tone & Manner
        - 전문가용 관제 보고서 스타일 (명조체 중심의 정중하고 명확한 문체)
        - 수치와 제공된 데이터 기반 팩트 위주의 서술
    """

    weather_report_prompt = ChatPromptTemplate.from_template(weather_report_template)

    chain = (
        RunnablePassthrough.assign(
            weather_data = lambda x: weather_data,
        )
        | weather_report_prompt
        | llm_model
    )

    answer = chain.invoke({"question": question})
    if answer:
        return answer.content

WEATHER_AGENT_TOOLS = [fetch_weather_information]

weather_info_agent = create_react_agent(
    model=llm_model,
    tools=WEATHER_AGENT_TOOLS,
    state_schema=AgentState,
    prompt=
    """당신은 날씨 정보를 제공하는 유용한 조력자입니다.

    사용자가 현재 날씨, 지금 날씨, 날씨 묘사, 해상 상태, 바람, 파고, 기온 등을 물으면
    반드시 fetch_weather_information 도구를 먼저 호출하세요.

    사용자가 위치를 제공하지 않아도 위치를 되묻지 마세요.
    fetch_weather_information 도구는 기본 관측 지점의 현재 날씨를 반환하므로 location이 필요하지 않습니다.
    """,
    pre_model_hook=pre_model_weather_guardrail,
)

def compress_ship_data_duckdb_further(db_path, table_name, min_time, max_time, min_lon=125.678, max_lon=131.229, max_lat=36.001):
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE SQLITE);")

    query = f"""
    -- [STEP 1] Raw 데이터 로드 및 1차 트리거 (정수 변환 비교로 정밀도 확보)
    WITH raw_data AS (
        SELECT *,
            CAST(timestamp AS TIMESTAMP) as ts,
            CAST(longitude AS DOUBLE) as lon_val,
            CAST(latitude AS DOUBLE) as lat_val,
            CAST(course AS DOUBLE) as c_course,
            CAST(speed AS DOUBLE) as s_speed,
            row_number() OVER () as temp_row_idx
        FROM sqlite_db.{table_name}
        WHERE longitude >= {min_lon} AND longitude <= {max_lon} AND latitude <= {max_lat}
            AND timestamp BETWEEN '{min_time}' AND '{max_time}'
    ),
    ordered_data AS (
        SELECT *,
            LAG(lon_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lon,
            LAG(lat_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lat,
            LAG(c_course) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_course,
            LAG(s_speed) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_speed
        FROM raw_data
    ),
    diff_calc AS (
        SELECT *,
            CASE WHEN CAST(lon_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lon, lon_val) * 1000 AS BIGINT) 
                OR CAST(lat_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lat, lat_val) * 1000 AS BIGINT) 
                THEN 1 ELSE 0 END as pos_change,
            CASE 
                WHEN (c_course - COALESCE(prev_course, c_course)) > 180 THEN (c_course - COALESCE(prev_course, c_course)) - 360
                WHEN (c_course - COALESCE(prev_course, c_course)) < -180 THEN (c_course - COALESCE(prev_course, c_course)) + 360
                ELSE (c_course - COALESCE(prev_course, c_course))
            END as course_diff,
            (s_speed - COALESCE(prev_speed, s_speed)) as speed_diff
        FROM ordered_data
    ),
    event_logic AS (
        SELECT *,
            -- 경계값 오차 방지를 위해 0.000001 보정 (Pandas와의 일치성 향상)
            CASE WHEN pos_change = 1 OR (ABS(course_diff) >= 19.999999 AND s_speed >= 0.999999) OR ABS(speed_diff) >= 1.999999 THEN 1 ELSE 0 END as event_trigger
        FROM diff_calc
    ),
    grouping_v1 AS (
        SELECT *,
            SUM(event_trigger) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id_v1
        FROM event_logic
    ),
    summarized_v1 AS (
        -- [1차 압축] ANY_VALUE 대신 FIRST를 사용하여 Pandas .first()와 100% 일치화
        SELECT 
            ShipName, group_id_v1,
            FIRST(mmsi) as mmsi, FIRST(higher_types) as higher_types, FIRST(radius) as radius,
            MIN(ts) as start_time, MAX(ts) as end_time,
            FIRST(lon_val) as lon, FIRST(lat_val) as lat,
            FIRST(c_course) as first_course, AVG(s_speed) as avg_speed,
            FIRST(course_diff) as turn_val, FIRST(speed_diff) as accel_val
        FROM grouping_v1 
        GROUP BY ShipName, group_id_v1
    ),
    -- [STEP 2] 상태 판별 (부동소수점 오차 차단)
    status_calc AS (
        SELECT *,
            avg_speed - COALESCE(LAG(avg_speed) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1), avg_speed) as group_speed_diff
        FROM summarized_v1
    ),
    status_final AS (
        SELECT *,
            CASE 
                -- 1.0, 20.0 등의 경계값을 소수점 8자리에서 반올림 후 비교하여 Pandas와 일치시킴
                WHEN ROUND(avg_speed, 8) < 1.0 THEN '정박/대기'
                ELSE TRIM(CONCAT_WS(' ',
                    CASE WHEN ROUND(ABS(turn_val), 8) >= 20.0 AND ROUND(avg_speed, 8) >= 1.0 
                        THEN (CASE WHEN turn_val > 0 THEN '우선회' ELSE '좌선회' END) || '(' || ROUND(ABS(turn_val), 1) || '°)' ELSE '' END,
                    CASE WHEN ROUND(group_speed_diff, 8) >= 2.0 THEN '가속' 
                        WHEN ROUND(group_speed_diff, 8) < -2.0 THEN '감속' ELSE '' END,
                    CASE WHEN ROUND(avg_speed, 8) >= 5.0 THEN '이동/통과' ELSE '저속 운항' END
                ))
            END as status
        FROM status_calc
    ),
    -- [STEP 3] 2차 압축
    v2_trigger AS (
        SELECT *,
            CASE WHEN status != COALESCE(LAG(status) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1), status) 
                THEN 1 ELSE 0 END as status_change
        FROM status_final
    ),
    v2_grouping AS (
        SELECT *,
            SUM(status_change) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id
        FROM v2_trigger
    )
    -- [STEP 4] 최종 요약 (집계 방식 일치)
    SELECT 
        ShipName, group_id,
        FIRST(mmsi) as mmsi, FIRST(higher_types) as higher_types, FIRST(radius) as radius,
        MIN(start_time) as start_time, MAX(end_time) as end_time,
        FIRST(lon) as lon, FIRST(lat) as lat,
        FIRST(first_course) as first_course,
        AVG(avg_speed) as avg_speed,
        FIRST(turn_val) as turn_val,
        FIRST(accel_val) as accel_val,
        FIRST(status) as status
    FROM v2_grouping
    GROUP BY ShipName, group_id
    ORDER BY ShipName, start_time
    """

    df_result = con.execute(query).df()
    con.execute("DETACH sqlite_db;")
    return df_result

def create_dynamic_route_prompt(num_ships, start_time, end_time, time_diff):
    # 배의 개수만큼 프롬프트 안에 들어갈 변수 리스트를 동적으로 생성
    trajectory_data = "\n".join([f"선박{i+1} 데이터: {{ship{i+1}}}" for i in range(num_ships)])
    
    system_template = f"""
    # Role
    당신은 대한민국 주변 선박운행을 관제하는 베테랑 해상 관제사(VTS Operator)이자 선박 항적 분석 전문가 입니다. 
    아래 제공된 {num_ships}척의 요약된 항적 데이터(Summarized Trajectory)를 바탕으로 선박의 이동 패턴과 주요 이벤트를 전문적인 자연어로 묘사해주세요.
    
    #Input Data (Summarized Trajectory)
    1. [선박별 항해 패턴]:
    {trajectory_data}

    # Context & Rules (필독)
        - **[데이터 근거]**: 모든 분석은 수치에만 근거하며, 상상이나 추측은 엄격히 금지합니다.
        - markdown 구조를 정확하게 지켜서 출력하세요
    
    # Mission: 리포트 구성 가이드라인
    1. [분석 대상 시간]:
        - 시작 시점: {start_time}
        - 종료 시점: {end_time}
        - (약 {time_diff} 동안의 데이터 집계 결과)
    2. **[선박별 항해 패턴]**:
        - 제공된 1번 데이터를 활용하여 선박별 전체적인 항해패턴을 누락되는 배 없이 간단히 요약
        - "status"필드를 기준으로 하되 start_time과 end_time을 참고하여 특징적인 항목(좌·우선회, 급 감·가속)위주로 요약, 배끼리 데이터가 혼용되지 않도록 주의
        - 관제사가 관심을 가져야 할 특이사항 위주로 간단하게 언급
    3. **[종합 결론]**:  
        - 현재 데이터상에서 나타나는 가장 두드러진 해상 교통 특징 및 관제 주의사항 간략하게 요약하여 기술
    """

    return ChatPromptTemplate.from_messages([
        ("system", system_template),
        ("human", "{question}")
    ])

@tool(description="개별항적에 대한 ais report를 생성할 수 있고 선박에 대한 정보를 얻을 수 있음")
def individual_ais_trajectory_reporting(question: str) -> str:
    full_path = "ships.db"

    start_time, end_time, time_diff = "2022-12-01 00:00:00", "2022-12-01 03:00:00", timedelta(seconds=10800)

    #mmsi로 배 선택
    target_mmsi = [371473000, 563161700]
    compress_twice = compress_ship_data_duckdb_further(db_path=full_path, table_name="ship_logs", min_time=start_time, max_time=end_time)

    filtered_mmsi = compress_twice[compress_twice['mmsi'].isin(target_mmsi)].copy()

    ship_input_data = {
        f"ship{i+1}": json.dumps(df.to_dict(orient='records'), ensure_ascii=False, default=str, indent=4)
        for i, (_, df) in enumerate(filtered_mmsi.groupby('ShipName', sort=False))
    }
    
    # 1. 현재 배의 개수 파악
    num_ships = len(ship_input_data)

    # 현재 필터링된 선박 수
    print(num_ships)
    print("*" * 55)

    # 2. 개수에 맞는 템플릿 생성
    dynamic_prompt = create_dynamic_route_prompt(num_ships, start_time, end_time, time_diff)

    # 4. 실행
    chain = dynamic_prompt | llm_model

    inputs = {"question": question}
    inputs.update(ship_input_data)

    answer = chain.invoke(inputs)
    if answer:
        return answer.content

# @tool(description="")
# def 


REPORTING_AGENT_TOOLS = [individual_ais_trajectory_reporting]

ais_trajectory_reporting_agent = create_react_agent(
    model=llm_model,
    tools=REPORTING_AGENT_TOOLS,
    state_schema=AgentState,
    prompt="""
    당신은 ais 항적 정보를 제공하는 유용한 조력자입니다.

    사용자가 현재 운항중인 선박에 대한 묘사와 같은 
    선박의 이동패턴, 위치, 선회 여부 등 ais 항적에 관한 전반적인 질문 또는 세부적인 질문을 할 경우
    반드시 individual_ais_trajectory_reporting 도구를 먼저 호출하세요
    """,
    pre_model_hook=pre_model_ais_trajectory_guardrail,
)

graph = StateGraph(AgentState)
graph.add_node("router_agent", router_agent_node) 
graph.add_node("weather_info_agent", weather_info_agent) 
graph.add_node("ais_trajectory_reporting_agent", ais_trajectory_reporting_agent) 
graph.add_node("guardrail_refusal", guardrail_refusal_node) #B

graph.add_edge("weather_info_agent", END) 
graph.add_edge("ais_trajectory_reporting_agent", END) 
graph.add_edge("guardrail_refusal", END) #C

graph.set_entry_point("router_agent") 

checkpointer = InMemorySaver() 
travel_assistant = graph.compile(checkpointer=checkpointer) 

#A Define the guardrail refusal node, which is a no-op node that is used to shortcut to END 
#B Add the guardrail refusal node
#C Add the edge from the guardrail refusal node to the end


# ----------------------------------------------------------------------------
# 5. Simple CLI interface
# ----------------------------------------------------------------------------

def chat_loop(): #A
    thread_id=uuid.uuid1() #B
    phoenix_id = str(uuid.uuid4())
    # langfuse_handler = CallbackHandler()
    print(f'Thread ID: {thread_id}') 
    config={
        # "configurable": {"thread_id": thread_id},
        "configurable": {"thread_id": phoenix_id},
        # "callbacks": [langfuse_handler]
    } #B

    print("UK Travel Assistant (type 'exit' to quit)")
    while True:
        user_input = input("You: ").strip() #C
        if user_input.lower() in {"exit", "quit"}: #D
            break
        state = {"messages": [HumanMessage(content=user_input)]} #E
        result = travel_assistant.invoke(state, config=config) #F
        response_msg = result["messages"][-1] #G
        if isinstance(response_msg, dict):
            # response_msg가 딕셔너리인 경우 (가드레일에서 거절 메시지를 보냈을 때)
            response_text = response_msg.get("content", "")
        else:
            # response_msg가 객체인 경우 (메인 에이전트가 정상적으로 대답했을 때)
            response_text = response_msg.content
        # print("*"*20 + "state 값 디버깅" + "*"*20)
        # for i, m in enumerate(result["messages"]):
        #     print("INDEX:", i)
        #     print("TYPE:", type(m))
        #     print("REPR:", repr(m))
        #     print("DICT:", m.model_dump() if hasattr(m, "model_dump") else m)
        # print("*"*60)
        print(f"Assistant: {response_text}\n") #H
        # print("*" * 55)
        # print(type(response_text))
        # print(response_text[0].get('text'))


#A Define the chat loop
#B Create a unique thread id
#C Check if the user input is "exit" or "quit" to exit the loop
#D Create the initial state with a HumanMessage containing the user input
#E Set the state with the HumanMessage
#F Invoke the graph with the state and the config
#G Get the last message from the result, which contains the final answer
#H Print the assistant's final answer, from the content of the last message

if __name__ == "__main__":
    chat_loop() 