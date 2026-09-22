import sys
import os
import json
import asyncio
from typing import Dict, List, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
# from engine.task_router import RouterCrew
from crews.battlefield_crew import BattlefieldCrew


class HallucinationCheckResult(BaseModel):
    is_hallucination_free: bool = Field(
        description="final_answer가 정량 데이터(top_dense_zones, main_routes 등)와 완벽히 일치하면 True, 숫자를 왜곡하거나 없는 사실을 지어냈으면 False"
    )
    score: int = Field(
        description="사실 부합성 및 신뢰도 점수 (100점 만점 기준)"
    )
    reason: str = Field(
        description="환각 판단 근거 (정량 데이터 수치와 final_answer 간의 불일치 지점, 거짓 수치 언급 등을 상세히 기술)"
    )

# 2. report_data 직렬화 기반 검증 함수
def check_report_hallucination(report_data) -> HallucinationCheckResult:
    """
    MaritimeSituationReport Pydantic 객체 내의 정량 데이터 구조체들과
    final_answer 간의 사실 부합성(환각 여부)을 검증하는 함수
    """
    evaluator_llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_evaluator = evaluator_llm.with_structured_output(HallucinationCheckResult)

    # final_answer를 제외한 순수 정량 데이터들만 딕셔너리로 분리
    full_dict = report_data.model_dump()
    target_answer = full_dict.pop("final_answer", "")
    
    # 정량 데이터 구조체를 JSON 문자열로 변환 (Ground Truth)
    raw_fact_data = json.dumps(full_dict, ensure_ascii=False, indent=2)

    eval_prompt = f"""
당신은 해상 전장 분석 시스템의 'Fact-Checker (환각 검증관)'입니다.
아래 제공된 [정량 분석 데이터 JSON]만을 '유일한 진실(Ground Truth)'로 간주하여, [지휘관 최종 답변 (final_answer)]에 환각(Fact 오류)이 있는지 엄격히 검증하십시오.

[검증 규칙]
1. final_answer에 언급된 모든 숫자(체류지수, 속도, 척수, 방향각, 횟수 등)가 [정량 분석 데이터 JSON] 내의 해당 필드 수치와 일치하는가(소수점 차이는 무시해도 좋음)?
2. final_answer에 언급된 해역명, 항로, 선박명이 실제 데이터 필드 내에 존재하는가?
3. null 또는 empty 상태의 데이터가 보여도 환각으로 판별하지마. null로 되어 있다는 것은 그 데이터 값들이 사용자의 질문과 직접 관련이 없다는 뜻이야.
4. 하지만 정량 데이터 필드가 null이거나 empty([]) 상태인데 final_answer에서 해당 항목에 대한 거짓 사실이나 구체적 수치를 언급하고 있다면 환각이야.
5. 데이터 해석에 기반한 전술적 의견이나 군사적 시사점 추론은 허용하되, '수치 데이터의 왜곡'이나 '없는 사실의 주장'은 엄격히 환각(False) 처리하십시오.


--------------------------------------------------
[정량 분석 데이터 JSON (Ground Truth)]:
{raw_fact_data}

--------------------------------------------------
[지휘관 최종 답변 (final_answer)]:
{target_answer}
--------------------------------------------------
"""
    return structured_evaluator.invoke(eval_prompt)
    
