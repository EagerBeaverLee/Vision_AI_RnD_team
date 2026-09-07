emb# 🔥 [🚨 필수 패치] Ragas 0.4.x의 최신 LangChain 호환성 버그 우회
# 다른 어떤 모듈(ragas, langchain 등)을 import 하기 전에 "가장 먼저" 실행되어야 합니다.
import sys
from unittest.mock import MagicMock

# Ragas 내부에서 찾으려고 떼쓰는 낡은 버텍스AI 경로를 가짜 모듈로 채워줍니다.
sys.modules['langchain_community.chat_models.vertexai'] = MagicMock()
sys.modules['langchain_community.llms.vertexai'] = MagicMock()

import asyncio
import pandas as pd
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings as emb
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings, OpenAIEmbeddings
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall
)

async def run_local_ragas_evaluation():
    local_llm = ChatOpenAI(
        api_key="ai",
        model="openai/gpt-oss-20b",
        base_url="http://192.168.0.110:8000/v1",
        temperature=0,
    )
    vllm_client = AsyncOpenAI(
        base_url="http://192.168.0.110:8000/v1", 
        api_key="ai"           
    )

    real_openai_client = AsyncOpenAI(
        api_key="실제 키 입력" 
    )
    
    # 2. ⭕ llm_factory에 vllm 클라이언트를 주입하여 InstructorLLM 요구 조건 충족
    judge_llm = llm_factory(
        model="openai/gpt-oss-20b",          # vLLM에 로드된 LLM 모델명
        client=vllm_client,
        max_tokens=6000,
        temperature=0
    )
    
    # 2. vLLM 서버를 바라보는 LangChain Embeddings 객체 생성 (임베딩 담당)
    # (만약 임베딩은 다른 모델을 쓰신다면 해당 LangChain 임베딩 객체를 넣으시면 됩니다)
    # judge_embeddings = HuggingFaceEmbeddings(
    #     model="BAAI/bge-small-en-v1.5"
    # )
    judge_embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        client = real_openai_client,
    )

    
    # 4. 메트릭 객체 초기화 및 래핑된 모델 주입
    metrics = {
        "Faithfulness": Faithfulness(llm=judge_llm),
        "Answer Relevance": AnswerRelevancy(llm=judge_llm, embeddings=judge_embeddings),
        "Context Precision": ContextPrecision(llm=judge_llm),
        "Context Recall": ContextRecall(llm=judge_llm)
    }
    query = "How do action and enabling units differ in function, risk, and mission task allocation during planning?"
    answer = "Action units are responsible for performing the primary task that accomplishes the overall mission objective, such as assaulting an enemy or seizing terrain. Enabling units, on the other hand, support the action unit by creating conditions that allow the action unit to operate successfully; their activities are based on their assigned supporting mission tasks and can change as tactical opportunities arise.\n\nIn terms of risk, enabling units may be required to operate at significant risk and may sustain substantial casualties to create opportunities for the action unit, even though they may not always make direct contact with the enemy. Action units typically face direct risk as they execute the main mission task.\n\nDuring planning, mission tasks are allocated by first identifying the action function (the main task) and the enabling functions (supporting tasks), then allocating resources accordingly. Action units are given tasks directly tied to achieving the mission objective, while enabling units are assigned tasks that support or facilitate the action unit’s success."

    embedding = emb(
        model="text-embedding-3-small",
        api_key="실제 키 입력"
    )
    save_vector = "./north_korean_tactics_faiss_new"
    vectorstore = FAISS.load_local(save_vector, embedding, allow_dangerous_deserialization=True)
    retriever = vectorstore.as_retriever()
    docs = retriever.invoke(query)
    retrieved_contexts_text = [doc.page_content for doc in docs]
    context = "\n\n".join(retrieved_contexts_text)

    # 2. 컨텍스트 기반 답변 생성 프롬프트
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert military analyst. Answer the user's question accurately using ONLY the provided context document pieces. If the context lacks information, do your best with given facts."),
        ("human", "Context:\n{context}\n\nQuestion: {query}")
    ])

    naive_chain = prompt | local_llm
    response = naive_chain.invoke({"context": context, "query": query})
    
    # 5. 평가 데이터셋 (Ragas v0.4 신규 스키마 반영)
    eval_samples = [
        {
            "user_input": query,
            "response": response.content,
            "retrieved_contexts": retrieved_contexts_text,
            "reference": answer
        }
    ]
    
    evaluation_output = []
    
    # 6. 비동기 평가 수행 루프
    for i, sample in enumerate(eval_samples):
        print(f"🔄 로컬 vLLM 모델로 샘플 {i+1} 채점 중...")
        row_results = {"User Input": sample["user_input"]}
        
        for metric_name, metric_obj in metrics.items():
            try:
                # 🌟 [수정된 부분] 메트릭 종류에 따라 필요한 인자만 골라서 넘겨줍니다!
                if metric_name == "Faithfulness":
                    metric_result = await metric_obj.ascore(
                        user_input=sample["user_input"],
                        response=sample["response"],
                        retrieved_contexts=sample["retrieved_contexts"]
                        # reference 없음
                    )
                elif metric_name == "Answer Relevance":
                    metric_result = await metric_obj.ascore(
                        user_input=sample["user_input"],
                        response=sample["response"]
                        # retrieved_contexts, reference 없음
                    )
                elif metric_name in ["Context Precision", "Context Recall"]:
                    metric_result = await metric_obj.ascore(
                        user_input=sample["user_input"],
                        retrieved_contexts=sample["retrieved_contexts"],
                        reference=sample["reference"]
                        # response 없음
                    )
                else:
                    raise ValueError(f"알 수 없는 메트릭: {metric_name}")
                
                row_results[metric_name] = round(metric_result.value, 4)
            except Exception as e:
                print(f"❌ [{metric_name}] 평가 중 에러 발생: {e}")
                row_results[metric_name] = None
                
        evaluation_output.append(row_results)
        
    # 7. 결과 출력
    print("\n📊 ==================== vLLM 기반 Ragas 평가 결과 ====================")
    for i, row in enumerate(evaluation_output):
        print(f"\n[ 샘플 {i+1} 상세 결과 ]")
        for key, value in row.items():
            # 점수와 텍스트를 보기 좋게 정렬해서 출력
            print(f" 🔹 {key:<18} : {value}")

if __name__ == "__main__":
    asyncio.run(run_local_ragas_evaluation())