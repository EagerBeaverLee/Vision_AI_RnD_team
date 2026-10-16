import asyncio
import json
import time
from typing import Any, List, Optional
import chainlit as cl

try:
    from langchain_core.agents import AgentAction, AgentFinish
except ImportError:
    AgentAction = AgentFinish = None
##########
class ChainlitCrewHandler:
    """CrewAI 실행 진행 상황을 단일 cl.Step 내부에 집약하여 제어하는 핸들러"""


    def __init__(self, root_step: cl.step):
        # 1. 최상위 루트 스텝
        self.root_step = root_step

        # 2. 계층별 활성 스텝 포인터
        self.current_agent_step: Optional[cl.Step] = None
        self.current_task_step: Optional[cl.Step] = None
        self.current_tool_step: Optional[cl.Step] = None
    
    # =========================================================================
    # [Agent 관련 함수 - 3개] (Parent: root_step)
    # =========================================================================

    def on_agent_start(self, agent_name: str, agent_role: str):
        """1. Agent 실행 시작: Root 스텝 하위에 Agent 전용 스텝 생성"""
        self.current_agent_step = cl.Step(
            name=f"🤖 [Agent 시작] {agent_name}",
            type="run",
            parent_id=self.root_step.id
        )
        self.current_agent_step.output = f"**담당 역할**: {agent_role}"
        cl.run_sync(self.current_agent_step.send())

    def on_agent_progress(self, agent_name: str, status_desc: str = "상황 분석 및 작업 계획 수립 중"):
        """2. Agent 실행 중: 현재 에이전트 스텝 제목 갱신"""
        if self.current_agent_step:
            self.current_agent_step.name = f"🧠 [Agent 분석 중] {agent_name}: {status_desc}"
            cl.run_sync(self.current_agent_step.update())

    def on_agent_complete(self, agent_name: str):
        """3. Agent 실행 완료: 에이전트 스텝 마감 및 포인터 초기화"""
        if self.current_agent_step:
            self.current_agent_step.name = f"✨ [Agent 완료] {agent_name}"
            cl.run_sync(self.current_agent_step.update())
            self.current_agent_step = None

    # =========================================================================
    # [Task 관련 함수 - 4개] (Parent: current_agent_step)
    # =========================================================================

    def on_task_start(self, task_name: str, task_desc: str = ""):
        """4. Task 실행 시작: 활성화된 Agent 스텝 하위에 Task 스텝 생성"""
        short_desc = self._extract_short_desc(task_desc)
        # 활성 Agent가 있으면 Agent 아래로, 없으면 Root 아래로 연결
        parent_id = self.current_agent_step.id if self.current_agent_step else self.root_step.id

        label = f"📋 [Task 착수] {task_name}"
        if short_desc:
            label += f" | {short_desc[:25]}..."

        self.current_task_step = cl.Step(
            name=label,
            type="run",
            parent_id=parent_id
        )
        if short_desc:
            self.current_task_step.output = f"> 📝 **지침**: {short_desc}"

        cl.run_sync(self.current_task_step.send())

    def on_task_progress(self, task_name: str, status_desc: str = "중간 결과 도출 및 적합성 검증 중"):
        """5. Task 실행 중: Task 스텝 제목 갱신"""
        if self.current_task_step:
            self.current_task_step.name = f"⏳ [Task 진행 중] {task_name}: {status_desc}"
            cl.run_sync(self.current_task_step.update())

    def on_task_complete(self, task_name: str):
        """6. Task 실행 완료: Task 상태를 완료로 전환"""
        if self.current_task_step:
            self.current_task_step.name = f"✔ [Task 완료] {task_name}"
            cl.run_sync(self.current_task_step.update())

    def on_task_result(self, task_name: str, result: Any):
        """7. Task 실행 결과: 산출물을 Task 아코디언 본문에 기록 후 포인터 초기화"""
        if self.current_task_step:
            parsed_result = self._parse_structured_output(result)
            prev_output = self.current_task_step.output or ""
            
            self.current_task_step.name = f"📊 [Task 완료] {task_name}"
            self.current_task_step.output = f"{prev_output}\n\n#### 📊 산출 결과\n{parsed_result}"
            cl.run_sync(self.current_task_step.update())
            
            # 태스크 완료 시 포인터 해제
            self.current_task_step = None

    # =========================================================================
    # [Tool 관련 함수 - 3개 (+완료 보조)] (Parent: current_task_step)
    # =========================================================================

    def on_tool_start(self, tool_name: str, tool_desc: str = "", tool_input: Any = None):
        """8. Tool 실행 시작: 현재 활성화된 Task 하위에 독립 Tool 스텝 생성"""
        # Task -> Agent -> Root 순으로 상위 부모 자동 탐색
        parent_id = (
            self.current_task_step.id if self.current_task_step
            else (self.current_agent_step.id if self.current_agent_step else self.root_step.id)
        )

        formatted_input = ""
        if tool_input:
            formatted_input = json.dumps(tool_input, ensure_ascii=False, indent=2) if isinstance(tool_input, dict) else str(tool_input)

        self.current_tool_step = cl.Step(
            name=f"🛠️ [Tool 호출] {tool_name}",
            type="tool",
            parent_id=parent_id
        )
        self.current_tool_step.output = (
            f"**목적**: {tool_desc if tool_desc else '지정 연산 수행'}\n\n"
            f"```json\n# Input Data\n{formatted_input if formatted_input else 'None'}\n```"
        )
        cl.run_sync(self.current_tool_step.send())

    def on_tool_progress(self, tool_name: str, status_desc: str = "연산 수행 및 외부 데이터 수집 중"):
        """9. Tool 실행 중: Tool 스텝 상태 갱신"""
        if self.current_tool_step:
            self.current_tool_step.name = f"⚙️ [Tool 연동 중] {tool_name}: {status_desc}"
            cl.run_sync(self.current_tool_step.update())

    def on_tool_result(self, tool_name: str, tool_output: Any):
        """10. Tool 실행 결과 수신: Tool 아코디언에 결과 데이터 바인딩 후 포인터 마감"""
        if self.current_tool_step:
            output_str = (
                json.dumps(tool_output, ensure_ascii=False, indent=2)
                if isinstance(tool_output, (dict, list))
                else str(tool_output)
            )

            prev_content = self.current_tool_step.output or ""
            self.current_tool_step.name = f"✅ [Tool 완료] {tool_name}"
            self.current_tool_step.output = f"{prev_content}\n\n```json\n# Output Data\n{output_str.strip()}\n```"
            
            cl.run_sync(self.current_tool_step.update())
            # 툴 완료 시 포인터 해제
            # self.current_tool_step = None

    def on_tool_complete(self, tool_name: str):
        """(보조) Tool 단순 완료 시: 결과 전달 없이 상태만 완료로 닫을 때 사용"""
        if self.current_tool_step:
            self.current_tool_step.name = f"✅ [Tool 완료] {tool_name}"
            cl.run_sync(self.current_tool_step.update())


    # def update_step_status(self, type_str: str = None, icon: str = None, name: str = None, output: str = None, delay: float = 1.0):
    #     """Chainlit Step UI 상태(아이콘, 타입, 제목)를 실시간 업데이트"""
    #     if type_str is not None:
    #         self.step.type = type_str
    #     if icon is not None:
    #         self.step.icon = icon
    #     if name is not None:
    #         self.step.name = name
    #     if output is not None:
    #         self.step.output = output

    #     if self.logs_history:
    #         self.step.output = "\n\n".join(self.logs_history)

    #     cl.run_sync(self.step.update())

    #     if delay > 0:
    #         time.sleep(delay)

    def agent_step_callback(self, agent_output: Any):
        """에이전트의 현재 동작 상태에 맞춰 Step의 제목과 아이콘을 동적으로 변경하고 내역을 누적"""
        log_text = getattr(agent_output, 'log', str(agent_output))
        tool_name = getattr(agent_output, 'tool', None)
        tool_input = getattr(agent_output, 'tool_input', None)
        log_lower = log_text.lower()
        obj_str = str(agent_output)
        
        # -------------------------------------------------------------
        # 1. AgentFinish 감지: 최종 답변 단계인 경우 logs_history에 넣지 않음
        # -------------------------------------------------------------
        is_finish = False
        type_name = type(agent_output).__name__
        output_data = None

        # (1) 클래스명에 'AgentFinish'가 포함된 경우 (모든 라이브러리 변종 대응)
        if "AgentFinish" in type_name:
            is_finish = True

        # (2) 최종 답변 고유 속성을 가지고 있는 경우
        elif hasattr(agent_output, 'return_values') or hasattr(agent_output, 'needed_categories'):
            is_finish = True

        # (3) 문자열 덤프에 AgentFinish / final_answer 문구가 포함된 경우 (Tool 사용 중이 아닐 때)
        elif not tool_name and (
            obj_str.startswith("AgentFinish") 
            or "AgentFinish(" in obj_str 
            or "final_answer" in obj_str.lower() 
            or "final answer:" in log_lower
        ):
            is_finish = True

        # 🛑 AgentFinish 감지 시: logs_history에 전혀 추가하지 않고 스텝 제목만 마감 후 종료
        if is_finish:
            output_data = None
            if hasattr(agent_output, 'return_values'):
                ret_val = getattr(agent_output, 'return_values')
                output_data = ret_val.get('output', str(ret_val)) if isinstance(ret_val, dict) else str(ret_val)
            elif hasattr(agent_output, 'output'):
                output_data = getattr(agent_output, 'output')
            else:
                output_data = obj_str

            parsed_text = self._parse_structured_output(output_data or log_text)
            short_desc = parsed_text.replace('\n', ' ')[:50]
            
            # 스텝 UI만 완료 상태로 갱신하고 logs_history.append() 없이 바로 return!
            # self.update_step_status("sparkles", "llm", f"🤖 [판단 완료] {short_desc}...", delay=0)
            return

        # -------------------------------------------------------------
        # 2. Tool 실행 감지
        # -------------------------------------------------------------
        if tool_name or "action:" in log_lower or "tool:" in log_lower:
            name_str = tool_name if tool_name else "외부 도구"
            formatted_input = ""
            if tool_input:
                formatted_input = json.dumps(tool_input, ensure_ascii=False, indent=2) if isinstance(tool_input, dict) else str(tool_input)

            clean_log = log_text.strip()
            # self.logs_history.append(
            #     f"#### 🛠️ Tool 실행: `{name_str}`\n"
            #     f"```json\n# Tool Input\n{formatted_input if formatted_input else '입력값 없음'}\n```\n"
            #     f"<details>\n<summary>🔍 Raw Log</summary>\n\n```text\n{clean_log}\n```\n</details>\n"
            # )
            # self.update_step_status("wrench", "tool", f"🛠️ [도구 실행 중] {name_str}", delay=2)

        # -------------------------------------------------------------
        # 3. Vector / DB / Retrieval 감지
        # -------------------------------------------------------------
        elif any(k in log_lower for k in ["search", "vector", "embed", "retriev", "rag", "database"]):
            # self.logs_history.append(f"#### 📚 DB/지식 검색\n```text\n{log_text.strip()}\n```\n")
            # self.update_step_status("database", "retrieval", "📚 [지식 검색 중] 전장 데이터 수집", delay=2)
            return

        # -------------------------------------------------------------
        # 4. 순수 사고 과정 (Thought) - AgentFinish가 완벽히 필터링된 후만 진입
        # -------------------------------------------------------------
        else:
            thought_line = ""
            for line in log_text.split("\n"):
                line_str = line.strip()
                if line_str.startswith("Thought:"):
                    thought_line = line_str.replace("Thought:", "").strip()
                    break

            desc = (thought_line[:45] + "...") if thought_line else "답변 구상 및 상황 분석 중..."
            # self.logs_history.append(f"#### 💡 사고 과정 (Thought)\n{log_text.strip()}\n")
            # self.update_step_status("brain", "llm", f"🧠 [분석 중] {desc}", delay=2)
        
    def task_callback(self, task_output: Any):
        """Task 완료 시 해당 실행 지침과 결과물을 히스토리 버퍼에 저장"""
        # 1. Task 이름 추출 (name -> description 순 탐색)
        task_name = getattr(task_output, 'name', None)
        task_desc = getattr(task_output, 'description', '설명 없음')

        # 첫 번째 마침표까지 잘라내어 간결한 설명으로 사용
        short_desc = self._extract_short_desc(task_desc)
        
        if not task_name:
            # name 속성이 없을 경우 description의 첫 줄을 태스크 이름으로 사용
            raw_desc = getattr(task_output, 'description', '')
            task_name = raw_desc.split('\n')[0][:40] if raw_desc else "태스크 완료"

        agent_role = getattr(task_output, 'agent', 'Agent')
        raw_output = getattr(task_output, 'raw', str(task_output))

        # 2. 결과물 정제 (Pydantic/JSON 파싱)
        parsed_result = self._parse_structured_output(raw_output)

        # 3. 아코디언 내역에 Task 이름 명시적 기록
        # self.logs_history.append(
        #     f"\n---\n#### 📌 [Task Complete] `{task_name}`\n"
        #     f"* **담당 에이전트**: `{agent_role}`\n\n"
        #     f"{parsed_result}\n"
        # )

        # 4. Chainlit UI 상단 라벨에 Task 이름 실시간 적용
        # self.update_step_status("check", "run", f"✔ [Task Complete] {task_name} | {short_desc}...", delay=2)

    def _extract_short_desc(self, text: str) -> str:
        """첫 번째 마침표까지 안전하게 잘라내기"""
        if not text:
            return ""
        if '.' in text:
            return text.split('.', 1)[0].strip() + '.'
        return text.strip()
    
    def _parse_structured_output(self, raw_data: Any) -> str:
        """str() 변환 전 Pydantic 객체, dict, JSON에서 needed_categories와 rationale을 직접 추출"""
        categories = None
        rationale = None

        # 0. CrewOutput / TaskOutput 인스턴스인 경우 내부 pydantic 객체나 json_dict 우선 참조
        if hasattr(raw_data, 'pydantic') and raw_data.pydantic:
            raw_data = raw_data.pydantic
        elif hasattr(raw_data, 'json_dict') and raw_data.json_dict:
            raw_data = raw_data.json_dict

        # 1. Pydantic BaseModel 인스턴스 형태 (속성으로 직접 접근)
        if hasattr(raw_data, 'needed_categories'):
            categories = getattr(raw_data, 'needed_categories', None)
            rationale = getattr(raw_data, 'rationale', None)

        # 2. Dictionary 형태인 경우
        elif isinstance(raw_data, dict):
            categories = raw_data.get('needed_categories')
            rationale = raw_data.get('rationale')

        # 3. JSON 문자열 형태인 경우 (json.loads 사용)
        elif isinstance(raw_data, str):
            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    categories = parsed.get('needed_categories')
                    rationale = parsed.get('rationale')
            except Exception:
                pass

        # 💡 needed_categories 항목을 정상적으로 찾은 경우 포맷팅 후 반환
        if categories is not None:
            if isinstance(categories, list):
                cats_str = ", ".join(categories) if categories else "선택된 카테고리 없음"
            else:
                cats_str = str(categories)
            
            rat_str = rationale if rationale else "사유 미기재"
            return f"* **선택 카테고리**: `{cats_str}`\n* **판단 사유**: {rat_str}"

        # 일반 마크다운/텍스트 결과물인 경우 그대로 출력
        return str(raw_data)

    def finish_main_step(self):
        """Crew 종료 후 메인 Step의 이름을 마감하고, 누적된 전체 로그를 output(드롭다운)에 연결"""
        # self.update_step_status(
        #     name = "✅ [Workflow 완료] 에이전트 상세 작업 내역 보기 (클릭)",
        #     # output = "\n\n".join(self.logs_history) if self.logs_history else "상세 실행 로그가 존재하지 않습니다."
        # )

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