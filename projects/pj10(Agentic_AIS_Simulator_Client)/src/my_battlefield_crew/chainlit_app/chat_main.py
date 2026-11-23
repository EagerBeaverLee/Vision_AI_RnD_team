import asyncio
import chainlit as cl
from my_battlefield_crew.chainlit_app.chainlit_handler import ChainlitCrewHandler
from chainlit.server import app
from fastapi import Response, status, Request, status, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from typing import Optional
from my_battlefield_crew.setting.rag_config import RAGConfig
from my_battlefield_crew.setting.llm_config import LLMConfig
from my_battlefield_crew.engine.rag_pipeline import RAGPipeline
from my_battlefield_crew.chainlit_app.schemas import SimulationContext, SimTime
from multiprocessing import shared_memory
from my_battlefield_crew.chainlit_app.map_store import get_map_html

CURRENT_LLM_CONFIG = LLMConfig()
CURRENT_RAG_CONFIG = RAGConfig()
CURRENT_RAG_PIPELINE = RAGPipeline(rag_config=CURRENT_RAG_CONFIG)

SHM_NAME = "ais_sim_server_time"
SHM_NAME_2 = "ais_start_server_time"
SHM_DB_PATH_NAME = "db_path"

# 해시 기반 인메모리 캐시 딕셔너리 (combined_hash -> FAISS)
# EMBED_CACHE: dict[str, FAISS] = {}
# 비동기 취소 제어 이벤트
EMBED_CANCEL_EVENT = asyncio.Event()

