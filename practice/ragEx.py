from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
import numpy as np

# Initialize components
embeddings = OllamaEmbeddings(model="nomic-embed-text")
chat_model = ChatOllama(model="qwen3:0.6b", temperature=0.3)

# Sample knowledge base representing project documentation
documents = [
    Document(page_content="Python is a high-level programming language known for its simplicity and readability."),
    Document(page_content="Machine learning algorithms can automatically learn patterns from data without explicit programming."),
    Document(page_content="Data preprocessing involves cleaning, changing, and organizing raw data for analysis."),
    Document(page_content="Neural networks are computational models inspired by biological brain networks."),
]

# Create embeddings for all documents
doc_embeddings = embeddings.embed_documents([doc.page_content for doc in documents])

def similarity_search(query, top_k=2):
    """Find the most relevant documents for a query"""
    query_embedding = embeddings.embed_query(query)

    # Calculate cosine similarities
    similarities = []
    for doc_emb in doc_embeddings:
        similarity = np.dot(query_embedding, doc_emb) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(doc_emb)
        )
        similarities.append(similarity)

    # Get top-k most similar documents
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    return [documents[i] for i in top_indices]

# Create RAG prompt template
rag_prompt = PromptTemplate.from_template("""
Use the following context to answer the question. If the answer isn't in the context, say so.

Context:
{context}

Question: {question}

Answer:
""")

def answer_question(question):
    """Generate an answer using retrieved context"""
    # Retrieve relevant documents
    relevant_docs = similarity_search(question, top_k=2)
    context = "\n".join([doc.page_content for doc in relevant_docs])

    # Generate answer using context
    prompt_text = rag_prompt.format(context=context, question=question)
    response = chat_model.invoke([{"role": "user", "content": prompt_text}])

    return response.content, relevant_docs

# Test the RAG system
question = "What makes Python popular for data science?"
answer, sources = answer_question(question)

print(f"Question: {question}")
print(f"Answer: {answer}")
print(f"Sources: {[doc.page_content[:50] + '...' for doc in sources]}")
