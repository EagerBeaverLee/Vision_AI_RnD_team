import pandas as pd
import textwrap
import threading
import time
from datetime import timedelta, datetime
from dataclasses import dataclass, field
from pydantic import BaseModel
from typing import Dict, List, Any, Set
from my_battlefield_crew.engine.rag_pipeline import RAGPipeline
from my_battlefield_crew.chainlit_app.map_store import save_map_html

@dataclass
class SimTime:
    origin_start_time: str = ""
    start_time: str = ""
    curr_time: str = ""
    end_time: str = ""
    time_diff: timedelta = field(default_factory=timedelta) 

@dataclass
class SimulationContext:
    """모든 Flow 및 하위 Crew가 공유하는 단일 런타임 컨텍스트"""
    user_question: str = ""
    realtime_db_path: str = ""                                  # 패킷 저장되는 db경로
    processing_list: dict = field(default_factory=dict)         # geo관련 전처리 변수
    time: SimTime = field(default_factory=SimTime)
    rag_pipe: RAGPipeline = field(default_factory=RAGPipeline)
    ui_handler: any = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    raw_outputs: Dict[str, Any] = field(default_factory=dict)

    # Pydantic 검증/직렬화에서 제외되는 내부 동기화 상태
    # --- 생성자(init) 인자에서 제외되는 내부 동기화용 변수들 ---
    _expected_tools: Set[str] = field(default_factory=set, init=False, repr=False)
    _completed_tools: Set[str] = field(default_factory=set, init=False, repr=False)
    _answer_step_started: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def report_time_adjustment(self):
        origin_start_time = self.time.start_time[:19]
        end_time = self.time.curr_time[:19]

        time_diff = pd.to_datetime(end_time) - pd.to_datetime(origin_start_time)
        
        # 최근 3시간으로 리포트 생성되도록 시간 설정
        if time_diff.total_seconds() > 10800:
            time_diff = timedelta(seconds=10800)
            res = pd.to_datetime(end_time) - time_diff
            start_time = res.strftime('%Y-%m-%d %H:%M:%S')
        else:
            start_time = origin_start_time

        self.time.origin_start_time = origin_start_time
        self.time.start_time = start_time
        self.time.end_time = end_time
        self.time.time_diff = time_diff

    def attach_bokeh_odflow_map(
        self, key: str, html_content: str, height: int = 330
    ) -> None:
        """Bokeh HTML을 저장소에 등록하고 마크다운 삽입용 iframe 블록으로 변환해 저장"""
        map_url = save_map_html(html_content)
        self.artifacts[key] = textwrap.dedent(f"""\
<!-- BOKEH_MAP_START -->
<div style="display: flex; flex-wrap: wrap; width: 100%; justify-content: center; gap: 12px; margin: 16px 0;">
<iframe src="{map_url}" width="78%" height="{height}" style="border: 1px solid #374A37; border-radius: 8px;"></iframe>
</div>
<!-- BOKEH_MAP_END -->""")

    def attach_bokeh_major_port_map_grid(
        self, key: str, html_contents: List[str], height: int = 360
    ) -> None:
        """여러 개의 Bokeh HTML을 2열(2x2 등) 그리드 형태의 단일 블록으로 저장"""
        if not html_contents:
            print("html_contents 리스트가 비어있습니다")
            return

        iframes = []
        for html_content in html_contents:
            map_url = save_map_html(html_content)
            iframes.append(
                f'<iframe src="{map_url}" width="49%" height="{height}" '
                'style="border: 1px solid #374A37; border-radius: 8px;"></iframe>'
            )

        self.artifacts[key] = (
            "<!-- BOKEH_MAP_START -->\n"
            '<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin: 16px 0;">\n'
            + "\n".join(iframes)
            + "\n</div>\n"
            "<!-- BOKEH_MAP_END -->"
        )

    def attach_bokeh_direction_map(
        self, key: str, html_content_hist: str, html_content_map: str, height_hist: int = 330, height_map: int = 620
    ) -> None:
        iframes = []

        map_url_hist = save_map_html(html_content_hist)
        iframes.append(
            f'<iframe src="{map_url_hist}" width="100%" height="{height_hist}" '
            'style="border: 1px solid #374A37; border-radius: 8px; margin: 12px 0;"></iframe>'
        )

        map_url_map = save_map_html(html_content_map)
        iframes.append(
            f'<iframe src="{map_url_map}" width="100%" height="{height_map}" '
            'style="border: 1px solid #374A37; border-radius: 8px; margin: 12px 0;"></iframe>'
        )

        self.artifacts[key] = (
            "<!-- BOKEH_MAP_START -->\n"
            '<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin: 16px 0;">\n'
            + "\n".join(iframes)
            + "\n</div>\n"
            "<!-- BOKEH_MAP_END -->"
        )
    
    def attach_table_block(
        self, key: str, html_content: str, height: int = 300
    ) -> None:
        """html로 만든 필터 가능한 테이블을 마크다운 삽입용 iframe 블록 변환 저장"""
        table_widget_url = save_map_html(html_content)
        self.artifacts[key] = textwrap.dedent(f"""\
<!-- WIDGET_START -->
<iframe src="{table_widget_url}" width="100%" height="{height}" style="border: 1px solid #374A37; border-radius: 8px; margin: 14px 0;" scrolling="no"></iframe>
<!-- WIDGET_END -->""")

    def attach_base64_image(
        self, key: str, base64_str: str, height: int = 380
    ) -> None:
        """Base64 PNG 이미지를 마크다운 삽입용 iframe 블록으로 변환해 저장"""
        self.artifacts[key] = textwrap.dedent(f"""\
<!-- IMG_START -->
<iframe srcdoc='<body style="margin:0;display:flex;justify-content:center;"><img src="data:image/png;base64,{base64_str}" style="max-width:100%; border-radius:8px;"></body>' width="100%" height="{height}px" style="border:none;" scrolling="no"></iframe>
<!-- IMG_END -->""")

    ########## 도구 호출 이후 답변 생성중 메세지를 띄우기 위한 함수들 ############
    def init_tool_tracker(self, equipped_tools: list) -> None:
        """Crew 실행 직전에 호출하여 장착된 도구 목록 세팅"""
        with self._lock:
            self._expected_tools = {t.name for t in (equipped_tools or [])}
            self._completed_tools.clear()
            self._answer_step_started = False

    def _check_should_trigger(self, tool_name: str) -> bool:
        """락 내부에서 마지막 도구 완료 여부 1회 판별"""
        with self._lock:
            if tool_name in self._expected_tools:
                self._completed_tools.add(tool_name)
                
            if (
                len(self._completed_tools) >= len(self._expected_tools)
                and not self._answer_step_started
            ):
                self._answer_step_started = True
                return True
            return False

    def mark_tool_done(self, tool_name: str) -> None:
        """도구 실행이 끝나는 직후 호출 (동기/비동기 도구 공통 사용 가능)"""
        if self._check_should_trigger(tool_name) and self.ui_handler is not None:
            self.ui_handler.start_final_answer_phase()
    ###########################################################################