# 지도를 렌더링하기 위해 호출되는 함수
@app.get("/api/inmemory-map/{map_id}", response_class=HTMLResponse)
async def serve_inmemory_map(map_id: str):
    """브라우저가 iframe을 통해 요청 시 메모리(RAM)에서 HTML을 직접 반환"""
    html_content = get_map_html(map_id)
    if html_content:
        return HTMLResponse(
            content=html_content,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    return HTMLResponse(
        "<h3>지도를 불러올 수 없습니다 (만료됨).</h3>", status_code=404
    )
# 지도 정상적 갱신을 위한 필수 코드
app.router.routes.insert(0, app.router.routes.pop())

@app.post("/api/rag/embed/cancel")
async def cancel_rag_embed():
    """진행 중인 임베딩 플래그 중단 설정"""
    print("[chainlit서버] 취소 신호 수신")
    EMBED_CANCEL_EVENT.set()
    return {"status": "cancel_signal_set"}

@app.post("/api/rag/embed")
async def stream_rag_embed(request: Request):
    """Qt 클라이언트로부터 절대 경로들을 받아 인메모리 임베딩 후 진행률 스트리밍"""
    data = await request.json()
    file_paths: list[str] = data.get("file_paths", [])

    if not file_paths:
        return JSONResponse(
            status_code=400, content={"error": "파일 경로가 없습니다."}
        )
    #취소 플래그 초기화
    EMBED_CANCEL_EVENT.clear()

    # 절대경로를 RAGConfig에 넣고 Pipeline의 config 업데이트
    CURRENT_RAG_CONFIG.source_path = file_paths

    print("#"*20 + "현재 ragconfig 설정" + "#"*20)
    print(f"{CURRENT_RAG_CONFIG.question_transform}\n{CURRENT_RAG_CONFIG.post_processing}\n{CURRENT_RAG_CONFIG.indexing.strategy}\n{CURRENT_RAG_CONFIG.source_path}")

    CURRENT_RAG_PIPELINE.update_config(CURRENT_RAG_CONFIG)

    # 캐시 확인
    # combined_hash = compute_combined_hash(file_paths)
    # if combined_hash in EMBED_CACHE:
    #     global CURRENT_RAG_PIPELINE
    #     CURRENT_RAG_PIPELINE = EMBED_CACHE[combined_hash]
    #     CURRENT_RAG_PIPELINE.update_config(CURRENT_RAG_CONFIG)
    #     return StreamingResponse(iter(["CACHED\n"]), media_type="text/plain")

    # EMBED_CANCEL_EVENT.clear()

    async def sse_stream():
        # 💡 RAGPipeline의 build_stream 제너레이터를 SSE로 직접 패스스루
        async for progress_msg in CURRENT_RAG_PIPELINE.build_vectorstore(EMBED_CANCEL_EVENT):
            yield progress_msg
            if progress_msg == "COMPLETE\n":
                print("chainlit_main에서 임베딩 성공적으로 완료")
                # EMBED_CACHE[combined_hash] = CURRENT_RAG_PIPELINE

    return StreamingResponse(sse_stream(), media_type="text/plain")
        
# 💡 2. Qt로부터 최신 설정을 수신받는 FastAPI 엔드포인트
@app.post("/api/rag/config", status_code=status.HTTP_200_OK)
async def update_rag_config(rag_config: RAGConfig):
    """Qt 클라이언트에서 설정 변경 시 호출하는 API"""
    global CURRENT_RAG_CONFIG
    CURRENT_RAG_CONFIG = rag_config
    CURRENT_RAG_PIPELINE.update_config(CURRENT_RAG_CONFIG)
    print(f">>> [Chainlit API] RAG 설정이 인메모리에 갱신되었습니다:\n{CURRENT_RAG_CONFIG.question_transform}\n{CURRENT_RAG_CONFIG.indexing.strategy}\n{CURRENT_RAG_CONFIG.post_processing}")
    return {"status": "success", "message": "RAG 설정이 성공적으로 반영되었습니다."}

@app.post("/api/llm/config", status_code=status.HTTP_200_OK)
async def update_llm_config(llm_config: LLMConfig):
    """Qt 클라이언트에서 설정 변경 시 호출하는 API"""
    global CURRENT_LLM_CONFIG
    CURRENT_LLM_CONFIG = llm_config
    print(f">>> [Chainlit API] LLM 설정이 인메모리에 갱신되었습니다: {llm_config.system_prompt[:10]}")
    return {"status": "success", "message": "LLM 설정이 성공적으로 반영되었습니다."}


def get_current_simulation_time() -> str:
    """공유 메모리에서 현재 시뮬레이션 서버 시간을 즉시 읽어오는 함수"""
    try:
        shm = shared_memory.SharedMemory(name=SHM_NAME)
        # RAM 버퍼의 첫 19바이트를 읽어 문자열로 디코딩
        sim_time_str = bytes(shm.buf[:19]).decode("ascii").strip()
        shm.close()  # 연결만 닫음 (unlink는 하지 않음)
        return sim_time_str
    except FileNotFoundError:
        # Qt 시뮬레이터가 아직 실행되지 않았거나 시간을 쓰지 않은 경우
        return "시간 정보 미수신 (시뮬레이터 미연결)"
    except Exception as e:
        return f"시간 확인 불가 ({e})"

def get_start_simulation_time() -> str:
    """공유 메모리에서 현재 시뮬레이션 서버 시간을 즉시 읽어오는 함수"""
    try:
        shm2 = shared_memory.SharedMemory(name=SHM_NAME_2)
        # RAM 버퍼의 첫 19바이트를 읽어 문자열로 디코딩
        start_time_str = bytes(shm2.buf[:19]).decode("ascii").strip()
        shm2.close()  # 연결만 닫음 (unlink는 하지 않음)
        return start_time_str
    except FileNotFoundError:
        # Qt 시뮬레이터가 아직 실행되지 않았거나 시간을 쓰지 않은 경우
        return "시간 정보 미수신 (시뮬레이터 미연결)"
    except Exception as e:
        return f"시간 확인 불가 ({e})"

def get_db_path() -> str:
    """공유 메모리에서 db경로를 즉시 읽어오는 함수"""
    try:
        shm_db_path = shared_memory.SharedMemory(name=SHM_DB_PATH_NAME)
        # 널 바이트(\x00) 전까지만 잘라서 복원
        raw_bytes = bytes(shm_db_path.buf).split(b"\x00", 1)[0]
        db_path = raw_bytes.decode("utf-8")
        shm_db_path.close()  # 연결만 닫음 (unlink는 하지 않음)
        return db_path
    except FileNotFoundError:
        # Qt 시뮬레이터가 아직 실행되지 않았거나 시간을 쓰지 않은 경우
        return "시간 정보 미수신 (시뮬레이터 미연결)"
    except Exception as e:
        return f"시간 확인 불가 ({e})"


@cl.on_chat_start
async def start():
    await cl.Message(content="👋 안녕하세요! 해상 기상 및 안전 매뉴얼 검색 시스템입니다.").send()

@cl.on_message
async def main(message: cl.Message):
    from my_battlefield_crew.crews.main_system_flow import MainSystemFlow
    from my_battlefield_crew.engine.preprocessor import init_geo_processing
    # 💡 async with 컨텍스트로 cl.Step을 열어야 '사용 중' 활성 상태가 유지됩니다.
    async with cl.Step(name="🚀 질문 분석 및 에이전트 구동 중...", type="run", default_open=False, auto_collapse=True) as step:
        handler = ChainlitCrewHandler(step=step)

        processing_list = None
        db_path = get_db_path()
        start_time = get_start_simulation_time()
        curr_time = get_current_simulation_time()
        print(f">>> [Chainlit] 리포트 db경로 출력: {db_path}")
        print(f">>> [Chainlit] 리포트 시작 시각 캡처: {start_time}")
        print(f">>> [Chainlit] 리포트 기준 시각 캡처: {curr_time}")

        async with cl.Step(name="🛰️ 전술 상황 사전 분석 및 데이터 전처리", type="tool") as prep_step:
            prep_step.output = f"기준 시각 [{curr_time}] 기준 데이터셋 추출 중..."
            
            # 이벤트 루프 차단 없이 백그라운드 스레드에서 무거운 작업 처리
            processing_list = await asyncio.to_thread(
                init_geo_processing,
                db_path=db_path,
                start_time=start_time,
                end_time=curr_time
            )
            if processing_list:
                prep_step.output = f"전처리 완료: {processing_list})"
            else:
                prep_step.output = "오류로 인해 전처리가 정상적으로 완료되지 않았습니다."
                return

        if not processing_list:
            handler.update_step_status(
                name = "❌​ 전처리가 이루어지지 않아 답변을 생성할 수 없습니다",
                output = "상세 실행 로그가 존재하지 않습니다."
            )
            return

        context = SimulationContext(
            user_question=message.content,
            processing_list=processing_list,
            realtime_db_path=db_path,
            time = SimTime(
                start_time=start_time,
                curr_time=curr_time,
            ),
            ui_handler=handler,
            rag_pipe = CURRENT_RAG_PIPELINE
        )

        context.report_time_adjustment()

        mainsystemflow = MainSystemFlow(
            context=context
        )

        result = await mainsystemflow.kickoff_async()

        handler.finish_main_step()

    # 4. 전체 태스크 이력 아코디언 출력 및 최종 답변 타이핑 스트리밍    
    await handler.stream_final_response(result, context)