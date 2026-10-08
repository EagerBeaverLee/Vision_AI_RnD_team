import json
import asyncio
from typing import Dict, List, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI # this is for using openai models (e.g., gpt-4o-mini, gpt-5-nano)
from crews.battlefield_router_crew import RouterCrew
from crews.battlefield_crew import BattlefieldCrew
from crews.battlefield_models import format_maritime_report

from tests.test_data_loading import test_dataset_loading


import random

##################### TEST-TEMP #############
import os
from langchain_together import ChatTogether
from dotenv import load_dotenv
load_dotenv()
##################### TEST-TEMP #############


class HallucinationCheckResult(BaseModel):
    is_hallucination_free: bool = Field(
        description="""
        지휘관 최종 답변(final_answer)이 정량 데이터의 핵심 사실을 왜곡하지 않고
        주요 수치가 부합하면 True, 명백한 데이터 창작이나 심각한 왜곡이 잇는 경우에만 False
        """
    )
    score: int = Field(
        description="""
        사실 부합성 및 신뢰도 점수 (10점 만점 기준; 0 ~ 10 사이).
        단순 요약이나 소수점 차이는 감점하지 않으며, 팩트가 부합하면 8점 이상을 부여할 것.
        """
    )
    reason: str = Field(
        description="""
        환각 판단 사유. 서론/부연 설명은 생략하고 '어느 항목의 숫자가 실제와 어떻게 다른지' 핵심 위주로 문장이 중간에 끊기지 않게 완결하여 작성하세요."""
    )

# 2. report_data 직렬화 기반 검증 함수
def check_report_hallucination(report_data) -> HallucinationCheckResult:
    """
    MaritimeSituationReport Pydantic 객체 내의 정량 데이터 구조체들과
    final_answer 간의 사실 부합성(환각 여부)을 검증하는 함수
    """
    # OPENAI 
    # evaluator_llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    #TOGETHER AI
    # evaluator_llm = ChatTogether( # this is for using gpt-oss-120b as evaluator from TOGETHER AI API
    #     model="openai/gpt-oss-120b",  # Together AI 전용 모델 ID (접두사 없음)
    #     together_api_key=os.getenv("TOGETHER_API_KEY"),    # 발급받은 Together API Key 문자열 직접 입력
    #     temperature=0,
    #     max_tokens=2048
    #     )

    #FIREWORKS AI
    evaluator_llm = ChatOpenAI(
            model="accounts/fireworks/models/gpt-oss-120b",  # Fireworks AI 모델 ID (fireworks_ai/ 접두사 제거)
            api_key=os.getenv("FIREWORKS_API_KEY"),
            base_url="https://api.fireworks.ai/inference/v1",
            temperature=0,
            max_tokens=2048,  # 사유 짤림 방지
            max_retries=3
        )

    structured_evaluator = evaluator_llm.with_structured_output(HallucinationCheckResult)

    # final_answer를 제외한 순수 정량 데이터들만 딕셔너리로 분리
    full_dict = report_data.model_dump()
    target_answer = full_dict.pop("final_answer", "")
    
    # 정량 데이터 구조체를 JSON 문자열로 변환 (Ground Truth)
    raw_fact_data = json.dumps(full_dict, ensure_ascii=False, indent=2)

    eval_prompt = f"""
        당신은 해상 전장 분석 시스템의 너그럽고 합리적인 'Fact-Checker (환각 검증관)'입니다.
        [지휘관 최종 답변 (final_answer)]이 [정량 분석 데이터 JSON(Ground Truth)]의 핵심 정보를 잘 반영하고 있는지 검증하세요.

        [환각 검증 패스(True) 기준 - 매우 중요]:
        1. **소수점 및 단위 표현**: 소수점 반올림, 버림, 약(approximate) 수치 표현은 절대 환각으로 판별하지 마세요. (예: 16.158 -> 16.16 또는 16.2 모두 수용)
        2. **요약 및 일부 누락**: 지휘관이 전체 데이터 중 주요 데이터(상위 몇 개)만 선별하여 요약 보고하는 것은 정상적인 동작입니다. 모든 항로/구역을 전부 나열하지 않았다고 해서 환각(False)으로 처리하지 마세요.
        3. ** null/empty 데이터**: null 또는 빈 데이터는 질문과 관련 없거나 정보가 없는 것이므로 환각 판단 대상에서 제외하세요.
        4. **유연한 텍스트 표현**: "주요 경로", "북진 흐름" 등의 요약적 묘사는 데이터의 경향성을 나타낸 것이라면 환각으로 보지 말고 너그럽게 인정하세요.

        [오직 다음의 경우에만 환각(False)으로 판정하세요]:
        - Ground Truth 데이터에 존재하지 않는 **아예 엉뚱한 숫자**를 창작해 냈을 때
        - 단순 합산이나 산술 결과가 명백히 틀렸을 때 (예: 13 + 14 + 3 = 31 로 기술한 경우)
        - 남서진(15척)이 압도적인데 "동진이 대세다"처럼 데이터의 명백한 사실을 정반대로 왜곡했을 때

        --------------------------------------------------
        [정량 분석 데이터 JSON (Ground Truth)]:
        {raw_fact_data}

        --------------------------------------------------
        [지휘관 최종 답변 (final_answer)]:
        {target_answer}
        --------------------------------------------------
        정량 데이터의 핵심 경향과 수치가 부합한다면 웬만하면 is_hallucination_free를 True로 판정하고, 점수는 8점 이상을 부여하세요.
        그리고 is_hallucination_free가 False인 경우, 그 이유(reason)를 반드시 기술해야 해!
    """
    return structured_evaluator.invoke(eval_prompt)
    
