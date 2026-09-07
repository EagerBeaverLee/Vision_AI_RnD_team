# =====================================================================
# 🔥 [1단계. 필수 패치] Ragas 최신버전의 랭체인 레거시 경로 버그 우회
import sys, traceback
import os
from unittest.mock import MagicMock
sys.modules['langchain_community.chat_models.vertexai'] = MagicMock()
sys.modules['langchain_community.llms.vertexai'] = MagicMock()
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# =====================================================================

import json, re
import asyncio
import pandas as pd
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings as emb
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
# Ragas 0.4.x Collections 지표 및 임베딩
from ragas.llms import llm_factory
from ragas.embeddings import OpenAIEmbeddings
from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextRecall

from typing import TypedDict, List, Dict, Any, Annotated
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_community.vectorstores import FAISS

local_llm = ChatOpenAI(
    # api_key="ai",
    # model="openai/gpt-oss-20b",
    # base_url="http://192.168.0.110:8000/v1",
    # temperature=0,
    api_key="ai",
    # model="meta-llama/Llama-3.1-8B-Instruct",
    model="unsloth/gemma-3-27b-it-bnb-4bit",
    # model="google/gemma-2-9b-it",
    # model="Qwen/Qwen2-7B-Instruct",
    # model="mistralai/Mistral-7B-Instruct-v0.3",
    base_url="http://192.168.0.110:8001/v1",
    temperature=0,
    max_tokens=3000
)

# ==========================================
# 1. 툴(Tools) 정의 및 모델 바인딩
# ==========================================

@tool
def VectorDB(query: str) -> str:
    """Use this to search the military doctrine vectorstore. Input must be a concise semantic search query."""
    embedding = emb(
        model="text-embedding-3-small",
        
    )
    save_vector = "./north_korean_tactics_faiss_new"
    vectorstore = FAISS.load_local(save_vector, embedding, allow_dangerous_deserialization=True)
    retriever = vectorstore.as_retriever()
    print(f"[VectorDB 결과] '{query}'에 대한 군사 교리 내용 수집 완료.")
    docs = retriever.invoke(query)
    combined_text = "\n\n".join([clean_text(doc.page_content) for doc in docs if doc.page_content])
    return combined_text

@tool
def LLM(instruction: str) -> str:
    """Use this to reason, summarize, extract, or synthesize information. Input must be a clear instruction."""
    print(f"[LLM 추론 결과] 지시사항('{instruction}')에 대한 추론 및 요약 완료.")
    return local_llm.invoke(instruction).content

#vectorstore결과 특수문자 후처리
def clean_text(text: str) -> str:
    if not text:
        return ""
    # 1. 이상한 불릿 기호( 등) 및 깨진 특수문자 제거
    text = re.sub(r'[^\w\s\d.,?!:\-\(\)\[\]\/\"\'\%]', ' ', text)
    # 2. 문서 '내부'의 연속된 줄바꿈/공백을 단일 공백으로 치환
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
    

# 사용할 툴 리스트 등록
tools = [VectorDB, LLM]

# 유저님의 모델에 툴을 바인딩합니다.
# model_with_tools는 이제 일반 텍스트 대신 tool_calls를 반환할 수 있게 됩니다.
model_with_tools = local_llm.bind_tools(tools)


# ==========================================
# 2. 그래프 State 정의 (messages 추가)
# ==========================================

class TaskStepSpec(BaseModel):
    plan: str
    evidence_id: str
    tool: str
    tool_input: str

class ReWOOPlanSpec(BaseModel):
    steps: List[TaskStepSpec]

class ReWOOState(TypedDict):
    task: str
    steps: List[Dict[str, Any]]
    results: Dict[str, str]
    current_step_idx: int
    final_answer: str
    # ToolNode와 연동하기 위해 메시지 내역을 상태에 포함시킵니다.
    messages: Annotated[List[AnyMessage], add_messages]


# ==========================================
# 3. 보조 함수 (이전 증거 치환)
# ==========================================

