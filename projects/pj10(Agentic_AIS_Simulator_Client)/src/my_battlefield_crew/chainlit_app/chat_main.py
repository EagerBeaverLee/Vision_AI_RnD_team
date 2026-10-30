import asyncio
import chainlit as cl
from pathlib import Path
from my_battlefield_crew.chainlit_app.chainlit_handler import ChainlitCrewHandler
from chainlit.server import app
from fastapi import Response, status, Request, status, HTTPException
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from my_battlefield_crew.crews.main_system_flow import MainSystemFlow
from my_battlefield_crew.setting.rag_config import RAGConfig
from my_battlefield_crew.setting.llm_config import LLMConfig
from my_battlefield_crew.chainlit_app.schemas import SimulationContext
from multiprocessing import shared_memory
from my_battlefield_crew.engine.preprocessor import init_geo_processing

CURRENT_LLM_CONFIG = LLMConfig()
CURRENT_RAG_CONFIG = RAGConfig()
CURRENT_VECTOR_STORE: FAISS = None
SHM_NAME = "ais_sim_server_time"
SHM_NAME_2 = "ais_start_server_time"
SHM_DB_PATH_NAME = "db_path"

@app.post("/api/rag/vectorstore", status_code=status.HTTP_200_OK)
async def upload_vectorstore(request: Request):
    """Qt 클라이언트로부터 직렬화된 FAISS 바이너리를 수신하여 메모리에 적재"""
    global CURRENT_VECTOR_STORE
    try:
        # 1. HTTP Body에서 순수 바이너리 바이트 스트림 읽기
        raw_bytes = await request.body()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="수신된 데이터가 비어 있습니다.")

        # 2. text-embedding-3-small 모델로 인메모리 역직렬화
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        CURRENT_VECTOR_STORE = FAISS.deserialize_from_bytes(
            serialized=raw_bytes,
            embeddings=embeddings,
            allow_dangerous_deserialization=True  # pickle 역직렬화 허용
        )

        doc_count = len(CURRENT_VECTOR_STORE.docstore._dict)
        print(f">>> [Chainlit API] FAISS DB 인메모리 로드 완료 (보유 문서 수: {doc_count})")
        return {"status": "success", "message": f"{doc_count}개의 문서 인덱스가 메모리에 로드되었습니다."}

    except Exception as e:
        print(f">>> [Chainlit API Error] 역직렬화 실패: {e}")
        raise HTTPException(status_code=500, detail=f"역직렬화 실패: {str(e)}")
    
# 💡 2. Qt로부터 최신 설정을 수신받는 FastAPI 엔드포인트
@app.post("/api/rag/config", status_code=status.HTTP_200_OK)
async def update_rag_config(config: RAGConfig):
    """Qt 클라이언트에서 설정 변경 시 호출하는 API"""
    global CURRENT_RAG_CONFIG
    CURRENT_RAG_CONFIG = config
    print(f">>> [Chainlit API] RAG 설정이 인메모리에 갱신되었습니다:\n {CURRENT_RAG_CONFIG.question_transform}\n{CURRENT_RAG_CONFIG.indexing.strategy}\n{CURRENT_RAG_CONFIG.post_processing}")
    return {"status": "success", "message": "RAG 설정이 성공적으로 반영되었습니다."}

@app.post("/api/llm/config", status_code=status.HTTP_200_OK)
async def update_rag_config(config: LLMConfig):
    """Qt 클라이언트에서 설정 변경 시 호출하는 API"""
    global CURRENT_LLM_CONFIG
    CURRENT_LLM_CONFIG = config
    print(f">>> [Chainlit API] LLM 설정이 인메모리에 갱신되었습니다: {config.system_prompt[:10]}")
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
    """공유 메모리에서 현재 시뮬레이션 서버 시간을 즉시 읽어오는 함수"""
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

app.get("/api/rag/config", response_model=RAGConfig)

@cl.on_chat_start
async def start():
    await cl.Message(content="👋 안녕하세요! 해상 기상 및 안전 매뉴얼 검색 시스템입니다.").send()

@cl.on_message
async def main(message: cl.Message):
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
            
            prep_step.output = f"전처리 완료: {processing_list})"

        context = SimulationContext(
            user_question=message.content,
            processing_list=processing_list,
            db_path=db_path,
            start_time=start_time,
            curr_time=curr_time,
            ui_handler=handler,
            rag_config=CURRENT_RAG_CONFIG,
            llm_config=CURRENT_LLM_CONFIG,
            vector_store=CURRENT_VECTOR_STORE,
        )

        context.report_time_adjustment()

        mainsystemflow = MainSystemFlow(
            context=context
        )

        result = await mainsystemflow.kickoff_async()

        handler.finish_main_step()

    # 4. 전체 태스크 이력 아코디언 출력 및 최종 답변 타이핑 스트리밍    
    await handler.stream_final_response(result)