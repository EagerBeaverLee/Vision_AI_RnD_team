import sys
from pathlib import Path
import chainlit as cl
from chainlit_handler import ChainlitCrewHandler
from chainlit.server import app
from fastapi import Response, status

# 현재 파일(chat_main.py) 기준으로 프로젝트 최상위 루트 디렉토리 찾기
# chat_main.py(파일) -> chainlit_app(parent) -> 프로젝트 루트(parent.parent)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# sys.path 최상단에 프로젝트 루트 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crews.battlefield_router_crew import RouterCrew
from crews.battlefield_crew import BattlefieldCrew
from crews.battlefield_models import format_maritime_report
from crews.main_system_flow import MainSystemFlow
# from crews.rag_crew import RAGCrew
from RAG.rag_config import RAGConfig

CURRENT_RAG_CONFIG = RAGConfig()

# 💡 2. Qt로부터 최신 설정을 수신받는 FastAPI 엔드포인트
@app.post("/api/rag/config", status_code=status.HTTP_200_OK)
async def update_rag_config(config: RAGConfig):
    """Qt 클라이언트에서 설정 변경 시 호출하는 API"""
    global CURRENT_RAG_CONFIG
    CURRENT_RAG_CONFIG = config
    print(f">>> [Chainlit API] RAG 설정이 인메모리에 갱신되었습니다: {config.indexing.strategy}")
    return {"status": "success", "message": "RAG 설정이 성공적으로 반영되었습니다."}

app.get("/api/rag/config", response_model=RAGConfig)

@cl.on_chat_start
async def start():
    await cl.Message(content="👋 안녕하세요! 해상 기상 및 안전 매뉴얼 검색 시스템입니다.").send()

@cl.on_message
async def main(message: cl.Message):
    # 💡 async with 컨텍스트로 cl.Step을 열어야 '사용 중' 활성 상태가 유지됩니다.
    async with cl.Step(name="🚀 질문 분석 및 에이전트 구동 중...", type="run", default_open=False, auto_collapse=True) as step:
        handler = ChainlitCrewHandler(step=step)

        mainsystemflow = MainSystemFlow(
            ui_handler=handler,
            message=message.content
        )

        result = await mainsystemflow.kickoff_async()

        handler.finish_main_step()

    # 4. 전체 태스크 이력 아코디언 출력 및 최종 답변 타이핑 스트리밍    
    await handler.stream_final_response(result)