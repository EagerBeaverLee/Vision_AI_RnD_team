import uuid
from typing import Literal
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

# ==========================================
# 1. 더미 툴(Dummy Tools) 정의
# ==========================================
@tool
def tool_weather() -> str:
    """현재 한반도의 평균 날씨(풍향, 풍속, 기온, 수온, 최대파고 등) 결과 값 반환"""
    print("\n" + "="*40)
    print(">>> 🛠️ [TOOL 실행] 한반도 평균 날씨 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return "날씨 분석 결과: 기온 20도, 파고 잔잔함."

@tool
def tool_target_ship_track(target_identifier: str) -> str:
    """선박의 이름 or mmsi를 명시했을 때 그 특정 선박에 대한 자세한 항적 정보 반환"""
    print("\n" + "="*40)
    print(f">>> 🛠️ [TOOL 실행] 특정 선박({target_identifier}) 항적 정보 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return f"{target_identifier} 선박 항적: 정상 운항 중."

@tool
def tool_fleet_od_flow() -> str:
    """현재 운항중인 전체 선박의 od flow 분석 된 결과를 반환"""
    print("\n" + "="*40)
    print(">>> 🛠️ [TOOL 실행] 전체 선박 OD Flow 분석 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return "OD Flow 결과: 부산항 방향 트래픽 증가."

@tool
def tool_fleet_density() -> str:
    """현재 운항중인 전체 선박의 구역별 밀집 현황 분석 결과 반환"""
    print("\n" + "="*40)
    print(">>> 🛠️ [TOOL 실행] 구역별 밀집 현황 분석 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return "밀집 현황: 남해안 구역 혼잡."

@tool
def tool_fleet_speed() -> str:
    """현재 운항중인 전체 선박의 구역별 이동속도 요약 결과 반환"""
    print("\n" + "="*40)
    print(">>> 🛠️ [TOOL 실행] 구역별 이동속도 요약 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return "이동속도 요약: 평균 15노트."

@tool
def tool_fleet_anomaly() -> str:
    """현재 운항중인 전체 선박 중 특이 기동 선박의 기동결과 및 선정 기준 반환"""
    print("\n" + "="*40)
    print(">>> 🛠️ [TOOL 실행] 특이 기동 선박 분석 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return "특이 기동 분석: 이상 징후 없음."

@tool
def tool_fleet_direction() -> str:
    """현재 운항중인 전체 선박이 8방위중에 어디로 이동중인지 분석 결과 반환"""
    print("\n" + "="*40)
    print(">>> 🛠️ [TOOL 실행] 8방위 이동 방향 분석 툴이 호출되었습니다!")
    print("="*40 + "\n")
    return "이동 방향: 북동쪽 이동 선박이 대다수."

# ==========================================
# 2. LLM 및 에이전트 셋업
# ==========================================
# 테스트를 위해 가볍고 빠른 모델을 추천합니다 (실제 적용 시 gpt-oss-20b 등으로 변경)
llm = ChatOpenAI(
    model="openai/gpt-oss-20b",
    api_key="ai",
    base_url="http://192.168.0.110:8000/v1",
)

# 전문가 에이전트 3명 생성 (각각 자신의 역할에 맞는 툴만 가집니다)
weather_agent = create_react_agent(llm, tools=[tool_weather])
target_ship_agent = create_react_agent(llm, tools=[tool_target_ship_track])
fleet_analytics_agent = create_react_agent(llm, tools=[
    tool_fleet_od_flow, 
    tool_fleet_density, 
    tool_fleet_speed, 
    tool_fleet_anomaly, 
    tool_fleet_direction
])

# ==========================================
# 3. 라우터(Router) 노드 정의
# ==========================================
# 라우터가 선택할 수 있는 목적지를 Pydantic으로 명확히 정의합니다.
class RouteDecision(BaseModel):
    destination: Literal["weather_agent", "target_ship_agent", "fleet_analytics_agent"] = Field(
        ...,
        description="사용자의 질문에 따라 적절한 에이전트를 선택하세요. 날씨=weather_agent, 특정선박=target_ship_agent, 전체선박통계=fleet_analytics_agent"
    )

# 라우터용 LLM (구조화된 출력 사용)
router_llm = llm.with_structured_output(RouteDecision)

def router_node(state: MessagesState) -> Command[Literal["weather_agent", "target_ship_agent", "fleet_analytics_agent"]]:
    """사용자의 마지막 메시지를 보고 알맞은 에이전트로 라우팅합니다."""
    messages = state["messages"]
    last_user_message = messages[-1].content
    
    print("\n[Router] 사용자 의도 분석 중...")
    
    # 라우팅 프롬프트
    sys_prompt = (
        "당신은 해상 트래픽 및 기상 정보 시스템의 라우터입니다. "
        "사용자의 질문을 분석하여 가장 적합한 에이전트로 연결하세요."
    )
    
    decision = router_llm.invoke([
        SystemMessage(content=sys_prompt),
        HumanMessage(content=last_user_message)
    ])
    
    print(f"[Router] 결정된 에이전트: {decision.destination}\n")
    
    # 선택된 에이전트로 상태를 업데이트하며 이동합니다.
    return Command(goto=decision.destination)

# ==========================================
# 4. LangGraph 조립 (Graph Construction)
# ==========================================
builder = StateGraph(MessagesState)

# 노드 추가 (라우터 및 3개의 전문가 에이전트)
builder.add_node("router", router_node)
builder.add_node("weather_agent", weather_agent)
builder.add_node("target_ship_agent", target_ship_agent)
builder.add_node("fleet_analytics_agent", fleet_analytics_agent)

# 엣지 연결: 시작하면 무조건 라우터로 갑니다.
builder.add_edge(START, "router")

# 각 워커 에이전트의 작업이 끝나면 대화(그래프)를 종료합니다.
builder.add_edge("weather_agent", END)
builder.add_edge("target_ship_agent", END)
builder.add_edge("fleet_analytics_agent", END)

# 그래프 컴파일
graph = builder.compile()

# ==========================================
# 5. 테스트를 위한 메인 채팅 루프
# ==========================================
def chat_loop():
    thread_id = uuid.uuid4()
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n🚀 [시스템 시작] 해상 트래픽 & 기상 테스트 봇 (종료하려면 'exit' 입력)")
    print("테스트 예시:")
    print(" 1. 오늘 한반도 날씨 어때?")
    print(" 2. 에버기븐호(MMSI 12345) 항적 정보 알려줘")
    print(" 3. 전체 선박 중에 특이 기동하는 배들 분석해줘\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            print("테스트를 종료합니다.")
            break
            
        if not user_input:
            continue
            
        state = {"messages": [HumanMessage(content=user_input)]}
        
        # 그래프 실행
        result = graph.invoke(state, config=config)
        
        # 결과 메시지 출력
        response_msg = result["messages"][-1]
        print(f"Assistant: {response_msg.content}\n")

if __name__ == "__main__":
    chat_loop()