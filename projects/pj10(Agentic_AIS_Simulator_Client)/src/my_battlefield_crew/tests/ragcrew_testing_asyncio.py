import os
import json
import asyncio
import pandas as pd
from typing import Dict, List, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from crews.rag_crew import RAGCrew

## test if together ai model can be used
from dotenv import load_dotenv
from langchain_together import ChatTogether

load_dotenv()

class RagEvaluationResult(BaseModel):
    final_result: str = Field(description="최종 판정 결과 (PASS 또는 FAIL)")
    reason: str = Field(description="판정 결과에 대한 간략한 사유")

# 2. report_data 직렬화 기반 검증 함수
def evaluate_response(question: str, agent_answer: str, eval_points: List[str]) -> Dict[str, Any] :
    """
    Agent의 답변과 eval_points를 비교하여 PASS/FAIL을 채점합니다.
    """

    # evaluator_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0) #openai API 사용시
    # evaluator_llm = ChatTogether(
    #     model="openai/gpt-oss-120b",  # Together AI 전용 모델 ID (접두사 없음)
    #     together_api_key=os.getenv("TOGETHER_API_KEY"),    # 발급받은 Together API Key 문자열 직접 입력
    #     temperature=0
    # )

    evaluator_llm = ChatOpenAI(
        model="accounts/fireworks/models/gpt-oss-120b",  # Fireworks AI 모델 ID (fireworks_ai/ 접두사 제거)
        api_key=os.getenv("FIREWORKS_API_KEY"),
        base_url="https://api.fireworks.ai/inference/v1",
        temperature=0,
        # max_tokens=2048,  # 사유 짤림 방지
        max_retries=3
    )
    structured_evaluator = evaluator_llm.with_structured_output(RagEvaluationResult)

    formatted_points = "\n".join([f"- {pt}" for pt in eval_points])

    eval_prompt = f"""
    너는 RAG 시스템 답변의 핵심 맥락을 채점하는 평가자(evaluator)이다. 
    목표는 Agent의 답변이 '사용자 질문의 의도'에 부합하고 '안전상 치명적인 오류'가 없는지 판단하여 PASS 또는 FAIL을 부여하는 것이다.
    reason에 관련된 답벼은 반드시 한글로 써야해! 

    [PASS 기준]
    - 답변이 완벽하지 않거나, 숫자가 틀리거나, 특정 단어나 핵심 포인트가 빠져있어도 문제 상황에 도움이 되는 답변이라고 판단되면 되도록이면 PASS로 인정한다.

    [FAIL을 부여 기준]
    - [환각/오답]: 질문의 핵심 맥락과 완전히 반대되는 잘못된 정보나 위험한 조치 방법을 안내하는 경우.
    - [완전히 엉뚱한 답변]: 질문에서 요구한 핵심 문제 상황을 무시하고 완전히 엉뚱한 주제를 답변하는 경우.
    - [내용 회피]: "알 수 없습니다", "정보가 없습니다" 등 유용한 정보를 전혀 제공하지 못한 경우.

    --------------------------------------------------
    [사용자 질문]:
    {question}

    [RAG 핵심 평가 포인트]:
    {formatted_points}

    [Agent가 생성한 답변]
    {agent_answer}
    --------------------------------------------------
    """
    return structured_evaluator.invoke(eval_prompt)
    
