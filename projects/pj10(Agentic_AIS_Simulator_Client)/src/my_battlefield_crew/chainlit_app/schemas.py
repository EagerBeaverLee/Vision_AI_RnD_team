import pandas as pd
import textwrap
from datetime import timedelta
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, List, TYPE_CHECKING
from langchain_community.vectorstores import FAISS
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

    def attach_bokeh_map(
        self, key: str, html_content: str, height: int = 330
    ) -> None:
        """Bokeh HTML을 저장소에 등록하고 마크다운 삽입용 iframe 블록으로 변환해 저장"""
        map_url = save_map_html(html_content)
        self.artifacts[key] = textwrap.dedent(f"""\
<!-- BOKEH_MAP_START -->
<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin: 16px 0;">
<iframe src="{map_url}" width="49%" height="{height}" style="border: 1px solid #334155; border-radius: 8px;"></iframe>
</div>
<!-- BOKEH_MAP_END -->""")

    def attach_bokeh_map_grid(
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
                'style="border: 1px solid #334155; border-radius: 8px;"></iframe>'
            )

        self.artifacts[key] = (
            "<!-- BOKEH_MAP_START -->\n"
            '<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin: 16px 0;">\n'
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
<iframe src="{table_widget_url}" width="100%" height="{height}" style="border: 1px solid #334155; border-radius: 8px; margin: 14px 0;" scrolling="no"></iframe>
<!-- WIDGET_END -->""")


    def attach_base64_image(
        self, key: str, base64_str: str, height: int = 380
    ) -> None:
        """Base64 PNG 이미지를 마크다운 삽입용 iframe 블록으로 변환해 저장"""
        self.artifacts[key] = textwrap.dedent(f"""\
<!-- IMG_START -->
<iframe srcdoc='<body style="margin:0;display:flex;justify-content:center;"><img src="data:image/png;base64,{base64_str}" style="max-width:100%; border-radius:8px;"></body>' width="100%" height="{height}px" style="border:none;" scrolling="no"></iframe>
<!-- IMG_END -->""")