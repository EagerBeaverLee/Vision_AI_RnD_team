import os
import time
from engine.pipeline_run import build_data_cache
import asyncio
from tests.test_data_loading import test_dataset_loading
from tests.benchmark_testing_asyncio import run_automated_benchmark

def run_battlefield_assistant(update_data=False):
    print("====================================")
    print("🛡️ 해상 작전 정보 에이전트 시스템 통합 가동")
    print("====================================")
    
    cluster_cache_path = "./cache/clusters.geojson"
    flow_cache_path = "./cache/flows.geojson"
    cache_exists = os.path.exists(cluster_cache_path) and os.path.exists(flow_cache_path)
    
    # 1. 데이터 엔진 자동 및 유연한 제어 조건
    if update_data or not cache_exists:
        print("\n⚠️ [시스템] 최신 원시 데이터 기반의 전처리 및 공간 분석(DBSCAN)을 시작합니다...")
        build_data_cache()  # engine의 파이프라인 호출 실행
    else:
        print("\n✅ [시스템] 신속한 대응을 위해 기존 분석 캐시 데이터를 자동 재사용합니다.")

    # 2. 에이전트 작동 및 종합 평가 시작...
    print("\n[에이전트 정보 수집 및 전술 브리핑 준비 중...]")



if __name__ == "__main__":

    start_time = time.perf_counter()

    run_battlefield_assistant(update_data=False)
    
    TEST_DATASET = test_dataset_loading()

    # 벤치마크 비동기 실행
    asyncio.run(run_automated_benchmark(TEST_DATASET)) #비동기 일 때
    

    elapsed_time = time.perf_counter() - start_time

    print(f"\n⏱️ 총 소요 시간: {elapsed_time:.2f}초 ({elapsed_time/60:.2f}분)")