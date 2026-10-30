import pandas as pd
from datetime import timedelta
from dataclasses import dataclass, field
from typing import Callable, Optional
from langchain_community.vectorstores import FAISS
from my_battlefield_crew.setting.rag_config import RAGConfig
from my_battlefield_crew.setting.llm_config import LLMConfig
from my_battlefield_crew.chainlit_app.chainlit_handler import ChainlitCrewHandler

@dataclass
class SimulationContext:
    """모든 Flow 및 하위 Crew가 공유하는 단일 런타임 컨텍스트"""
    user_question: str = ""
    db_path: str = ""
    processing_list: dict = field(default_factory=dict)
    
    origin_start_time: str = ""
    start_time: str = ""
    curr_time: str = ""
    end_time: str = ""

    time_diff: timedelta = field(default_factory=timedelta) 
    vector_store: Optional[FAISS] = None
    llm_config: Optional[LLMConfig] = None
    rag_config: Optional[RAGConfig] = None
    ui_handler: Optional[ChainlitCrewHandler] = None

    def report_time_adjustment(self):
        origin_start_time = self.start_time[:19]
        end_time = self.curr_time[:19]

        time_diff = pd.to_datetime(end_time) - pd.to_datetime(origin_start_time)
        
        # 최근 3시간으로 리포트 생성되도록 시간 설정
        if time_diff.total_seconds() > 10800:
            time_diff = timedelta(seconds=10800)
            res = pd.to_datetime(end_time) - time_diff
            start_time = res.strftime('%Y-%m-%d %H:%M:%S')
        else:
            start_time = origin_start_time

        self.origin_start_time = origin_start_time
        self.start_time = start_time
        self.end_time = end_time
        self.time_diff = time_diff