# ---------------------------------------------------------------------------
# 2. 통합 평가 자동화 스크립트 메인 함수(비동기 처리)
# ---------------------------------------------------------------------------
async def process_single_query(
        idx: int, 
        total_count: int, 
        user_query: str,
        expected_categories: List[str],
        sem: asyncio.Semaphore
) -> Dict[str, Any]:
    """단일 쿼리에 대한 라우팅 및 환각 평가 수행하는 함수"""

    async with sem:
        await asyncio.sleep(random.uniform(1.5, 2.0))

        test_result: Dict[str, Any] ={
                "query": user_query,
                "expected_categories": expected_categories,
                "actual_categories": [],
                "router_score": 0,
                "hallucination_pass": False,
                "fact_score": 0,
                "reason": ""
            }
        
        try:
            # 1. 라우팅 테스트
            router = RouterCrew()

            router_output = await router.crew().kickoff_async(
                inputs={"user_question": user_query}
            )

            actual_categories = router_output.pydantic.needed_categories
            test_result["actual_categories"] = actual_categories

            #라우터 점수 계산
            is_router_matched = any(cat in actual_categories for cat in expected_categories)

            if is_router_matched:
                test_result["router_score"] = 1
                log_router = f"🎯 [라우팅] ✅ 성공 (1점) | 매핑: {actual_categories}]"
            else:
                log_router = f"🎯 [라우팅] ❌ 실패 (0점) | Expected: {expected_categories} vs Actual: {actual_categories}"

            if hasattr(router_output.pydantic, 'rationale'):
                rationale_text = f"\n | [판단근거]: {router_output.pydantic.rationale}"
            else:
                rationale_text = ""

            # 2. 메인크루 실행
            battlefield_crew_instance = BattlefieldCrew(needed_categories=actual_categories)
            # BattlefieldCrew.needed_categories = actual_categories

            crew_output = await battlefield_crew_instance.crew().kickoff_async(
                inputs={
                    'user_question': user_query,
                    }
            )

            #3. fact-check 검증
            report_data = crew_output.pydantic

            #전체상황 요약 요청시 사용할 템플릿(format_maritimr_report) 적용된 결과 출력
            if '전체상황 요약' in actual_categories and report_data:
                report_data.final_answer = format_maritime_report(report_data)
                #전체상황 요약 템플릿 형식대로 출력되는지 확인
                print("+"*85)
                print("+"*85)
                print(report_data.final_answer)
                print("+"*85)
                print("+"*85)

            fact_check = check_report_hallucination(report_data)

            test_result["hallucination_pass"] = fact_check.is_hallucination_free
            test_result["fact_score"] = fact_check.score
            test_result["reason"] = fact_check.reason

            if fact_check.is_hallucination_free:
                log_fact = f"🧐 [Fact-Check] ✅ 통과 ({fact_check.score}점)"
            else:
                log_fact = f"🧐 [Fact-Check] ❌ 실패 ({fact_check.score}점) - {fact_check.reason}"

            # 중간 결과 출력
            print(f"\n[테스트 {idx}/{total_count}] \"{user_query}\"\n  ├ {log_router}{rationale_text}\n  └ {log_fact}")

        except Exception as e:
            print(f"\n[테스트 {idx}/{total_count}] \"{user_query}\"\n  └ ⚠️ [오류 발생]: {e}")
            test_result["reason"] = f"Pipeline Execution Error: {str(e)}"
        
        return test_result

    

async def run_automated_benchmark(dataset: Dict[str, List[str]]):
    """모든 데이터셋 쿼리를 병렬(Concurrent)로 실행하는 벤치마크 메인 함수"""
    print("\n"+"="*85)
    print("[통합 평가 시작 (비동기 병렬 실행: 라우팅 퍼포먼스 & Hallucination 평가)]")
    print("="*85)

    total_count = len(dataset)

    sem = asyncio.Semaphore(5) #동시 실행 개수 컨트롤
    # 1. 모든 작업(Task) 생성

    tasks = [
        process_single_query(idx, total_count, query, expected_cats, sem)
        for idx, (query, expected_cats) in enumerate(dataset.items(), 1)
    ]

    # 2. 모든 작업 동시 실행 및 결과 수집
    evaluation_logs = await asyncio.gather(*tasks)

    # 3. 최종 집계 및 리포팅
    router_success_count = sum(log["router_score"] for log in evaluation_logs)
    hallucination_pass_count = sum(1 for log in evaluation_logs if log["hallucination_pass"])

    print("\n" + "="*85)
    print("📊 [최종 평가 보고서]")
    print(f" • 총 테스트 수: {total_count}")
    print(f" • 라우터 성공률: {router_success_count}/{total_count} ({router_success_count/total_count*100:.1f}%)")
    print(f" • 환각 검증 통과율: {hallucination_pass_count}/{total_count} ({hallucination_pass_count/total_count*100:.1f}%)")
    print("="*85 + "\n")

    return evaluation_logs




if __name__ == "__main__":

    TEST_DATASET = test_dataset_loading() 
    
    # 벤치마크 비동기 실행
    asyncio.run(run_automated_benchmark(TEST_DATASET)) #비동기 일 때
    