# ---------------------------------------------------------------------------
# 2. 통합 평가 자동화 스크립트 메인 함수(비동기 처리)
# ---------------------------------------------------------------------------
async def process_single_query(
        idx: int, 
        total_count: int, 
        user_query: str,
        agent_answer:str,
        eval_points: str,
        semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """단일 쿼리에 대한 RAGCrew 실행 및 평가 수행 함수"""
    test_result: Dict[str, Any] ={
        "Query": user_query,
        "Agent_answer": "",
        "Evaluation_Points": eval_points,
        "hallucination_pass": "FAIL",
        "reason": ""
    }
    async with semaphore:

        try:
            # 1. RAGCrew 비동기 실행
            rag_crew = RAGCrew()

            rag_output = await rag_crew.crew().kickoff_async(
                inputs={"user_question": user_query}
            )

            generated_answer = rag_output.raw

            test_result["Agent_answer"] = generated_answer

            rag_evaluation = evaluate_response(user_query, generated_answer, eval_points)

            test_result["hallucination_pass"] = rag_evaluation.final_result
            test_result["reason"] = rag_evaluation.reason

            if rag_evaluation.final_result == "PASS":
                log_fact = f"🧐 [Hallucination-Check] ✅ 통과"
                log_reason = rag_evaluation.reason
            else:
                log_fact = f"🧐 [Hallucination-Check] ❌ 실패 - {rag_evaluation.reason}"
                log_reason = rag_evaluation.reason

            # 중간 결과 출력
            print(f"\n[테스트 {idx}/{total_count}] \"{user_query[:30]}\"\n  ├  {log_fact} ├  {log_reason}")
            

        except Exception as e:
            print(f"\n[테스트 {idx}/{total_count}] \"{user_query[:30]}\"\n  └ ⚠️ [오류 발생]: {e}")
            test_result["reason"] = f"Pipeline Execution Error: {str(e)}"
        
        return test_result

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_PATH = os.path.join(CURRENT_DIR, "rag_parallel_eval_results.csv" )

async def run_parallel_benchmark(json_path: str, 
                                 max_concurrency: int = 7,
                                 output_csv_path: str = DEFAULT_OUTPUT_PATH) -> List[Dict[str, Any]]:
    """
    JSON 파일 경로를 입력받아 데이터를 로드한 뒤, 질문별 RAG 수행 및 병렬로 결과 평가
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except Exception as e:
        print(f"❌ JSON 파일 로드 실패: {e}")
        return []

    total_count = len(dataset)
    semaphore = asyncio.Semaphore(max_concurrency) 

    print(f" 🚀 총 {total_count}개 질문 로드 완료.")
    print(f"최대 동시 처리 게수: {max_concurrency}개로 비동기 Benchmark 시작 \n")


    tasks = [
        process_single_query(
            idx=i+1, 
            total_count=total_count, 
            user_query=item["question"], 
            agent_answer="",
            eval_points=item["eval_points"],
            semaphore=semaphore
            )
            for i, item in enumerate(dataset)
        ]

    # 2. 모든 작업 동시 실행 및 결과 수집
    evaluation_logs = await asyncio.gather(*tasks)

    # 3. 최종 결과 집계
    hallucination_pass_count = sum(1 for log in evaluation_logs if log["hallucination_pass"]=="PASS")
    fail_count = total_count - hallucination_pass_count

    print("\n" + "="*85)
    print("📊 [최종 평가 보고서]")
    print(f" • 총 테스트 수: {total_count}")
    print(f" • 통과 (PASS): {hallucination_pass_count}개")
    print(f" • 실패 (FAIL): {fail_count}개")
    print(f" • 환각 검증 통과율: {hallucination_pass_count}/{total_count} ({hallucination_pass_count/total_count*100:.1f}%)")
    print("="*85 + "\n")

    fail_cases = [log for log in evaluation_logs if log["hallucination_pass"]=="FAIL"]

    print("\n" + "="*85)
    print(f"[실패케이스 분석] (총 {len(fail_cases)}건)")
    print("\n" + "="*85)

    if not fail_cases:
        print("🎉 실패한 케이스가 없습니다!\n")
    else:
        for idx, case in enumerate(fail_cases, 1):
            print(f"\n[{idx}]질문: {case['Query']}")
            print(f"[상태]: {case['hallucination_pass']}")
            print(f"[사유]: {case['reason']}")    

    df = pd.DataFrame(evaluation_logs)
    df.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ CSV 파일 저장 완료: {output_csv_path}")

    return evaluation_logs

if __name__ == "__main__":

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(BASE_DIR, "..", "data", "doctrine_data", "rag_evaluation_data", "ragcrew_evaluation_dataset.json")
    # json_path = os.path.join(BASE_DIR, "..", "data", "doctrine_data", "rag_evaluation_data", "rag_eval_temp_data.json")
    json_path = os.path.abspath(json_path)
    print(json_path)

    asyncio.run(run_parallel_benchmark(
        json_path=json_path
    ))