def substitute_evidence(text: str, results: Dict[str, str]) -> str:
    for eq_id, val in results.items():
        text = text.replace(eq_id, str(val))
    return text


# ==========================================
# 4. LangGraph 노드(Nodes) 리팩토링
# ==========================================

planner_chain = ChatPromptTemplate.from_messages([
    ("human", """You are a planning module that breaks down a given task into sequential evidence collection and reasoning steps.
        Your task:
        Create a step-by-step plan to answer the given question. Each step must specify:
        - a detailed natural-language plan
        - one evidence variable ID
        - one external tool
        - one tool input
        
        Available tools:
        1. VectorDB
        Use this to search a vectorstore containing embedded military doctrines, field manuals, and related doctrinal references.
        Use VectorDB when the step requires doctrinal evidence, definitions, concepts, tactics, operational methods, terminology, or source-grounded military information.
        The tool_input must be a concise semantic search query.
        
        2. LLM
        Use this to reason over previous evidence, summarize retrieved evidence, extract definitions or lists, compare concepts, or synthesize the final answer.
        The tool_input must be a clear instruction. It may refer to previous evidence variables such as #E1 or #E2.
        
        Output requirements:
        - Return only the structured output object expected by the schema.
        - Do not include markdown.
        - Do not include explanations outside the object.
        - The top-level object must contain a field named steps.
        - steps must be a non-empty list.
        - Create enough steps to fully answer the task.
        - Each step must contain exactly these fields:
          - plan
          - evidence_id
          - tool
          - tool_input
        - evidence_id must start at #E1 and increment by 1 for each step: #E1, #E2, #E3, ...
        - Each step must have exactly one evidence_id.
        - tool must be exactly one of:
          - VectorDB
          - LLM
        - Do not use any other tool name.
        - Do not use Google, Search, Browser, Calculator, WolframAlpha, Python, DoctrineSearch, Vectorstore, or any other tool name.
        - plan must not be empty.
        - tool_input must not be empty.
        - Never return an empty steps list.
        
        Planning rules:
        - For military or doctrine-related tasks, use VectorDB before LLM.
        - Use VectorDB to gather source evidence.
        - Use LLM to extract, compare, reason, or synthesize from evidence.
        - The final step should usually be an LLM step that directly answers the task using the previous evidence.
        - If the task asks to compare two concepts, search for each concept separately, then use LLM to compare them.
        - If the task asks for a definition or list, one VectorDB search and one or two LLM extraction/final-answer steps are enough.
        - If the task has multiple dimensions, such as terrain, timing, enemy vulnerabilities, function, risk, coordination, or control requirements, search for the main dimensions separately when useful.
        - Keep the plan focused on the user question. Do not search for the opposite actor or reverse the direction of the question.
        - Do not assume the answer in the plan. Search for evidence first, then extract or synthesize from it.
        - Use broad semantic search queries rather than exact quoted phrases.
        - Do not put quotation marks around VectorDB search queries unless the exact phrase itself is essential.
        - Tool inputs for VectorDB should include the key military concept, actor, and requested comparison or dimension.
        - Tool inputs for LLM should explicitly say which evidence variables to use.
        
        Good VectorDB query style:
        - action unit doctrine function risk task organization planning
        - enabling unit doctrine support function mission allocation planning
        - North Korea terrain exploitation technological inferiority mountains tunnels concealment doctrine
        - North Korea adaptive operations disrupt enemy command control communications logistics infiltration
        - PMESII-PT operational variables doctrine
        - kill box joint fires airspace control fire support coordination dimensions
        
        Bad VectorDB query style:
        - "action unit" doctrine definition
        - EIW doctrine
        - tech-superior coalition C2 disruption tactics, when the question asks how North Korea disrupts enemy C2
        - hometown of #E2
        - using #E1 summarize the evidence
        
        Example task:
        Compare the roles of fixing drills and EIW in restricting enemy movement and influencing decisions.
        
        Example structured output:
        {{
          "steps": [
            {{
              "plan": "Search the doctrine vectorstore for passages defining fixing drills and explaining how they are used to fix, restrict, or shape enemy movement during operations.",
              "evidence_id": "#E1",
              "tool": "VectorDB",
              "tool_input": "fixing drills doctrine fix enemy restrict movement influence decision making"
            }},
            {{
              "plan": "Search the doctrine vectorstore for passages defining EIW and explaining how it affects enemy movement, decision-making, command and control, or operational behavior.",
              "evidence_id": "#E2",
              "tool": "VectorDB",
              "tool_input": "EIW doctrine definition restrict enemy movement influence decisions command control"
            }},
            {{
              "plan": "Compare the doctrinal roles of fixing drills and EIW using the retrieved evidence, focusing on how each restricts enemy movement and influences enemy decisions.",
              "evidence_id": "#E3",
              "tool": "LLM",
              "tool_input": "Using #E1 and #E2, compare fixing drills and EIW in how they restrict enemy movement and influence enemy decisions."
            }},
            {{
              "plan": "Produce a concise final answer that directly addresses the question and summarizes the key similarities and differences between fixing drills and EIW.",
              "evidence_id": "#E4",
              "tool": "LLM",
              "tool_input": "Using #E3, provide the final answer comparing the roles of fixing drills and EIW in restricting enemy movement and influencing decisions."
            }}
          ]
        }}
        
        Now create a structured plan for the task below.
        
        Task:
        {task}""")
]) | local_llm.with_structured_output(ReWOOPlanSpec)

