from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_openai import ChatOpenAI

chat_history = ChatMessageHistory()

chat_model = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.108:8000/v1",
            temperature=0.3
        )

prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    ""
                ),
                ("placeholder", "{chat_history}")
            ]
        )

chain = (
            prompt
            # | RunnableLambda(lambda x: print(x["chat history"].messages))
            | chat_model
        )

chat_history.add_user_message("나는 빨간색을 좋아해")
response = chain.invoke(
    {"chat_history": chat_history.messages},
)
chat_history.add_ai_message(response)

print(response.response_metadata['token_usage'])

chat_history.add_user_message("내가 무슨색을 좋아한다고 했지?")
response = chain.invoke(
    {"chat_history": chat_history.messages},
)
chat_history.add_ai_message(response)

print(response.response_metadata['token_usage'])

chat_history.add_user_message("나는 흰색도 좋아해")
response = chain.invoke(
    {"chat_history": chat_history.messages},
)
chat_history.add_ai_message(response)

print(response.response_metadata['token_usage'])
print(chat_history.messages)