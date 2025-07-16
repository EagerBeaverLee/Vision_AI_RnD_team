from langchain_ollama import OllamaLLM

# Initialize the LLM with specific options
llm = OllamaLLM(
    model="qwen3:0.6b",
)

# Generate text from a prompt
text = """
Write a quick sort algorithm in Python with detailed comments:
```python
def quicksort(
"""

response = llm.invoke(text)
print(response[:500])


# for chunk in llm.stream("Explain quantum computing in three sentences:"):
#     print(chunk, end="", flush=True)