def plan_node(state: ReWOOState) -> dict:
    print("🤖 [Node: Plan] 계획 수립 중...")
    response = planner_chain.invoke({"task": state["task"]})
    #plan 내용 디버깅
    plans = [
        f"plan: {step.plan}\n{step.evidence_id} = {step.tool}[{step.tool_input}]\n\n"
        for step in response.steps
    ]
    print("\n".join(plans))
    ###
    steps_dict = [step.model_dump() for step in response.steps]
    return {"steps": steps_dict, "current_step_idx": 0, "results": {}, "messages": []}


def execute_node(state: ReWOOState) -> dict:
    """[변경] 직접 실행하지 않고, 바인딩된 모델에게 툴 호출(tool_calls)을 유도합니다."""
    idx = state["current_step_idx"]
    step = state["steps"][idx]
    
    # 예: #E1 결과를 뒤단계 쿼리에 주입
    resolved_input = substitute_evidence(step["tool_input"], state["results"])
    
    print(f"⚙️ [Node: Execute] 모델에게 {step['tool']} 호출 요청 중... ({step['evidence_id']})")
    
    # 모델에게 플래너가 지정한 툴과 입력값을 강제로 매칭하여 실행하도록 컨텍스트를 줍니다.
    prompt = f"""You must execute the current plan step.
    Plan Description: {step['plan']}
    Required Tool: {step['tool']}
    Argument/Input: {resolved_input}
    
    Call the designated tool with the provided argument immediately."""

    # 툴이 바인딩된 모델을 호출하면 내부적으로 tool_calls가 담긴 AIMessage가 반환됩니다.
    ai_message = model_with_tools.invoke(prompt)
    
    # 이 메시지를 리턴하면 상태의 messages에 추가되어 다음 노드인 ToolNode가 읽을 수 있게 됩니다.
    return {"messages": [ai_message]}


def post_execute_node(state: ReWOOState) -> dict:
    """[추가] ToolNode가 실행한 결과를 ReWOO의 변수(#E) 스토어에 매핑합니다."""
    idx = state["current_step_idx"]
    step = state["steps"][idx]
    evidence_id = step["evidence_id"]
    
    # ToolNode가 실행을 마치면 최신 메시지(messages[-1])에 ToolMessage가 들어옵니다.
    tool_message = state["messages"][-1]
    tool_result = tool_message.content
    
    print(f"✅ [Node: Post-Execute] {evidence_id} 결과 저장 완료.")
    
    updated_results = {**state["results"], evidence_id: tool_result}
    
    return {
        "results": updated_results,
        "current_step_idx": idx + 1 # 다음 단계 스텝으로 인덱스 전환
    }


