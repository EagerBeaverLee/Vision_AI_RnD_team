from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# Initialize the chat model with specific configurations
chat_model = ChatOllama(
    model="qwen3:0.6b",
    temperature=0.5,
    base_url="http://localhost:11434",  # Can be changed for remote Ollama instances
)

# Create a conversation with system and user messages
messages = [
    SystemMessage(content="You are a helpful coding assistant specialized in Python."),
    HumanMessage(content="Write a recursive Fibonacci function with memoization.")
]

# Invoke the model
response = chat_model.invoke(messages)
print(response.content[:200])