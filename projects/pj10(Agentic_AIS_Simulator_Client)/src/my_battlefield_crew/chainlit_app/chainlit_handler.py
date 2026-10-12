import asyncio
import json
import re
from typing import Any, List
import chainlit as cl

try:
    from langchain_core.agents import AgentAction, AgentFinish
except ImportError:
    AgentAction = AgentFinish = None

class ChainlitCrewHandler:
    """CrewAI 실행 진행 상황을 단일 cl.Step 내부에 집약하여 제어하는 핸들러"""

    def __init__(self, step: cl.step):
        self.step = step
        self.logs_history: List[str] = []

    def agent_step_callback(self, agent_output: Any):
        # -------------------------------------------------------------
        # 1. AgentFinish 감지: 최종 답변 단계인 경우 logs_history에 넣지 않음
        # -------------------------------------------------------------
        is_finish = False
        if AgentFinish and isinstance(agent_output, AgentFinish):
            is_finish = True
        elif hasattr(agent_output, 'return_values') or "final_answer" in str(agent_output).lower():
            is_finish = True

        if is_finish:
            # 스텝 제목만 마감 형태로 변경하고 과정 기록(logs_history)에는 추가하지 않음
            self.step.type = "llm"
            self.step.icon = "sparkles"
            self.step.name = "[COMPLETED] 최종 답변 작성 완료"
            cl.run_sync(self.step.update())
            return

        """에이전트의 현재 동작 상태에 맞춰 Step의 제목과 아이콘을 동적으로 변경하고 내역을 누적"""
        log_text = getattr(agent_output, 'log', str(agent_output))
        tool_name = getattr(agent_output, 'tool', None)
        tool_input = getattr(agent_output, 'tool_input', None)
        log_lower = log_text.lower()

        step_type = "run"
        step_icon = "brain"
        action_desc = "생각을 정리하고 있습니다..."

        # 1. Tool 실행 감지
        if tool_name or "action:" in log_lower or "tool:" in log_lower:
            step_type = "tool"
            step_icon = "wrench"
            name_str = tool_name if tool_name else "외부 도구"
            action_desc = f"도구 실행 중: {name_str}"

            formatted_input = ""
            if tool_input:
                if isinstance(tool_input, dict):
                    formatted_input = json.dumps(tool_input, ensure_ascii=False, indent=2)
                else:
                    formatted_input = str(tool_input)

            clean_log = log_text.strip()
            self.logs_history.append(
                f"#### 🛠️ Tool 실행: `{name_str}`\n"
                f"```json\n"
                f"# Tool Input\n"
                f"{formatted_input if formatted_input else '입력값 없음'}\n"
                f"```\n\n"
                f"<details>\n"
                f"<summary>🔍 Raw Agent Log 보기</summary>\n\n"
                f"```text\n"
                f"{clean_log}\n"
                f"```\n"
                f"</details>\n"
            )

        # 2. Vector / DB / Retrieval 감지
        elif any(k in log_lower for k in ["search", "vector", "embed", "retriev", "rag", "database"]):
            step_type = "retrieval"
            step_icon = "database"
            action_desc = "지식 베이스 검색 및 정보 수집 중..."

            clean_log = log_text.strip()
            self.logs_history.append(
                f"#### 📚 DB/지식 검색\n"
                f"```text\n"
                f"{clean_log}\n"
                f"```\n"
            )

        # 3. LLM 사고 과정 (Thought)
        else:
            step_type = "llm"
            step_icon = "sparkles"
            
            thought_line = ""
            for line in log_text.split("\n"):
                line_str = line.strip()
                if line_str.startswith("Thought:"):
                    thought_line = line_str.replace("Thought:", "").strip()
                    break

            action_desc = (thought_line[:50] + "...") if thought_line else "답변 구상 및 추론 중..."
            
            self.logs_history.append(
                f"#### 💡 사고 과정 (Thought)\n"
                f"{log_text.strip()}\n"
            )
            
        # -------------------------------------------------------------
        # UI 타이틀 및 아이콘 실시간 Fade 업데이트
        # -------------------------------------------------------------
        self.step.type = step_type
        self.step.icon = step_icon
        self.step.name = f"[{step_type.upper()}] {action_desc}"

        cl.run_sync(self.step.update())

    def task_callback(self, task_output: Any):
        """Task 완료 시 해당 실행 지침과 결과물을 히스토리 버퍼에 저장"""
        task_desc = getattr(task_output, 'description', '테스크 완료')
        raw_output = getattr(task_output, 'raw', str(task_output))
        agent_role = getattr(task_output, 'agent', 'Agent')

        # Pydantic/JSON 형태로 반환된 경우 final_answer만 정제해서 저장 가능
        clean_result = raw_output
        if "final_answer" in raw_output:
            try:
                parsed = json.loads(raw_output)
                if isinstance(parsed, dict) and "final_answer" in parsed:
                    clean_result = parsed["final_answer"]
            except Exception:
                pass

        self.logs_history.append(
            f"\n---\n📌 **[Task Complete]** {agent_role}\n"
            f"> **지시사항**: {task_desc[:100]}\n\n"
            f"```markdown\n"
            f"{clean_result}...\n"
            f"```\n"
        )
        if self.step:
            self.step.name = f"📌 [테스크 완료] {task_desc[:100]}..."
            cl.run_sync(self.step.update())

    def finish_main_step(self):
        """Crew 종료 후 메인 Step의 이름을 마감하고, 누적된 전체 로그를 output(드롭다운)에 연결"""
        self.step.name = "✅ [Workflow 완료] 에이전트 상세 작업 내역 보기 (클릭)"
        self.step.output = "\n\n".join(self.logs_history) if self.logs_history else "상세 실행 로그가 존재하지 않습니다."
        cl.run_sync(self.step.update())

    @staticmethod
    async def stream_final_response(final_text: str):
        """메인 대화창에는 오직 깔끔한 최종 결과만 타이핑 스트리밍 연출로 출력"""
        msg = cl.Message(content="")
        await msg.send()

        words = str(final_text).split(" ")
        for word in words:
            await msg.stream_token(word + " ")
            await asyncio.sleep(0.015)
        await msg.update()