def should_continue(state: ReWOOState) -> str:
    if state["current_step_idx"] < len(state["steps"]):
        return "continue"
    return "end"


def final_answer_node(state: ReWOOState) -> dict:
    print("📝 [Node: Final Answer] 최종 답변 정리 중...")
    last_evidence_id = f"#E{len(state['steps'])}"
    final_raw_result = state["results"].get(last_evidence_id, "답변 생성 실패")
    return {"final_answer": final_raw_result}


# ==========================================
# 5. 워크플로우 그래프 빌드 (ToolNode 배치)
# ==========================================

workflow = StateGraph(ReWOOState)

# 전역 ToolNode 선언 (생성해 둔 툴 리스트 주입)
standard_tool_node = ToolNode(tools)

# 노드 등록
workflow.add_node("planner", plan_node)
workflow.add_node("executor", execute_node)
workflow.add_node("tools", standard_tool_node) # 👈 랭그래프 Prebuilt 툴 노드
workflow.add_node("post_executor", post_execute_node)
workflow.add_node("final_compiler", final_answer_node)

# 에지 연결 흐름 변경
workflow.add_edge(START, "planner")
workflow.add_edge("planner", "executor")
workflow.add_edge("executor", "tools")         # 1. 모델이 tool_call 뱉으면 -> 툴 노드로
workflow.add_edge("tools", "post_executor")   # 2. 툴 노드가 실행 완료하면 -> 사후 처리 노드로

# 루프 분기점 위치 변경 (사후 처리 노드 끝난 후 체크)
workflow.add_conditional_edges(
    "post_executor",
    should_continue,
    {
        "continue": "executor",
        "end": "final_compiler"
    }
)

workflow.add_edge("final_compiler", END)
rewoo_agent = workflow.compile()

# =====================================================================
# 🛠️ [유틸리티] ReWOO 상태에서 컨텍스트 리스트 추출
# =====================================================================
def extract_rewoo_contexts(state: dict) -> list:
    """ReWOO 플래너가 도구를 사용해 수집한 결과(텍스트)들을 추출합니다."""
    contexts = []
    results_dict = state.get("results", {})
    
    for tool_output in results_dict.values():
        if tool_output is None:
            continue

        # 1. 문자열인 경우 공백 제거 후 내용이 있을 때만 추가
        if isinstance(tool_output, str):
            cleaned = tool_output.strip()
            if cleaned:
                contexts.append(cleaned)
        # 2. 숫자나 기타 타입으로 결과가 들어왔을 경우 문자열로 변환 후 추가
        else:
            str_val = str(tool_output).strip()
            if str_val:
                contexts.append(str_val)
            
    return list(set(contexts))

