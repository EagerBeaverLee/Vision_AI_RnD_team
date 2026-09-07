from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from operator import itemgetter
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader


class naiveRAG:
    def __init__(self, embedding):
        self.embedding = embedding

    def build_vectorstore(self):
        save_vector_path = "./north_korean_tactics_faiss_ragas"

        load_file = "./North_Korean_Tactics.pdf"
        loader = PyPDFLoader(load_file)

        chunks = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=500).split_documents(loader.load())
        vectorstore = FAISS.from_documents(chunks, self.embedding)
        vectorstore.save_local(save_vector_path)
        retriever = vectorstore.as_retriever()
        return retriever


    def retrieve(self):
        save_vector = "./north_korean_tactics_faiss_new"
        vectorstore = FAISS.load_local(save_vector, self.embedding, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever()

        return retriever
    
    def ragas_retrieve(self):
        save_vector = "./north_korean_tactics_faiss_ragas"
        vectorstore = FAISS.load_local(save_vector, self.embedding, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever()

        return retriever
    
    def build_chain(self):
        retriever = self.retrieve()

        llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=0,
        )

        pull = """
            You are a helpful and highly accurate assistant for question-answering tasks.
            Your primary task is to answer the user's question based strictly on the provided Context.

            CRITICAL INSTRUCTIONS:
            1. Grounding: Use ONLY the information provided in the Context. Do not use your pre-trained outside knowledge or fabricate any information.
            2. Fallback: If the provided Context does not contain the information needed to answer the question, answer using the knowledge you possess.
            3. Adaptive Detail: Match the length and detail of your answer to the complexity of the user's question. If the question requires a comprehensive explanation, provide a detailed response. If it asks for a simple fact, keep it concise
        """
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", pull),
                ("human", "Question: {question}, Context: {context} "),
            ]
        )

        # Chain
        chain = (
            RunnablePassthrough.assign(context = itemgetter("question") | retriever)            
            | prompt
            | llm
            | StrOutputParser()            
        )

        return chain
