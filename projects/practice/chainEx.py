from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import OllamaEmbeddings
import numpy as np
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

chain = (
    {"concept": RunnablePassthrough()} 
    | prompt 
    | llm 
    | StrOutputParser()
)

# Execute the chain with detailed tracking
# result = chain.invoke("Recursive neural networks")
# print(result[:500])

embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://localhost:11434",
)

query = "How do neural networks learn?"
query_embedding = embeddings.embed_query(query)
# print(f"Embedding dimension: {len(query_embedding)}")

documents = [
    "Neural networks learn through backpropagation",
    "Transformers use attention mechanisms",
    "LLMs are trained on text data"
]

doc_embeddings = embeddings.embed_documents(documents)

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Find most similar document to query
similarities = [cosine_similarity(query_embedding, doc_emb) for doc_emb in doc_embeddings]
most_similar_idx = np.argmax(similarities)
print(f"Most similar document: {documents[most_similar_idx]}")
print(f"Similarity score: {similarities[most_similar_idx]:.3f}")