# =====================================================================
# ⚡ [단일 샘플 평가 태스크] Naive vs ReWOO
# =====================================================================
async def evaluate_single_sample(index, item, retriever, naive_rag, rewoo_agent, metrics, semaphore):
    query = item.get("input")
    ground_truth = item.get("expected_output")
    
    row_result = {
        "ID": index + 1, "Question": query, "Ground Truth": ground_truth,
        "Naive_Response": None, "Naive_Faithfulness": None, "Naive_Answer_Relevance": None, "Naive_Context_Recall": None,
        "ReWOO_Response": None, "ReWOO_Faithfulness": None, "ReWOO_Answer_Relevance": None, "ReWOO_Context_Recall": None
    }
    
    async with semaphore:
        try:
            # 🌟 [수정 1] gather로 동시에 쏘지 않고 하나씩 순차 수행하여 vLLM 과부하 방지
            
            # [A] Naive RAG 실행
            docs = await retriever.ainvoke(query)
            contexts_list = [clean_text(doc.page_content) for doc in docs]
            context_str = "\n".join(contexts_list)
            naive_res = await naive_rag.ainvoke({"context": context_str, "query": query})
            
            # response parsing
            if isinstance(naive_res, dict):
                naive_response = naive_res.get("answer", naive_res.get("text", str(naive_res)))
            else:
                naive_response = getattr(naive_res, "content", str(naive_res))

            # [B] ReWOO Agent 실행 (Naive가 끝난 후 호출하여 KV Cache 선점 방지)
            rewoo_state = await rewoo_agent.ainvoke({"task": query})
            rewoo_response = rewoo_state.get("final_answer")
            rewoo_contexts = extract_rewoo_contexts(rewoo_state)

            row_result["Naive_Response"] = naive_response
            row_result["ReWOO_Response"] = rewoo_response
            
        except Exception as e:
            print(f"❌ [샘플 {index+1}] RAG 시스템 구동 중 에러 발생: {e}")
            return row_result

        # -------------------------------------------------------------
        # [C] Ragas 지표 비동기 병렬 채점
        # -------------------------------------------------------------
        score_tasks = {}
        
        # Naive RAG 지표 예약
        if naive_response and contexts_list:
            score_tasks["N_F"] = metrics["Faithfulness"].ascore(user_input=query, response=naive_response, retrieved_contexts=contexts_list)
            score_tasks["N_A"] = metrics["Answer Relevance"].ascore(user_input=query, response=naive_response)
            score_tasks["N_C"] = metrics["Context Recall"].ascore(user_input=query, retrieved_contexts=contexts_list, reference=ground_truth)
            
        # ReWOO Agent 지표 예약
        if rewoo_response and rewoo_contexts:
            score_tasks["R_F"] = metrics["Faithfulness"].ascore(user_input=query, response=rewoo_response, retrieved_contexts=rewoo_contexts)
            score_tasks["R_A"] = metrics["Answer Relevance"].ascore(user_input=query, response=rewoo_response)
            score_tasks["R_C"] = metrics["Context Recall"].ascore(user_input=query, retrieved_contexts=rewoo_contexts, reference=ground_truth)
            
        # 모든 메트릭 평가를 한 방에 병렬 처리 (A6000의 힘 발휘!)
        if score_tasks:
            keys = list(score_tasks.keys())
            scores = await asyncio.gather(*score_tasks.values(), return_exceptions=True)
            score_map = dict(zip(keys, scores))
            
            def get_score(key):
                val = score_map.get(key)
                
                # 🌟 1. Ragas 평가 내부에서 Exception이 발생한 경우 (진짜 에러 원인 출력)
                if isinstance(val, Exception):
                    print("*" * 55)
                    print(f"💥 [ID:{index + 1}] 지표 '{key}' 평가 중 에러 발생!")
                    print(f"User Query: {query}")
                    print("-" * 55)
                    # Exception 객체(val) 안에 담긴 풀 스택 트레이스백을 출력합니다.
                    traceback.print_exception(type(val), val, val.__traceback__)
                    print("*" * 55)
                    return None

                # 🌟 2. 정상적으로 결과가 나온 경우 (.value 파싱)
                if val is not None:
                    try:
                        # MetricResult 객체인 경우 .value를 추출, 일반 수치면 그대로 사용
                        raw_val = getattr(val, "value", val)
                        if raw_val is not None:
                            return round(float(raw_val), 4)
                    except Exception as e:
                        print(f"\n💥 [ID:{index}] '{key}' 점수 float 변환 에러: {e}\n")
                        return None
                        
                # 3. val이 None인 경우
                return None

            row_result["Naive_Faithfulness"] = get_score("N_F")
            row_result["Naive_Answer_Relevance"] = get_score("N_A")
            row_result["Naive_Context_Recall"] = get_score("N_C")
            
            row_result["ReWOO_Faithfulness"] = get_score("R_F")
            row_result["ReWOO_Answer_Relevance"] = get_score("R_A")
            row_result["ReWOO_Context_Recall"] = get_score("R_C")

    print(f"✅ [진행 현황] 샘플 {index+1}번 평가 완료")
    return row_result


