import asyncio
import json
import time
import re
import threading
import contextvars
from typing import Any, List, Optional
import chainlit as cl
from my_battlefield_crew.chainlit_app.schemas import SimulationContext

try:
    from langchain_core.agents import AgentAction, AgentFinish
except ImportError:
    AgentAction = AgentFinish = None

class TimestampedLogList(list):
    """append 호출 시 핸들러 생성(질문 입력) 시점 기준 [MM:SS.ms] 경과 시간을 자동 부착하는 리스트"""

    def __init__(self, start_perf: float):
        super().__init__()
        self.start_perf = start_perf

    def get_elapsed_tag(self) -> str:
        elapsed = max(0.0, time.perf_counter() - self.start_perf)
        total_centiseconds = int(elapsed * 100)

        minutes, rem_cs = divmod(total_centiseconds, 6000)
        seconds, ms_two_digits = divmod(rem_cs, 100)

        if minutes > 0:
            return f"[{minutes}m {seconds}s {ms_two_digits:02d}ms]"
        return f"[{seconds}s {ms_two_digits:02d}ms]"

    def append(self, message: str) -> None:
        tag = self.get_elapsed_tag()
        msg_str = str(message)

        # 1. 앞쪽 구분선('\n---\n') 분리
        prefix = ""
        body = msg_str
        if body.startswith("\n---\n"):
            prefix = "\n---\n"
            body = body[len("\n---\n"):]

        # 2. 본문이 마크다운 헤딩('#'으로 시작)인 경우 '#' 기호 바로 뒤에 타임스탬프 배치
        heading_match = re.match(r"^(#{1,6}\s+)(.*)", body, flags=re.DOTALL)
        if heading_match:
            hashes, rest = heading_match.groups()
            formatted = f"{prefix}{hashes}`{tag}` {rest}"
        else:
            formatted = f"{prefix}`{tag}` {body}"

        super().append(formatted)

