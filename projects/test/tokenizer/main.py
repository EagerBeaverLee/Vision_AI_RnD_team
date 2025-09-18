from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import List
import tiktoken
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 모델 토크나이저 초기화 및 설정
encoding = tiktoken.get_encoding("o200k_harmony")
MAX_TOKENS = 4096

# 메시지 리스트의 토큰 수를 계산하는 함수
def count_tokens(messages: List[BaseMessage]) -> int:
    token_count = 0
    # 시스템 프롬프트 토큰도 계산
    token_count += len(encoding.encode("너는 친절한 AI 어시스턴트야. 항상 존댓말로 대답해."))
    
    for message in messages:
        token_count += len(encoding.encode(message.content))
    return token_count

# 챗 모델 인스턴스 생성
model = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.108:8000/v1",
            temperature=0.2
        )

# 프롬프트 템플릿 정의
prompt = ChatPromptTemplate.from_messages([
    ("system", "너는 친절한 AI 어시스턴트야. 항상 존댓말로 대답해."),
    ("placeholder", "{history}"),
    ("human", "{input}"),
])

# Runnable 객체 생성
runnable = prompt | model

# RunnableWithMessageHistory와 커스텀 기록 객체 연결
store = {}
def get_session_history(session_id: str) -> ChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

with_message_history = RunnableWithMessageHistory(
    runnable,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)

# 예시 실행
session_id = "test_session_id"
config = {"configurable": {"session_id": session_id}}

# 첫 번째 질문
print("사용자: 정보작전이 뭐야??")
response1 = with_message_history.invoke({"input": "정보작전이 뭐야??"}, config)
print(f"AI: {response1.content}")

# 첫 번째 대화 후 토큰 수 확인
history = get_session_history(session_id)
token_count = count_tokens(history.messages)
print(f"현재 채팅 기록의 토큰 수: {token_count}/{MAX_TOKENS}")

# 두 번째 질문
print("\n사용자: 그걸 활용하면 어떤 이점이 있어??")
response2 = with_message_history.invoke({"input": "그걸 활용하면 어떤 이점이 있어??"}, config)
print(f"AI: {response2.content}")

# 두 번째 대화 후 토큰 수 확인
history = get_session_history(session_id)
token_count = count_tokens(history.messages)
print(f"현재 채팅 기록의 토큰 수: {token_count}/{MAX_TOKENS}")