# =====================================================================
# 🏆 [메인 컨트롤러]
# =====================================================================
async def main_benchmark_process(retriever, naive_rag, rewoo_agent): # 🌟 retriever 파라미터 추가!
    file_path = "golden_answers_final_master_file.json"
    with open(file_path, "r", encoding="utf-8") as f:
        master_data = json.load(f)
    
    # 테스트 10개만
    master_data = master_data[:2]

    print(f"📊 총 {len(master_data)}개의 테스트 데이터셋을 로드했습니다.")
    
    # Ragas 평가 모델 세팅
    vllm_client = AsyncOpenAI(
        base_url="http://192.168.0.110:8000/v1",
        api_key="ai"
    )
    judge_llm = llm_factory(
        model="openai/gpt-oss-20b",
        client=vllm_client,
        max_tokens=25000,
        temperature=0
    )
    # judge_embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    
    real_openai_client = AsyncOpenAI(
        
    )

    judge_embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        client = real_openai_client,
    )
    
    metrics = {
        "Faithfulness": Faithfulness(llm=judge_llm),
        "Answer Relevance": AnswerRelevancy(llm=judge_llm, embeddings=judge_embeddings),
        "Context Recall": ContextRecall(llm=judge_llm)
    }
    
    semaphore = asyncio.Semaphore(10)
    
    tasks = [
        evaluate_single_sample(i, item, retriever, naive_rag, rewoo_agent, metrics, semaphore)
        for i, item in enumerate(master_data)
    ]
    
    print("🚀 모든 병렬 워커 활성화 완료. 로컬 vLLM 서버로 일괄 요청을 송신합니다...")
    results = await asyncio.gather(*tasks)
    
    # 저장 처리
    df_final = pd.DataFrame(results)
    json_path = "benchmark_gemma2_27b_4bit_test.json"
    # excel_path = "benchmark_llama_8b_naive.xlsx"
    
    df_final.to_json(json_path, orient="records", force_ascii=False, indent=4)
    # df_final.to_excel(excel_path, index=False)
    
    print("\n🎉 벤치마크 평가 완수 및 저장 완료!")
    
    print("\n📊 [최종 시스템별 평균 점수 요약]")
    summary_data = {
        "지표 (Metric)": ["Faithfulness", "Answer Relevance", "Context Recall"],
        "Naive RAG 평균": [
            df_final["Naive_Faithfulness"].mean(),
            df_final["Naive_Answer_Relevance"].mean(),
            df_final["Naive_Context_Recall"].mean()
        ],
        "ReWOO Agent 평균": [
            df_final["ReWOO_Faithfulness"].mean(),
            df_final["ReWOO_Answer_Relevance"].mean(),
            df_final["ReWOO_Context_Recall"].mean()
        ]
    }
    print(pd.DataFrame(summary_data).to_string(index=False))

embedding = emb(
    model="text-embedding-3-small",
    
)
save_vector = "./north_korean_tactics_faiss_new"
vectorstore = FAISS.load_local(save_vector, embedding, allow_dangerous_deserialization=True)
retriever = vectorstore.as_retriever()


# 2. 컨텍스트 기반 답변 생성 프롬프트
# prompt = ChatPromptTemplate.from_messages([
#     ("system", "You are a military analysis expert. Please answer the user's question accurately using only the provided contextual information. If the context is insufficient, try to give a plausible answer, but do not fabricate facts."),
#     ("human", "Context:\n{context}\n\nQuestion: {query}")
# ])

prompt = ChatPromptTemplate.from_messages([
    ("human", "You are a military analysis expert. Please answer the user's question accurately using only the provided contextual information. If the context is insufficient, try to give a plausible answer, but do not fabricate facts.\n\nContext:\n{context}\n\nQuestion: {query}")
])


naive_chain = prompt | local_llm

# [실행부 예시]
if __name__ == "__main__":
#     # retriever 객체를 파라미터로 함께 넘겨줍니다!
    asyncio.run(main_benchmark_process(
        retriever=retriever, 
        naive_rag=naive_chain, 
        rewoo_agent=rewoo_agent
    ))