class ChainlitCrewHandler:
    """CrewAI 실행 진행 상황을 단일 cl.Step 내부에 집약하여 제어하는 핸들러"""

    def __init__(self, step: cl.step):
        self.step = step
        self.start_perf = time.perf_counter()
        self.logs_history: List[str] = TimestampedLogList(self.start_perf)

        # 초기 step.name에 이미 [0s] 등이 붙어있더라도 중복되지 않게 순수 제목만 추출
        raw_name = step.name or "🚀 질문 분석 및 에이전트 구동 중..."
        self._base_step_name: str = re.sub(r"^\[(?:\d+m\s*)?\d+s\]\s*", "", raw_name)

        self.is_final_phase = False      # 최종 답변 생성 구간 진입 여부 잠금 플래그
        self.is_finished = False         # 타이머 종료 여부
        self._is_failed = False          # 에러/조기 중단 확정 여부 (finish 덮어쓰기 방지)
        self._ui_lock = threading.Lock()
        self._stop_event = threading.Event()

        # 생성 시점의 메인 이벤트 루프와 Chainlit 세션 컨텍스트를 캡처
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None
        self._cl_context = contextvars.copy_context()

        # 0초([0s]) 상태 즉시 1회 반영
        self.update_step_status(delay=0)

        # 타이머 스레드가 self._cl_context를 점유하지 않도록 target에 직접 함수 연결
        self._timer_thread = threading.Thread(
            target=self._live_timer_worker,
            daemon=True,
        )
        self._timer_thread.start()

    def _format_live_seconds(self) -> str:
        """밀리초를 제외한 실시간 경과 시간 포맷 ([3s], [57s], [1m 23s])"""
        total_sec = int(max(0.0, time.perf_counter() - self.start_perf))
        minutes, seconds = divmod(total_sec, 60)
        if minutes > 0:
            return f"[{minutes}m {seconds}s]"
        return f"[{seconds}s]"
    
    def _build_step_name(self) -> str:
        """실시간 시간 헤더 + 현재 상태 제목 결합"""
        if self.is_finished:
            return self._base_step_name
        return f"{self._format_live_seconds()} {self._base_step_name}"

    def _live_timer_worker(self):
        """별도 OS 스레드에서 1.0초 간격으로 끊김 없이 update_step_status 호출"""
        while not self._stop_event.wait(timeout=1.0):
            if self.is_finished:
                break
            try:
                self.update_step_status(delay=0)
            except Exception as e:
                print(f"[Timer Update Warning] {e}")

    def _dispatch_step_update(self):
        """어느 스레드에서 호출되든 캡처된 Chainlit 컨텍스트(_cl_context)로 안전하게 step.update() 실행"""
        if self._main_loop is not None and self._main_loop.is_running():
            def _schedule_task():
                task = self._main_loop.create_task(self.step.update())
                task.add_done_callback(
                    lambda t: print(f"[Step Update Error] {t.exception()}")
                    if not t.cancelled() and t.exception()
                    else None
                )
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop == self._main_loop:
                _schedule_task()
            else:
                # 워커 스레드 컨텍스트가 비어있어도 항상 _cl_context 안에서 태스크 생성 보장
                self._main_loop.call_soon_threadsafe(
                    _schedule_task, context=self._cl_context.copy()
                )
        else:
            self._cl_context.run(lambda: cl.run_sync(self.step.update()))

    def get_elapsed_str(self) -> str:
        """현재까지 경과 시간을 [MM:SS.ms] 문자열로 반환 (필요 시 외부에서도 직접 호출 가능)"""
        return self.logs_history.get_elapsed_tag()

    def start_final_answer_phase(self):
        """모든 도구 실행이 끝난 직후 단 1회 호출되어 '답변 생성중' 상태로 고정"""
        self.is_final_phase = True
        self.logs_history.append("✍️ 모든 데이터 추출 완료. 최종 전술 브리핑을 작성 중입니다...")
        self.update_step_status(
            type_str="llm",
            icon="brain-circuit",
            name="[Task 진행 중] 모든 도구 실행 결과를 종합하여 답변 생성중...",
            delay=0,
            force_title=True,
        )

    def stop_timer(self):
        """데드락 없이 타이머 플래그를 즉시 내리고 스레드 정지"""
        self.is_finished = True
        self._stop_event.set()

        if (
            hasattr(self, "_timer_thread")
            and self._timer_thread.is_alive()
            and threading.current_thread() is not self._timer_thread
        ):
            # 락 밖에서 짧게 대기하여 데드락 원천 차단
            self._timer_thread.join(timeout=0.3)
    
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
            log_message += f"```json\n# Input Data\n{formatted_input}\n```\n"
            
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

    def update_step_status(
        self, type_str: str = None,
        icon: str = None,
        name: str = None,
        output: str = None,
        delay: float = 1.0,
        force_title: bool = False,
        _is_timer_tick: bool = False,
    ):
        """Chainlit Step UI 상태(아이콘, 타입, 제목)를 실시간 업데이트"""
        with self._ui_lock:
            # 1) 이미 에러 중단(_is_failed)된 경우 그 이후의 모든 덮어쓰기 차단
            if self._is_failed:
                return

            # 2) 타이머가 종료된 뒤 뒤늦게 들어온 타이머 틱 차단 (명시적 마감 업데이트는 허용!)
            if self.is_finished and _is_timer_tick:
                return
            
            if force_title or not self.is_final_phase or self.is_finished:
                if type_str is not None:
                    self.step.type = type_str
                if icon is not None:
                    self.step.icon = icon
                if name is not None:
                    self._base_step_name = name

            # 제목이 바뀌었든 안 바뀌었든 현재 경과 시간 헤더를 붙여 최신 상태 반영
            self.step.name = self._build_step_name()

            if output is not None:
                self.step.output = output
            elif self.logs_history:
                self.step.output = "\n\n".join(self.logs_history)

            self._dispatch_step_update()

        is_main_thread = threading.current_thread() is threading.main_thread()
        if not is_main_thread and delay is not None and delay > 0:
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

            # # D. 일반 단일 값 (단문, 정수, 실수, 불리언)
            else:
                lines.append(f"{indent}* {display_name}: {val}")

        return "\n".join(lines) if lines else "*(표시할 세부 분석 데이터가 없습니다)*"

    def finish_main_step(self):
        """Crew 종료 후 메인 Step의 이름을 마감하고, 누적된 전체 로그를 output(드롭다운)에 연결"""
        # 정상 완료 시: 이미 fail_main_step으로 중단된 경우에는 덮어쓰지 않음
        if self._is_failed:
            return
        
        self.stop_timer()
        total_tag = self.get_elapsed_str()
        self.update_step_status(
            icon="sparkles",
            name=f"✅ [Workflow 완료] 에이전트 상세 작업 내역 보기 ({total_tag[1:-5]} 동안 작업)",
            output="\n\n".join(self.logs_history),
            delay=0,
            force_title=True,
        )

    def fail_main_step(
        self,
        error_title: str = "❌ 전처리가 이루어지지 않아 답변을 생성할 수 없습니다",
        error_output: str = "상세 실행 로그가 존재하지 않습니다.",
    ):
        """에러/조기 중단 시 타이머를 끄고 단일 파이프라인(update_step_status)으로 마감"""
        self.stop_timer()
        self.update_step_status(
            type_str="run",
            icon="alert-circle",
            name=error_title,
            output=error_output,
            delay=0,
            force_title=True,
        )
        with self._ui_lock:
            self._is_failed = True

    # @staticmethod
    # async def stream_final_response(full_markdown: str, context: SimulationContext):
    #     """메인 대화창에는 오직 깔끔한 최종 결과만 타이핑 스트리밍 연출로 출력"""
    #     final_msg = cl.Message(content="")
    #     await final_msg.send()

    #     # 2. 작성하신 정규식 패턴 그대로 적용
    #     pattern = (
    #         r"(<!--\s*[A-Z_]+_START\s*-->.*?<!--\s*[A-Z_]+_END\s*-->|"
    #         r"<iframe[\s\S]*?</iframe>)"
    #     )

    #     tokens = re.split(pattern, full_markdown, flags=re.DOTALL | re.IGNORECASE)

    #     for token in tokens:
    #         if not token:
    #             continue

    #         token_stripped = token.strip()
    #         # 미디어 블록(iframe 또는 주석으로 감싼 이미지/지도) 판별
    #         is_media_block = (
    #             token_stripped.startswith("<!--") and "_START" in token_stripped
    #         ) or token_stripped.lower().startswith("<iframe")

    #         if is_media_block:
    #             # HTML 코드는 띄어쓰기로 쪼개지 않고 통째로 출력 (앞뒤 빈 줄로 마크다운 충돌 방지)
    #             await final_msg.stream_token("\n\n" + token + "\n\n")
    #             await asyncio.sleep(0.05)  # 브라우저 DOM 렌더링 안정화를 위한 짧은 대기
    #         else:
    #             # 일반 마크다운 텍스트는 기존처럼 단어 단위 타이핑 효과
    #             words = token.split(" ")
    #             for word in words:
    #                 if word:
    #                     await final_msg.stream_token(word + " ")
    #                     await asyncio.sleep(0.005)

    #     await final_msg.update()

    @staticmethod
    async def stream_final_response(full_markdown: str, context: SimulationContext):
        """QWebEngineView 환경에서도 글자 누락 없이 타이핑 스트리밍 + 인라인 미디어 렌더링"""
        final_msg = cl.Message(content="")
        await final_msg.send()

        pattern = (
            r"(<!--\s*[A-Z_]+_START\s*-->.*?<!--\s*[A-Z_]+_END\s*-->|"
            r"<iframe[\s\S]*?</iframe>)"
        )

        tokens = re.split(pattern, full_markdown, flags=re.DOTALL | re.IGNORECASE)

        for token in tokens:
            if not token:
                continue

            token_stripped = token.strip()
            is_media_block = (
                token_stripped.startswith("<!--") and "_START" in token_stripped
            ) or token_stripped.lower().startswith("<iframe")

            if is_media_block:
                # 1. 직전 텍스트의 마지막 프레임이 QWebEngineView 화면에 완전히 그려질 시간 확보
                await asyncio.sleep(0.15)

                clean_html = "\n".join(line.lstrip() for line in token_stripped.splitlines())
                await final_msg.stream_token("\n\n" + clean_html + "\n\n")

                # 2. iframe 로드 및 Bokeh JS 초기화 동안 다음 텍스트 패킷 유실 방지
                await asyncio.sleep(0.25)
            else:
                # 3. 1단어(5ms) 대신 3단어 묶음(25ms)으로 전송 -> WebSocket 패킷량 70% 감소, 체감 속도 동일
                word_chunks = re.findall(r"(?:\s*\S+){1,3}", token)
                for chunk in word_chunks:
                    await final_msg.stream_token(chunk)
                    await asyncio.sleep(0.025)

                trailing_ws = token[len("".join(word_chunks)):]
                if trailing_ws:
                    await final_msg.stream_token(trailing_ws)

        # 4. 마지막 토큰 처리가 완료된 후 최종 전체 본문 확정 동기화
        await asyncio.sleep(0.15)
        final_msg.content = full_markdown
        await final_msg.update()
