import sys
from typing import Literal
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
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

# for tool in tools:
#     print(f"{tool.name}: {tool.description}\n")


get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
get_schema_node = ToolNode([get_schema_tool], name="get_schema")

run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
run_query_node = ToolNode([run_query_tool], name="run_query")


# Example: create a predetermined tool call
def list_tables(state: MessagesState):
    tool_call = {
        "name": "sql_db_list_tables",
        "args": {},
        "id": "abc123",
        "type": "tool_call",
    }
    tool_call_message = AIMessage(content="", tool_calls=[tool_call])

    list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
    tool_message = list_tables_tool.invoke(tool_call)
    response = AIMessage(f"Available tables: {tool_message.content}")

    return {"messages": [tool_call_message, tool_message, response]}


# Example: force a model to create a tool call
def call_get_schema(state: MessagesState):
    # Note that LangChain enforces that all models accept `tool_choice="any"`
    # as well as `tool_choice=<string name of tool>`.
    llm_with_tools = llm.bind_tools([get_schema_tool], tool_choice="any")
    response = llm_with_tools.invoke(state["messages"])

    return {"messages": [response]}


generate_query_system_prompt = """
    # Role
    You are an agent designed to interact with a SQL database.
    Given an input question, create a syntactically correct {dialect} query to run,
    then look at the results of the query and return the answer. Unless the user
    specifies a specific number of examples they wish to obtain, always limit your
    query to at least {top_k} results.

    # important Rules
    - You can order the results by a relevant column to return the most interesting
    examples in the database. Never query for all the columns from a specific table,
    only ask for the relevant columns given the question.

    - If you rewrite the query, please write it to accurately reflect the intent of the original question (e.g., do not omit other conditions such as [AND date LIKE '2025-07-06 10%'] when changing "Incheon seafront" to "Incheon").
    
    - When referencing the '지점명' column, be sure to refer to the following list to accurately write the query for the corresponding branch name.
      '지점명' 리스트: {zone_name}

    - Handling Time & Metrics: If the user's question asks to compare numerical metrics (e.g., temperature, wind speed) between locations/entities WITHOUT specifying a specific timestamp or time range, DO NOT fetch raw time-series rows. Instead, calculate the average value using `AVG()` grouped by the entity (or compare `AVG(metric)` between entities) to summarize the data

    - Date Filtering Rule: When filtering by specific dates (e.g., 'YYYY-MM-DD'), DO NOT use functions like `date(column) = 'YYYY-MM-DD'`. SQLite `date()` function returns NULL if format/whitespace varies slightly. ALWAYS use string pattern matching like `column LIKE 'YYYY-MM-DD%'` instead.

    - Numeric Type Casting: Columns storing numbers might be typed as TEXT. ALWAYS explicitly cast numerical columns using `CAST(column AS REAL)` inside aggregate functions (`MAX`, `MIN`, `AVG`) and arithmetic operations (e.g., `MAX(CAST(온도 AS REAL)) - MIN(CAST(온도 AS REAL))`) to prevent incorrect string-based comparisons.

    - If you cannot answer the question, you must use sql_db_query to get more information about question

    - When ordering by timestamp/time columns (일시), ALWAYS use ORDER BY datetime(column) instead of raw string ordering to ensure correct chronological sorting.

    - DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
""".format(
    dialect=db.dialect,
    top_k=5,
    zone_name=db.run("SELECT DISTINCT 지점명 from weather_data"),
)


def generate_query(state: MessagesState):
    
    system_message = {
        "role": "system",
        "content": generate_query_system_prompt,
    }
    # We do not force a tool call here, to allow the model to
    # respond naturally when it obtains the solution.
    llm_with_tools = llm.bind_tools([run_query_tool])
    response = llm_with_tools.invoke([system_message] + state["messages"])

    return {"messages": [response]}


check_query_system_prompt = """
    You are a SQL expert with a strong attention to detail.
    Double check the {dialect} query for common mistakes, including:
    - Using NOT IN with NULL values
    - Using UNION when UNION ALL should have been used
    - Using BETWEEN for exclusive ranges
    - Data type mismatch in predicates
    - Properly quoting identifiers
    - Using the correct number of arguments for functions
    - Casting to the correct data type
    - Using the proper columns for joins

    

    If there are any of the above mistakes, rewrite the query. If there are no mistakes,
    just reproduce the original query.

    You will call the appropriate tool to execute the query after running this check.
""".format(
    dialect=db.dialect
)


def check_query(state: MessagesState):
    system_message = {
        "role": "system",
        "content": check_query_system_prompt,
    }

    # Generate an artificial user message to check
    tool_call = state["messages"][-1].tool_calls[0]
    user_message = {"role": "user", "content": tool_call["args"]["query"]}
    llm_with_tools = llm.bind_tools([run_query_tool], tool_choice="any")
    response = llm_with_tools.invoke([system_message, user_message])
    response.id = state["messages"][-1].id

    return {"messages": [response]}

