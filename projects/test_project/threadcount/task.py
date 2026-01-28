import time
import concurrent.futures

def my_task(query):
    """
    단순한 작업을 시뮬레이션하는 함수
    """
    time.sleep(1) # 1초 지연
    return f"쿼리 '{query}'가 완료되었습니다."

# 1. ThreadPoolExecutor 생성
with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
    
    # 2. 태스크 제출 및 Future 객체 리스트 생성
    queries = [f"query_{i}" for i in range(100)]
    future_to_query = {executor.submit(my_task, query): query for query in queries}
    
    # 3. 완료된 태스크 개수를 추적
    completed_count = 0
    total_queries = len(queries)
    
    # 4. as_completed()를 사용하여 완료된 순서대로 Future 객체를 얻음
    for future in concurrent.futures.as_completed(future_to_query):
        query = future_to_query[future]
        try:
            result = future.result()
            completed_count += 1
            print(f"[{completed_count}/{total_queries}] {result}")
        except Exception as exc:
            print(f"쿼리 '{query}' 실행 중 예외 발생: {exc}")

print("\n모든 쿼리 처리가 완료되었습니다.")