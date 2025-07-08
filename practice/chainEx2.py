from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import json

# Create a structured prompt template
prompt = PromptTemplate.from_template("""
You are an expert educator.
Explain the following concept in simple terms that a beginner would understand.
Make sure to provide:
1. A clear definition
2. A real-world analogy
3. A practical example

Concept: {concept}
""")

# Create a parser that extracts structured data
class JsonOutputParser:
    def parse(self, text):
        try:
            # Find JSON blocks in the text
            if "```json" in text and "```" in text.split("```json")[1]:
                json_str = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            # Try to parse the whole text as JSON
            return json.loads(text)
        except:
            # Fall back to returning the raw text
            return {"raw_output": text}

# Initialize a model instance to be used in the chain
llm = OllamaLLM(model="qwen3:0.6b")

# Build a more complex chain
chain = (
    {"concept": RunnablePassthrough()} 
    | prompt 
    | llm 
    | StrOutputParser()
)

# Execute the chain with detailed tracking
result = chain.invoke("Recursive neural networks")
print(result[:500])