answer_system_prompt = """
    You are a helpful weather data assistant.
    Analyze the user's original question and the SQL query result provided in the messages.
    Provide a clear, natural, and polite answer in Korean.

    Guidelines:
    - Present numerical data clearly with proper units (e.g., ℃, m/s).
    - Summarize key insights (e.g., maximum/minimum differences, averages) if relevant.
    - Do NOT generate any SQL queries. Just answer the user in plain text.
"""

def generate_answer(state: MessagesState):
    system_message = {"role": "system", "content": answer_system_prompt}
    # 도구를 바인딩하지 않고 일반 LLM으로 호출하여 친절한 답변만 생성하게 함
    response = llm.invoke([system_message] + state["messages"])
    return {"messages": [response]}

def should_continue(state: MessagesState) -> Literal["check_query", "generate_query"]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "check_query"
    
    return "generate_query"

def route_after_run(state: MessagesState) -> Literal["generate_query", "generate_answer"]:
    messages = state["messages"]
    last_message = messages[-1] # run_query가 추가한 ToolMessage
    
    # ToolMessage 내용에 에러 문구가 포함되어 있다면 쿼리 다시 생성
    content = str(last_message.content).lower()
    if "error" in content or "exception" in content or "operationalerror" in content:
        return "generate_query"
    
    # 정상적으로 DB 결과를 받아왔다면 최종 답변 생성 노드로 이동
    return "generate_answer"


builder = StateGraph(MessagesState)
builder.add_node(list_tables)
builder.add_node(call_get_schema)
builder.add_node(get_schema_node, "get_schema")
builder.add_node(generate_query)
builder.add_node(check_query)
builder.add_node(run_query_node, "run_query")
builder.add_node(generate_answer)

builder.add_edge(START, "list_tables")
builder.add_edge("list_tables", "call_get_schema")
builder.add_edge("call_get_schema", "get_schema")
builder.add_edge("get_schema", "generate_query")
builder.add_conditional_edges(
    "generate_query",
    should_continue,
)
builder.add_edge("check_query", "run_query")
builder.add_conditional_edges("run_query", route_after_run)

builder.add_edge("generate_answer", END)

agent = builder.compile()

from IPython.display import Image, display
from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles

agent.get_graph().draw_mermaid_png(output_file_path="res.png")

param1 = None
if len(sys.argv) > 1:
    param1 = sys.argv[1]
    print(f"첫 번째 매개변수: {param1}")

# question = "2025년 5월 8일 오전 10시 기준 인천 앞바다의 수온은 기온보다 높게 기록되어 있나요?"
# question = "남해의 거제도와 서해의 덕적도 중 어느 해역의 풍속(바람)이 더 강하게 부나요?"
# question = "울릉도 해역과 동해 해역 중 어느 곳의 수온이 더 높나요?"
# question = "마라도와 추자도 부이의 기온 편차는 얼마나 발생하고 있나요?"
# question = "2025년 3월 8일 하루 동안 기온의 일교차(최고 기온 - 최저 기온)가 가장 컸던 지역은 어디인가요?"
# question = "기온과 수온의 차이(기온 - 수온)가 가장 크게 벌어진 지점과 시간은 언제인가요?"
# question = "인천, 풍도, 연평도 등 서해 중부 해역의 습도 상태를 볼 때 해무(바다 안개)가 발생할 가능성이 높나요?"
# question = "바람 방향(풍향)과 파도의 방향(파향)이 거의 일치하여 파도가 거세질 위험이 있는 지점은 어디인가요?"
# question = "최근 몇 시간 동안 기압이 급격히 떨어지면서 풍속이 강해지는 등 풍랑주의보 징후를 보이는 곳이 있나요?"
# question = "유의파고가 1.5m를 초과하여 소형 선박 운항이 위험할 것으로 예상되는 부이 목록을 중복 없이 5개정도 뽑아주세요"
# question = "전체 관측 데이터 중 수온이 가장 높게 기록된 곳의 지점명과 수온을 알려주세요."
# question = "동해57 부이의 기압 변화 추이를 알고 싶습니다. 기압이 계속 상승하고 있나요?"
# question = "25년 5월 3일 삼척 해역의 파주기(Wave Period)와 파향 상태를 알려주세요."

# question = "포항 앞바다의 습도가 가장 낮았던 시각은 몇 시인가요?"

for step in agent.stream(
    {"messages": [{"role": "user", "content": param1}]},
    stream_mode="values",
):
    step["messages"][-1].pretty_print()