# ---------------------------------------------------------------------------
# 2. 통합 평가 자동화 스크립트 메인 함수
# ---------------------------------------------------------------------------
async def run_automated_benchmark(dataset: Dict[str, List[str]]):
    """
    1)라우터 정확도 평가
    2)final_answer에 대한 환각(hallucination) 검증
    3)종합 평가 결과 보고서 출력
    """

    print("\n" + "="*85)
    print("[통합 평가 시작(라우팅 퍼포먼스 & Hallucination평가)]")

    total_count = len(dataset)
    router_success_count = 0
    hallucination_pass_count = 0
    evaluation_logs = []

    for idx, (user_query, expected_categories) in enumerate(dataset.items(),1):
        print("\n" + "-"*85)
        print(f"테스트 [{idx}/{total_count}]: \"{user_query}\"")
        print("\n" + "-"*85)

        test_result: Dict[str, Any] = {
            "query": user_query,
            "expected_categories": expected_categories,
            "actual_categories":[],
            "router_score": 0,
            "hallucination_pass": False,
            "fact_score": 0,
            "reason": ""
        }

        try:
            #1. 라우팅 테스트
            router = RouterCrew(user_question=user_query)
            router_output = await router.crew().kickoff_async()
            
            actual_categories = router_output.pydantic.needed_categories
            test_result["actual_categories"] =  actual_categories

            #라우터 점수 계산
            is_router_matched = any(cat in actual_categories for cat in expected_categories)
            if is_router_matched:
                test_result["router_score"] = 1
                router_success_count += 1
                print(f"  ├ 🎯 [라우팅 검증] : ✅ 성공 (1점) | 매핑된 카테고리: {actual_categories}")
            else:
                print(f"  ├ 🎯 [라우팅 검증] : ❌ 실패 (0점) | Expected: {expected_categories} vs Actual: {actual_categories}") 


# print("📡 [1단계] 작전통제 라우터 가동하여 필요 도구 식별 중...")
            # categories = router_output.needed_categories
            # print(f"[분석 카테고리 결정]: {categories}")
            # print(f"[전술적 판단 근거]: {router_output.rationale}")    

            if hasattr(router_output.pydantic, 'rationale'):
                print(f"[전술적 판단근거]: {router_output.pydantic.rationale}")

            BattlefieldCrew.needed_categories = actual_categories
            battlefield_crew_instance = BattlefieldCrew()

            crew_output = await battlefield_crew_instance.crew().kickoff_async(
                inputs={'user_question': user_query}
            )

            # 3. Pydantic으로 가공된 정밀 구조화 데이터 핸들링
            report_data = crew_output.pydantic
            
            fact_check = check_report_hallucination(report_data)
            test_result["hallucination_pass"] = fact_check.is_hallucination_free
            test_result["fact_score"] = fact_check.score
            test_result["reason"] = fact_check.reason

            if fact_check.is_hallucination_free:
                hallucination_pass_count += 1
                print(f"  └ 🧐 [Fact-Check] : ✅ 통과 ({fact_check.score}점) - 환각 없음")
            else:
                print(f"  └ 🧐 [Fact-Check] : ❌ 실패 ({fact_check.score}점) - {fact_check.reason}")
        except Exception as e:
            print(f"  └ ⚠️ [오류 발생] 실행 중 파이프라인 에러: {e}")
            test_result["reason"] = f"Pipeline Execution Error: {str(e)}"

        evaluation_logs.append(test_result)
        print()
    
    router_accuracy = (router_success_count / total_count) * 100
    hallucination_pass_rate = (hallucination_pass_count / total_count) * 100

    print("\n" + "="*85)
    print("📊 [최종 통합 검증 성적표 (Benchmark Summary Report)]")
    print("="*85)
    print(f"• 전체 테스트 질문 수   : {total_count}개")
    print(f"• 라우터 성공률 (Accuracy): {router_accuracy:.2f}% ({router_success_count}/{total_count} 성공)")
    print(f"• 환각 없음 무결점 비율  : {hallucination_pass_rate:.2f}% ({hallucination_pass_count}/{total_count} 통과)")
    print("="*85)

    # 실패 사례 디버깅 요약
    failed_items = [log for log in evaluation_logs if log['router_score'] == 0 or not log['hallucination_pass']]
    if failed_items:
        print("\n🔍 [개선 필요 질문 및 오류 취약점 분석]")
        for f in failed_items:
            print(f"\n\n• 질문: \"{f['query']}\"")
            print(f"\n•정답 도구: \"{f['expected_categories']}\"  ")
            print(f"\n•선택된 도구: \"{f['actual_categories']}\"  ")
            if f['router_score'] == 0:
                print(f"   - 라우팅 실패 : 정답 {f['expected_categories']} ↔ 실제 {f['actual_categories']}")
            if not f['hallucination_pass']:
                print(f"   - 환각 감지   : {f['fact_score']}점 | 사유: {f['reason']}")
    print("="*85 + "\n")