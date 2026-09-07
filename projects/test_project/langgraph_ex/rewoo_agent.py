import re
from langchain_openai import ChatOpenAI, OpenAIEmbeddings as emb
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate

from typing import TypedDict, List, Dict, Any, Annotated
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_community.vectorstores import FAISS

class RewooAgent():

    local_llm = ChatOpenAI(
        api_key="ai",
        model="openai/gpt-oss-20b",
        base_url="http://192.168.0.110:8000/v1",
        temperature=0,
        max_tokens=6000
    )
    # ==========================================
    # 1. 툴(Tools) 정의 및 모델 바인딩
    # ==========================================

    @tool
    def VectorDB(query: str) -> str:
        """Use this to search the military doctrine vectorstore. Input must be a concise semantic search query."""
        embedding = emb(
            model="text-embedding-3-small",
            api_key="실제 키 입력"
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
        ("system", """You are a planning module that breaks down a given task into sequential evidence collection and reasoning steps.
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
            {task}
            """ ),
        ("human", "Task: {task}")
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