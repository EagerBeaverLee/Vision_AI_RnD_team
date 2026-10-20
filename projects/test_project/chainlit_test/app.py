import os
import asyncio
import chainlit as cl
from crewai import Agent, Task, Crew, Process, LLM

os.environ["OPENAI_API_KEY"] = "sk-..."

@cl.on_chat_start
async def start():
    await cl.Message(
        content="👋 안녕하세요! 조사하고 싶은 주제를 입력하시면 AI 크루가 실시간으로 협업을 시작합니다."
    ).send()


@cl.on_message
async def run_crew(message: cl.Message):
    topic = message.content
    
    # 1. Step 객체를 외부 스코프에서 참조할 수 있도록 설정
    current_step = None

    # Agent 실행 단계별 Callback
    def agent_step_callback(agent_output):
        nonlocal current_step
        log_text = getattr(agent_output, 'log', str(agent_output))
        
        # Thought / Action 파싱
        current_action = "작업 단계를 수행 중입니다..."
        for line in log_text.split('\n'):
            line = line.strip()
            if line.startswith("Thought:") or line.startswith("Action:"):
                current_action = line.replace("Thought:", "").replace("Action:", "").strip()
                break

        # cl.Step의 이름을 직접 변경 후 update (Fade 효과 및 Spinner 유지)
        if current_step:
            current_step.name = f"🧠 {current_action}"
            cl.run_sync(current_step.update())

    # Task 완료시 Callback
    def task_callback(task_output):
        nonlocal current_step
        if current_step:
            # Task 완료 시 Step 이름 업데이트
            current_step.name = f"📌 [태스크 완료] {task_output.description[:30]}..."
            cl.run_sync(current_step.update())

    # ==========================================
    # CrewAI 구성
    # ==========================================
    # llm = LLM(model="gpt-4o-mini", temperature=0.7)
    llm = LLM(
        api_key="ai",
        model="hosted_vllm/openai/gpt-oss-20b",
        base_url="http://192.168.0.110:8000/v1"
    )

    researcher = Agent(
        role="수석 연구원",
        goal=f"'{topic}'에 대한 핵심 정보 조사",
        backstory="기술 및 시장 분석 전문가",
        verbose=True,
        llm=llm,
        step_callback=agent_step_callback
    )

    writer = Agent(
        role="수석 기술 작가",
        goal="이해하기 쉬운 요약 보고서 작성",
        backstory="전문 기술 작가",
        verbose=True,
        llm=llm,
        step_callback=agent_step_callback
    )

    research_task = Task(
        description=f"'{topic}'에 대해 상세히 조사하고 핵심 3가지를 정리하세요.",
        expected_output="3가지 주요 발견 사항",
        agent=researcher,
        callback=task_callback  # 태스크 콜백 추가
    )

    write_task = Task(
        description="조사된 내용을 바탕으로 서론/본론/결론이 있는 깔끔한 마크다운 리포트를 작성하세요.",
        expected_output="마크다운 보고서",
        agent=writer,
        callback=task_callback  # 태스크 콜백 추가
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential
    )

    # ==========================================
    # 2. cl.Step (Active 로딩 효과 + 실시간 문구 Fade 업데이트)
    # ==========================================
    async with cl.Step(name="🚀 [Workflow] CrewAI 실행 준비 중...", type="run") as step:
        current_step = step
        
        # 세부 진행상황 연출을 위한 단계적 업데이트 예시
        step.name = "🔍 [수석 연구원] 정보 수집 및 리서치 진행 중..."
        await step.update()

        # CrewAI 비동기 실행
        result = await crew.kickoff_async()

        step.name = "✅ [Workflow] 모든 에이전트의 작업이 완료되었습니다!"
        await step.update()

    # ==========================================
    # 3. 결과 리포트 실시간 토큰 스트리밍
    # ==========================================
    final_output = getattr(result, 'raw', str(result))

    # 빈 메시지 객체 생성 후 화면에 먼저 전달
    final_msg = cl.Message(content="")
    await final_msg.send()

    # 텍스트를 단어/문단 단위로 분할하여 실시간 타이핑(Streaming) 효과 연출
    words = final_output.split(" ")
    for word in words:
        await final_msg.stream_token(word + " ")
        await asyncio.sleep(0.015)  # 타이핑 속도 조절 (초 단위)

    # 최종 스트리밍 완료 업데이트
    await final_msg.update()