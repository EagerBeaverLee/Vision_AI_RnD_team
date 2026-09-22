import asyncio
from typing import Dict, List, Any
from crews.master_router_crew import MasterRouterCrew
from tests.test_data_loading import master_router_test_dataset_loading

# ----------------------------------------------
# 1. master_router_crew.py 메인 라우터 기능 테스트
# ----------------------------------------------

async def process_single_query(
        idx: int, 
        total_count: int, 
        user_query: str,
        expected_categories: List[str],
        sem: asyncio.Semaphore
) -> Dict[str, Any]:
    """단일 쿼리에 대한 라우팅 및 환각 평가 수행하는 함수"""
    test_result: Dict[str, Any] ={
        "query": user_query,
        "expected_categories": expected_categories,
        "actual_categories": [],
        "router_score": 0
    }

    async with sem:
        try:
            # 1. 라우팅 테스트
            router = MasterRouterCrew()

            router_output = await router.crew().kickoff_async(
                inputs={"user_question": user_query}
            )

            actual_categories = router_output.pydantic.target_crew
            test_result["actual_categories"] = actual_categories

            if hasattr(router_output.pydantic, 'rationale'):
                test_result["rationale"] = router_output.pydantic.rationale


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

            # 중간 결과 출력
            print(f"\n[테스트 {idx}/{total_count}] \"{user_query}\"\n  ├ {log_router}{rationale_text}")

        except Exception as e:
            print(f"\n[테스트 {idx}/{total_count}] \"{user_query}\"\n  └ ⚠️ [오류 발생]: {e}")
            test_result["reason"] = f"Pipeline Execution Error: {str(e)}"
        
        return test_result

async def run_automated_benchmark(dataset: Dict[str, List[str]]):
    """모든 데이터셋 쿼리를 병렬(Concurrent)로 실행하는 벤치마크 메인 함수"""
    print("\n"+"="*85)
    print("단위 평가 시작 (비동기 병렬 실행: 라우팅 퍼포먼스 평가)]")
    print("="*85)

    total_count = len(dataset)

    sem = asyncio.Semaphore(2) #동시 실행 개수 컨트롤
    # 1. 모든 작업(Task) 생성

    tasks = [
        process_single_query(idx, total_count, query, expected_cats, sem)
        for idx, (query, expected_cats) in enumerate(dataset.items(), 1)
    ]

    # 2. 모든 작업 동시 실행 및 결과 수집
    evaluation_logs = await asyncio.gather(*tasks)

    # 3. 최종 집계 및 리포팅
    failed_logs = [log for log in evaluation_logs if log["router_score"] == 0]
    router_success_count = sum(log["router_score"] for log in evaluation_logs)

    print("\n" + "="*85)
    print("📊 [최종 평가 보고서]")
    print(f" • 총 테스트 수: {total_count}")
    print(f" • 라우터 성공률: {router_success_count}/{total_count} ({router_success_count/total_count*100:.1f}%)")
    print(f" • 실패 건수: len{failed_logs}건")
    print("="*85 + "\n")

    if failed_logs:
        print("\n ❌ [실패 항목 상세 분석]")
        for i, fail in enumerate(failed_logs, 1):
            print(f"\n[{i}] 질문: \"{fail['query']}\"")
            print(f"  • Expected : {fail['expected_categories']}")
            print(f"  • Actual   : {fail['actual_categories']}")
            print(f"  • 판단 근거 : {fail['rationale']}")
        print("\n" + "="*85 + "\n")

    return evaluation_logs

if __name__ == "__main__":

    TEST_DATASET = master_router_test_dataset_loading() 
    
    # 벤치마크 비동기 실행
    asyncio.run(run_automated_benchmark(TEST_DATASET)) #비동기 일 때