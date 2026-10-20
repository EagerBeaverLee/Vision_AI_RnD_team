import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from typing import Optional

# 1. Data Layer 설정: 로컬 SQLite 파일에 대화방/메시지 영구 저장
@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo="sqlite+aiosqlite:///chat_history.db")

# 2. 인증 설정: 채팅방을 사용자별로 관리하기 위해 필수
@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    # 테스트 계정 (실제 운영 시에는 DB 조회 및 해시값 검증 사용)
    if username == "admin" and password == "1234":
        return cl.User(identifier=username, metadata={"role": "admin"})
    return None

# 3. 새로운 채팅방이 열렸을 때
@cl.on_chat_start
async def on_chat_start():
    # 신규 세션의 대화 히스토리 버퍼 초기화
    cl.user_session.set("messages", [])
    await cl.Message(content="새 대화방이 생성되었습니다. 질문을 입력하세요.").send()

# 4. 사이드바에서 기존 대화방을 클릭하여 이어할 때
@cl.on_chat_resume
async def on_chat_resume(thread: cl.ThreadDict):
    # Chainlit UI는 이전 메시지를 브라우저 화면에 자동으로 다시 그려줍니다.
    # 하지만 백엔드 메모리/LLM Context 유지를 위해 세션 변수에 이전 대화를 복원해야 합니다.
    messages = []
    for step in thread.get("steps", []):
        if step.get("type") == "user_message":
            messages.append({"role": "user", "content": step.get("output", "")})
        elif step.get("type") == "assistant_message":
            messages.append({"role": "assistant", "content": step.get("output", "")})

    cl.user_session.set("messages", messages)
    await cl.Message(content="기존 대화방을 불러왔습니다. 이어서 대화하세요!").send()

# 5. 사용자 메시지 수신 및 답변
@cl.on_message
async def on_message(message: cl.Message):
    history = cl.user_session.get("messages", [])
    history.append({"role": "user", "content": message.content})

    # 실제 LLM(OpenAI/LangChain 등) 호출부 (여기서는 동작 검증용 에코)
    response_text = f"답변: '{message.content}' (현재 방의 누적 대화 수: {len(history)})"
    
    history.append({"role": "assistant", "content": response_text})
    cl.user_session.set("messages", history)

    await cl.Message(content=response_text).send()