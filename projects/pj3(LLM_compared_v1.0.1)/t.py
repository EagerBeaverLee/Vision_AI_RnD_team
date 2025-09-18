from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables import RunnableLambda

rag_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant, world-class expert in Roman and Greek history,"
        " especially in towns located in southern Italy."
        "Provide interesting insights on local history and recommend places to visit with knowledgeable and engaging answers."
        "Answer all questions to the best of your ability, but only use what has been provided in the context."
        "If you don't know, just say you don't know. Use three sentences maximum and keep the answer as concise as possible."),
        ("placeholder", "{chat_history_messages}"),
        # ("assistant", "{retrieved_context}"),
        ("human", "{question}"),
    ]
)

# retriever = vector_db.as_retriever()
question_feeder = RunnablePassthrough()
chatbot = ChatOpenAI(
    api_key="ai",
    model="openai/gpt-oss-20b",
    base_url="http://192.168.0.108:8000/v1",
)
chat_history_memory = ChatMessageHistory()

def get_messages(x):
    print(chat_history_memory.messages)
    return chat_history_memory.messages

rag_chain = {
    # "retrieved_context": retriever,
    "question": question_feeder,
    "chat_history_messages": RunnableLambda(get_messages)
} | rag_prompt | chatbot

def execute_chain_with_memory(chain, question):
    chat_history_memory.add_user_message(question)
    answer = chain.invoke(question)
    chat_history_memory.add_ai_message(answer)
    print(answer.response_metadata['token_usage'])
    print(f'Full chat message history: {chat_history_memory.messages}\n\n')
    return answer


execute_chain_with_memory(rag_chain, "나는 빨간색을 좋아해")
execute_chain_with_memory(rag_chain, "내가 무슨색을 좋아한다고 했지?")
execute_chain_with_memory(rag_chain, "나는 흰색도 좋아해")