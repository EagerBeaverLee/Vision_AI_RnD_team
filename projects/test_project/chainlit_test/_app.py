import os
import chainlit as cl
from crewai import Agent, Task, Crew, Process, LLM
# from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# 1. 실시간 로그 스트리밍을 위한 Callback 함수 정의
def agent_step_callback(agent_output):
    """
    각 에이전트가 생각(Thought)이나 도구(Tool) 사용을 마칠 때마다 호출됩니다.
    CrewAI 내부적으로는 동기(Sync)로 실행되므로 Chainlit의 cl.run_sync()를 사용합니다.
    """
    # agent_output에서 로그 텍스트 추출 (CrewAI 버전에 따라 객체 속성이 다를 수 있음)
    log = getattr(agent_output, 'log', str(agent_output))
    
    # Chainlit UI에 실시간 메시지로 출력
    cl.run_sync(
        cl.Message(
            content=f"🧠 **에이전트 진행 상황:**\n```text\n{log}\n```",
        ).send()
    )


# 2. Chainlit 채팅 시작 시 초기화
@cl.on_chat_start
async def start():
    await cl.Message(
        content="👋 안녕하세요! 조사하고 싶은 주제를 입력하면 AI 크루가 작업을 시작합니다."
    ).send()


# 3. 사용자 메시지 입력 시 CrewAI 실행
@cl.on_message
async def run_crew(message: cl.Message):
    topic = message.content

    # Gemini 스타일의 실시간 상태 업데이트용 메시지 선언
    status_msg = cl.Message(content="✨ **[Workflow]** AI 크루를 소환하는 중...")
    await status_msg.send()

    # Step Callback: 새로운 메시지를 쌓지 않고 기존 status_msg를 '업데이트'
    def agent_step_callback(agent_output):
        # agent_output에서 최신 로그/생각 추출
        log_text = getattr(agent_output, 'log', str(agent_output))
        
        # 로그에서 핵심 문구(Thought/Action) 한 줄만 깔끔하게 정제
        current_action = "작업 단계를 분석하고 있습니다..."
        for line in log_text.split('\n'):
            line = line.strip()
            if line.startswith("Thought:") or line.startswith("Action:"):
                current_action = line.replace("Thought:", "").replace("Action:", "").strip()
                break
            elif line and not line.startswith("Entering") and len(line) > 5:
                current_action = line[:60] + "..."

        # 텍스트를 교체하고 update() 호출 (Gemini 스타일 Fade/Update 효과)
        status_msg.content = f"⚡ **[Workflow 진행 중]**\n> _{current_action}_"
        cl.run_sync(status_msg.update())

    
    # LLM 설정 (langchain_openai)
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    # llm = LLM(model="gpt-4o-mini", temperature=0.7)
    llm = LLM(
        api_key="ai",
        model="hosted_vllm/openai/gpt-oss-20b",
        base_url="http://192.168.0.110:8000/v1"
    )

    # ==========================================
    # 에이전트 (Agents) 정의
    # ==========================================
    researcher = Agent(
        role="수석 연구원",
        goal=f"'{topic}'에 대한 최신 트렌드와 핵심 정보를 빠르고 정확하게 조사합니다.",
        backstory="당신은 기술 및 시장 분석에 능통한 수석 리서치 전문가입니다.",
        verbose=True,
        llm=llm,
        step_callback=agent_step_callback  # <-- 콜백 연결
    )

    writer = Agent(
        role="수석 기술 작가",
        goal="연구원이 조사한 내용을 바탕으로 이해하기 쉽고 매력적인 요약 보고서를 작성합니다.",
        backstory="복잡한 정보를 일반인도 직관적으로 이해할 수 있게 설명하는 능력을 가진 작가입니다.",
        verbose=True,
        llm=llm,
        step_callback=agent_step_callback  # <-- 콜백 연결
    )

    # ==========================================
    # 태스크 (Tasks) 정의
    # ==========================================
    research_task = Task(
        description=f"'{topic}'에 대해 상세히 조사하고 주요 핵심 사항 3가지를 정리하세요.",
        expected_output="3가지 주요 발견 사항이 포함된 리서치 노트",
        agent=researcher
    )

    write_task = Task(
        description="조사된 내용을 바탕으로 서론, 본론, 결론 구조를 갖춘 깔끔한 마크다운 형식의 리포트를 작성하세요.",
        expected_output="마크다운 형식의 최종 보고서",
        agent=writer
    )

    # ==========================================
    # 크루 (Crew) 구성
    # ==========================================
    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential
    )

    # UI 상에서 작업 상태를 보여주는 "Step" 로딩 UI 표시
    async with cl.Step(name="🚀 CrewAI 작업 진행 중...", type="run") as step:
        step.input = topic
        
        # CrewAI 비동기 실행 (kickoff_async)
        result = await crew.kickoff_async()
        
        step.output = "작업 완료!"

    # 4. 최종 결과 출력
    final_output = getattr(result, 'raw', str(result)) # 최신 버전에 맞춘 결과 추출
    await cl.Message(
        content=f"## 📊 최종 보고서\n\n{final_output}"
    ).send()