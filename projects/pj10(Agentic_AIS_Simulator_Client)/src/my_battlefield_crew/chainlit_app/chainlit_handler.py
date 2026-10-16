import asyncio
import json
import time
from typing import Any, List
import chainlit as cl

try:
    from langchain_core.agents import AgentAction, AgentFinish
except ImportError:
    AgentAction = AgentFinish = None
##########
class ChainlitCrewHandler:
    """CrewAI 실행 진행 상황을 단일 cl.Step 내부에 집약하여 제어하는 핸들러"""

    def __init__(self, step: cl.step):
        self.step = step
        self.logs_history: List[str] = []

    
    # =========================================================================
    # 💡 Crew에서 호출할 의미 기반(Semantic) 메서드
    # [1~3] Agent Lifecycle
    # =========================================================================

    def on_agent_start(self, agent_name: str, agent_role: str, delay=1.0):
        """1. Agent 실행 시작"""
        label = f"[Agent 시작] {agent_name} ({agent_role})"
        self.logs_history.append(f"\n---\n"+ f"#### 🤖 [Agent 시작]: `{agent_name}`\n* **역할(Role)**: {agent_role}\n")
        self.update_step_status(icon="bot", type_str="llm", name=label, delay=delay)

    def on_agent_progress(self, agent_name: str, status_desc: str = "상황 분석 및 작업 계획 수립 중", delay=1.0):
        """2. Agent 실행 중"""
        label = f"[Agent 분석 중] {agent_name}: {status_desc}"
        self.logs_history.append(f"\n---\n"+ f"🧠 " + label + "\n")
        self.update_step_status(icon="brain", type_str="llm", name=label, delay=delay)

    def on_agent_complete(self, agent_name: str, agent_role: str = "", delay=1.0):
        """3. Agent 실행 완료"""
        label = f"[Agent 완료] {agent_name}**역할(Role)**: {agent_role}"
        self.logs_history.append(f"\n---\n"+ f"#### ✨ [Agent 완료]: **`{agent_name}`**\n")
        self.update_step_status(icon="sparkles", type_str="llm", name=label, delay=delay)

    # =========================================================================
    # [4~7] Task Lifecycle
    # =========================================================================

    def on_task_start(self, task_name: str, task_desc: str = "", delay=1.0):
        """4. Task 실행 시작"""
        short_desc = self._extract_short_desc(task_desc)
        label = f"[Task 시작] {task_name}"
        if short_desc:
            label += f" | {short_desc[:25]}..."

        self.logs_history.append(
            f"\n---\n#### 📋 [Task 시작] `{task_name}`\n"
            f"* **지침**: {short_desc if short_desc else '세부 지침 없음'}\n"
        )
        self.update_step_status(icon="list-todo", type_str="run", name=label, delay=delay)

    def on_task_progress(self, task_name: str, status_desc: str = "중간 결과 도출 및 적합성 검증 중", delay=1.0):
        """5. Task 실행 중"""
        label = f"[Task 진행 중] {task_name}: {status_desc}"
        self.logs_history.append(f"\n---\n"+ f"⏳ " + label + "\n")
        self.update_step_status(icon="loader", type_str="run", name=label, delay=delay)

    def on_task_complete(self, task_name: str, delay=1.0):
        """6. Task 실행 완료"""
        label = f"[Task 완료] {task_name}"
        self.logs_history.append(f"\n---\n"+ f"☑️ " + label + "\n")
        self.update_step_status(icon="list-checks", type_str="run", name=label, delay=delay)

    def on_task_result(self, task_name: str, result: Any, delay=1.0):
        """7. Task 실행 결과 기록"""
        parsed_result = self._parse_structured_output(result)
        self.logs_history.append(
            f"\n---\n#### 📊 [Task 결과] `{task_name}` 실행 결과\n"
            f"{parsed_result}\n"
        )
        label = f"[Task 결과 도출] {task_name}"
        self.update_step_status(icon="file-text", type_str="run", name=label, delay=delay)

    # =========================================================================
    # [8~11] Tool Lifecycle
    # =========================================================================

    def on_tool_start(self, tool_name: str, tool_desc: str = "", tool_input: Any = None, delay=1.0):
        """8. Tool 실행 시작"""
        formatted_input = ""
        if tool_input:
            formatted_input = json.dumps(tool_input, ensure_ascii=False, indent=2) if isinstance(tool_input, dict) else str(tool_input)

        log_message = f"\n---\n#### 🛠️ 도구 호출: `{tool_name}`\n" + f"* **목적**: {tool_desc if tool_desc else '지정 작업 수행'}\n"

        if formatted_input:
            log_message += f"```json\n# Input Data\n{formatted_input}\n"
            
        self.logs_history.append(
            log_message
        )
        label = f"[Tool 호출] {tool_name}"
        self.update_step_status(icon="wrench", type_str="tool", name=label, delay=delay)

    def on_tool_progress(self, tool_name: str, status_desc: str = "외부 리소스 조회 및 데이터 패치 중", delay=1.0):
        """9. Tool 실행 중"""
        label = f"[Tool 실행 중] {tool_name}: {status_desc}"
        self.logs_history.append(f"\n---\n"+ f"⚙️ " + label + "\n")
        self.update_step_status(icon="file-cog", type_str="tool", name=label, delay=delay)

    def on_tool_complete(self, tool_name: str, delay=1.0):
        """10. Tool 실행 완료"""
        label = f"[Tool 완료] {tool_name}"
        self.logs_history.append(f"\n---\n"+ f"✅ " + label + "\n")
        self.update_step_status(icon="square-check", type_str="tool", name=label, delay=delay)

    def on_tool_result(self, tool_name: str, delay=1.0):
        # 아코디언 내 접이식 블록으로 긴 Tool 결과 출력
        label = f"[Tool 결과 수신] {tool_name}"
        self.logs_history.append(f"\n---\n"+ f"📦 "+ label + "\n")
        self.update_step_status(icon="check-check", type_str="tool", name=label, delay=delay)

    def update_step_status(self, type_str: str = None, icon: str = None, name: str = None, output: str = None, delay: float = 1.0):
        """Chainlit Step UI 상태(아이콘, 타입, 제목)를 실시간 업데이트"""
        if type_str is not None:
            self.step.type = type_str
        if icon is not None:
            self.step.icon = icon
        if name is not None:
            self.step.name = name
        if output is not None:
            self.step.output = output

        if self.logs_history:
            self.step.output = "\n\n".join(self.logs_history)

        cl.run_sync(self.step.update())

        if delay is not None and delay > 0:
            time.sleep(delay)

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
            self.update_step_status("brain-circuit", "llm", f"🤖 [판단 완료] {short_desc}...", delay=0)
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
            self.logs_history.append(
                f"#### 🛠️ Tool 실행: `{name_str}`\n"
                f"```json\n# Tool Input\n{formatted_input if formatted_input else '입력값 없음'}\n```\n"
                f"<details>\n<summary>🔍 Raw Log</summary>\n\n```text\n{clean_log}\n```\n</details>\n"
            )
            self.update_step_status("tool", "wrench", f"🛠️ [도구 실행 중] {name_str}", delay=2)

        # -------------------------------------------------------------
        # 3. Vector / DB / Retrieval 감지
        # -------------------------------------------------------------
        elif any(k in log_lower for k in ["search", "vector", "embed", "retriev", "rag", "database"]):
            self.logs_history.append(f"#### 📚 DB/지식 검색\n```text\n{log_text.strip()}\n```\n")
            self.update_step_status("retrieval", "database", "📚 [지식 검색 중] 전장 데이터 수집", delay=2)

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
            self.logs_history.append(f"#### 💡 사고 과정 (Thought)\n{log_text.strip()}\n")
            self.update_step_status("llm", "brain-cog", f"🧠 [분석 중] {desc}", delay=2)
        
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

        # 4. Chainlit UI 상단 라벨에 Task 이름 실시간 적용
        self.update_step_status(type_str="run", icon="check-line", name=f"[Task Complete] {task_name} | {short_desc}...", delay=2)

    def _extract_short_desc(self, text: str) -> str:
        """첫 번째 마침표까지 안전하게 잘라내기"""
        if not text:
            return ""
        if '.' in text:
            return text.split('.', 1)[0].strip() + '.'
        return text.strip()
    
    def _parse_structured_output(self, raw_data: Any) -> str:
        """Pydantic / dict / JSON 객체를 동적으로 분석하여 비어있지 않은 모든 필드를 마크다운으로 포맷팅"""
        data_dict = None

        # 1. CrewAI TaskOutput 내부 Pydantic/JSON 객체 추출
        if hasattr(raw_data, 'pydantic') and raw_data.pydantic:
            raw_data = raw_data.pydantic
        elif hasattr(raw_data, 'json_dict') and raw_data.json_dict:
            data_dict = raw_data.json_dict

        # 2. Pydantic 모델을 딕셔너리로 변환 (Pydantic V2 및 V1 호환)
        if hasattr(raw_data, 'model_dump'):  # Pydantic v2
            data_dict = raw_data.model_dump()
        elif hasattr(raw_data, 'dict') and callable(getattr(raw_data, 'dict')):  # Pydantic v1
            data_dict = raw_data.dict()
        elif isinstance(raw_data, dict):
            data_dict = raw_data
        elif isinstance(raw_data, str):
            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    data_dict = parsed
            except Exception:
                pass

        # 3. 딕셔너리로 추출된 경우 동적 계층 포맷터 실행
        if isinstance(data_dict, dict):
            return self._format_dict_to_markdown(data_dict)

        # 4. 그 외 일반 문자열/스칼라 데이터
        return str(raw_data).strip()

    def _is_empty(self, val: Any) -> bool:
        """빈 값 검사 (0이나 False는 의미 있는 데이터이므로 제외하지 않음)"""
        if val is None:
            return True
        if isinstance(val, (str, list, dict, set, tuple)) and len(val) == 0:
            return True
        return False

    def _format_dict_to_markdown(self, data: dict, depth: int = 0) -> str:
        """딕셔너리 내부의 모든 필드를 마크다운 트리 구조로 변환"""
        # 자주 쓰이는 필드명에 대한 한글 라벨 맵핑 (선택 사항)
        field_labels = {
            "needed_categories": "선택 카테고리",
            "rationale": "판단 사유",
            "final_answer": "최종 분석 답변",
            "cluster_density": "정박 밀집도",
            "mean_speed": "평균 항해 속력",
            "traffic_flow": "교통 흐름",
            "unusual_ships": "특이 기동 선박"
        }

        indent = "  " * depth
        lines = []

        for key, val in data.items():
            # 빈 항목은 스킵
            if self._is_empty(val):
                continue

            # 라벨 이름 설정 (사전에 정의된 이름이 있으면 한글 표기 병기)
            display_name = f"**{field_labels[key]}** (`{key}`)" if key in field_labels else f"**`{key}`**"

            if isinstance(val, (dict, list)):
                lines.append(f"{indent}* {display_name}:\n")
                output_str = (
                    json.dumps(val, ensure_ascii=False, indent=2) 
                    if isinstance(val, (dict, list)) 
                    else str(val)
                )
                lines.append(f"```json\n{output_str.strip() if output_str else '파라미터 없음'}\n```\n")

            elif isinstance(val, str) and "```" in val:
                lines.append(f"{indent}* {display_name}:")
                lines.append(f"{val.strip()}\n")  # 추가 백틱 없이 원문 그대로 출력

            elif isinstance(val, str) and ("\n" in val or len(val) > 70):
                quote_block = val.strip().replace("\n", f"\n{indent}  > ")
                lines.append(f"{indent}* {display_name}:\n{indent}  > {quote_block}")

            # # A. 중첩 딕셔너리 (하위 객체)
            # if isinstance(val, dict):
            #     lines.append(f"{indent}* {display_name}:")
            #     sub_content = self._format_dict_to_markdown(val, depth + 1)
            #     lines.append(sub_content)

            # # B. 리스트 형태
            # elif isinstance(val, list):
            #     # B-1. 문자열/숫자 등 단순 값 목록인 경우
            #     if all(not isinstance(item, (dict, list)) for item in val):
            #         lines.append(f"{indent}* {display_name}: [{items_str}]")
            #         items_str = ", ".join(f"`{item}`" if isinstance(item, str) else str(item) for item in val)
            #     # B-2. 리스트 안에 딕셔너리(객체)가 들어있는 경우 (예: 관측된 선박 목록 등)
            #     else:
            #         lines.append(f"{indent}* {display_name} (총 {len(val)}건):")
            #         for idx, item in enumerate(val, 1):
            #             if isinstance(item, dict):
            #                 sub_items = [f"`{k}`: {v}" for k, v in item.items() if not self._is_empty(v)]
            #                 lines.append(f"{indent}  * [{idx}] " + " | ".join(sub_items))
            #             else:
            #                 lines.append(f"{indent}  * [{idx}] {item}")

            # # C. 여러 줄로 된 긴 텍스트 (final_answer 등)
            # elif isinstance(val, str) and ("\n" in val or len(val) > 70):
            #     quote_block = val.strip().replace("\n", f"\n{indent}  > ")
            #     lines.append(f"{indent}* {display_name}:\n{indent}  > {quote_block}")

            # # D. 일반 단일 값 (단문, 정수, 실수, 불리언)
            else:
                lines.append(f"{indent}* {display_name}: {val}")

        return "\n".join(lines) if lines else "*(표시할 세부 분석 데이터가 없습니다)*"

    def finish_main_step(self):
        """Crew 종료 후 메인 Step의 이름을 마감하고, 누적된 전체 로그를 output(드롭다운)에 연결"""
        self.update_step_status(
            name = "✅ [Workflow 완료] 에이전트 상세 작업 내역 보기 (클릭)",
            output = "\n\n".join(self.logs_history) if self.logs_history else "상세 실행 로그가 존재하지 않습니다."
        )

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