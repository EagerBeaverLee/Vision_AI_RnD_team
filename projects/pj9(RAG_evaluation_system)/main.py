from dotenv import load_dotenv
from naiveRAG import naiveRAG
from RAG_relevant import RAG_Relevant
from RAG_rel_halu import RAG_Rel_Halu
from Adaptive_RAG import Adaptive_RAG
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from langgraph.graph.state import CompiledStateGraph
from langchain_core.retrievers import BaseRetriever

import asyncio, time, json
import pandas as pd 
from typing import Dict, Any, List
from pydantic import BaseModel, Field

import matplotlib.pyplot as plt
import seaborn as sns
import platform

load_dotenv()

embedded = OpenAIEmbeddings()
retriever = naiveRAG(embedded).retrieve()

naive_rag = naiveRAG(embedded).build_chain()
rag_relevant = RAG_Relevant(retriever).build_graph()
rag_rel_halu = RAG_Rel_Halu(retriever).build_graph()
adaptive_rag = Adaptive_RAG(retriever).build_graph()

# res = naive_rag.invoke("정보작전에 대해 설명해줘")
# for a in res:
#     print(a.page_content)

# graph_input = {
#     "question": "정보작전이 뭔지 설명해줘"
# }
# response = rag_rel_halu.invoke(graph_input)
# print(response["generation"])


# ==========================================
# 1. 판사(LLM Judge) 구조화 출력 정의 (1~10점) gpt-4o와 같은 큰모델 전용
# ==========================================
# class RAGEvaluationResult(BaseModel):
#     hallucination_score: int = Field(
#         ..., min=1, max=10, 
#         description="환각 점수 (1~10점). 모범답안(expected_output)에 없는 사실을 지어내거나 왜곡하면 감점. 완벽히 사실만 말하면 10점."
#     )
#     hallucination_reason: str = Field(
#         ..., description="환각 점수를 부여한 구체적인 이유와 근거 서술"
#     )
#     relevance_score: int = Field(
#         ..., min=1, max=10, 
#         description="질문 적합성 점수 (1~10점). [input]의 의도를 벗어나거나 헛소리를 하면 감점. 완벽히 부합하면 10점."
#     )
#     relevance_reason: str = Field(
#         ..., description="질문 적합성 점수를 부여한 구체적인 이유와 근거 서술"
#     )

# JUDGE_SYSTEM_PROMPT = """당신은 RAG 시스템의 성능을 평가하는 엄격하고 공정한 분석 전문가입니다.
#     제공된 [사용자 질문]과 [모범 답안]을 바탕으로, 시스템이 내놓은 [RAG 답변]을 평가 기준에 따라 1점부터 10점까지의 척도로 채점하십시오.

#     [평가 기준]
#     1. 환각 (Hallucination) 평가
#     - [RAG 답변]이 [모범 답안]의 사실 정보를 왜곡하거나, 언급되지 않은 허위 사실을 포함하고 있다면 점수를 크게 깎으십시오.
#     - 오직 팩트에만 기반해야 10점입니다.
#     2. 질문 적합성 (Question Relevance) 평가
#     - [RAG 답변]이 [사용자 질문]의 본질적인 의도에 정확하게 대답하고 있는지 평가하십시오.
#     - 핵심을 비껴간 답변은 감점 대상입니다.

#     반드시 주관적 편견을 버리고 오직 제공된 텍스트만을 기준으로 논리적인 이유와 함께 점수를 부여하십시오."""

# judge_prompt = ChatPromptTemplate.from_messages([
#     ("system", JUDGE_SYSTEM_PROMPT),
#     ("human", """[사용자 질문]: {query}
# [모범 답안]: {ground_truth}
# [RAG 답변]: {rag_answer}

# 위 내용을 바탕으로 환각과 적합성을 엄격하게 평가해 주세요.""")
# ])

class RAGEvaluationResult(BaseModel):
    hallucination_score: int = Field(
        ..., min=1, max=10, 
        description="환각 점수 (1~10점). 모범답안에 없는 사실을 지어내거나 왜곡하면 감점. 완벽히 사실만 말하면 10점."
    )
    hallucination_reason: str = Field(
        ..., description="환각 점수를 부여한 이유. 최대 2문장 이내로 아주 간결하게 핵심만 작성할 것." # 👈 수정됨
    )
    relevance_score: int = Field(
        ..., min=1, max=10, 
        description="질문 적합성 점수 (1~10점). 질문의 의도를 벗어나거나 헛소리를 하면 감점. 완벽히 부합하면 10점."
    )
    relevance_reason: str = Field(
        ..., description="질문 적합성 점수를 부여한 이유. 최대 2문장 이내로 아주 간결하게 핵심만 작성할 것." # 👈 수정됨
    )

JUDGE_SYSTEM_PROMPT = """당신은 RAG 시스템의 성능을 평가하는 엄격하고 공정한 분석 전문가입니다.
제공된 [사용자 질문]과 [모범 답안]을 바탕으로, 시스템이 내놓은 [RAG 답변]을 평가 기준에 따라 1점부터 10점까지의 척도로 채점하십시오.

[평가 기준]
1. 환각 (Hallucination) 평가
- [RAG 답변]이 [모범 답안]의 사실 정보를 왜곡하거나, 언급되지 않은 허위 사실을 포함하고 있다면 점수를 크게 깎으십시오.
- 오직 팩트에만 기반해야 10점입니다.
2. 질문 적합성 (Question Relevance) 평가
- [RAG 답변]이 [사용자 질문]의 본질적인 의도에 정확하게 대답하고 있는지 평가하십시오.
- 핵심을 비껴간 답변은 감점 대상입니다.

[출력 규칙 - 매우 중요]
- 이유(reason) 필드는 반드시 1~2문장 이내로 아주 짧고 명확하게 작성하십시오.
- 장황한 서론이나 반복적인 설명은 절대 금지합니다.""" # 👈 족쇄 추가

judge_prompt = ChatPromptTemplate.from_messages([
    ("system", JUDGE_SYSTEM_PROMPT),
    ("human", """[사용자 질문]: {query}
[모범 답안]: {ground_truth}
[RAG 답변]: {rag_answer}

위 내용을 바탕으로 환각과 적합성을 평가해 주세요.""")
])

# 판사 LLM 
llm = ChatOpenAI(
    api_key="ai",
    model="openai/gpt-oss-20b",
    base_url="http://192.168.0.110:8000/v1",
    temperature=0,
    max_completion_tokens=6000,
)

llm_judge = judge_prompt | llm.with_structured_output(RAGEvaluationResult)
# ==========================================
# 2. [추가] 단일 RAG 실행 및 시간 측정 래퍼 함수
# ==========================================
async def run_rag_with_timing(name: str, pipeline, user_input: str, expected_answer: str, expected_documents: List[str]):
    """RAG 파이프라인을 실행하고 소요 시간을 측정하여 반환합니다."""
    start_time = time.perf_counter() # 시작 시간 기록
    
    try:
        # 타입에 따른 동적 입력 어댑터
        if isinstance(pipeline, CompiledStateGraph) or hasattr(pipeline, "get_state"):
            res = await pipeline.ainvoke({"question": user_input, "rag_name": name, "expected_answer": expected_answer, "expected_documents": expected_documents})
        elif isinstance(pipeline, BaseRetriever):
            res = await pipeline.ainvoke(user_input)
        else:
            try:
                res = await pipeline.ainvoke({"question": user_input})
            except Exception:
                res = await pipeline.ainvoke(user_input)
                
        # 결과 추출기
        if isinstance(res, dict) and "generation" in res:
            answer = res["generation"]
        elif isinstance(res, dict) and "output" in res:
            answer = res["output"]
        elif isinstance(res, list):
            answer = "\n".join([getattr(doc, 'page_content', str(doc)) for doc in res])
        else:
            answer = str(res)
            
    except Exception as e:
        answer = f"실행 중 에러 발생: {e}"

    end_time = time.perf_counter() # 종료 시간 기록
    elapsed_time = round(end_time - start_time, 2) # 소요 시간 (소수점 2자리)
    
    return name, answer, elapsed_time

# ==========================================
# 3. 단일 데이터셋 아이템 처리 함수
# ==========================================
async def evaluate_single_item(item: dict, rag_pipelines: dict, current_idx: int, total_idx: int) -> dict:
    """하나의 데이터셋 아이템을 받아 4개 RAG 가동 및 채점을 진행합니다."""
    user_input = item["input"]
    expected_answer = item["expected_output"]
    expected_documents = item["context"]
    
    print(f"\n🚀 [{current_idx}/{total_idx}] 질문 처리 시작: {user_input[:40]}...")


    # 4개의 RAG를 시간 측정 함수로 묶어 동시에 실행
    tasks = [
        run_rag_with_timing(name, pipeline, user_input, expected_answer, expected_documents)
        for name, pipeline in rag_pipelines.items()
    ]
    
    print(f"\n🚀 병렬실행 후 응답 수집: ...")
    # gather를 통해 4개 RAG 완료 대기
    results = await asyncio.gather(*tasks)
    
    # 기본 정보 저장
    report = {
        "input": user_input,
        "expected_output": expected_answer
    }


    print(f"\n🚀 llm-as-judge 채점요청: ...")
    
    # 판사 LLM에게 채점 요청 및 시간 기록
    for name, answer, elapsed_time in results:
        report[f"{name}_answer"] = answer
        report[f"{name}_time_sec"] = elapsed_time # ⏱️ 측정된 시간 저장
        
        try:
            judge_res = await llm_judge.ainvoke({
                "query": user_input,
                "ground_truth": expected_answer,
                "rag_answer": answer
            })
            report[f"{name}_환각점수"] = judge_res.hallucination_score
            report[f"{name}_환각이유"] = judge_res.hallucination_reason
            report[f"{name}_적합성점수"] = judge_res.relevance_score
            report[f"{name}_적합성이유"] = judge_res.relevance_reason
        except Exception as e:
            print(f"⚠️ {name} 채점 중 에러 발생: {e}")
            report[f"{name}_환각점수"] = 0
        
    print(f"✅ [{current_idx}/{total_idx}] 채점 완료!")
    return report

def save_boxplot_img(df):
    save_path = "total_rag_boxplot.png"

    # 2. '점수'라는 단어가 포함된 모든 컬럼 이름을 자동으로 추출
    score_columns = [col for col in df.columns if '점수' in col]

    # 3. 한글 폰트 및 마이너스 기호 깨짐 방지 설정
    if platform.system() == 'Windows':
        plt.rc('font', family='Malgun Gothic')
    elif platform.system() == 'Darwin':
        plt.rc('font', family='AppleGothic')
    else:
        plt.rc('font', family='NanumGothic')
    plt.rcParams['axes.unicode_minus'] = False 

    # 4. 그래프 사이즈 설정 (컬럼 개수가 많을수록 가로 길이를 늘려주면 좋습니다)
    plt.figure(figsize=(10, 6))

    # 5. Seaborn을 이용한 Boxplot 시각화
    # 추출한 score_columns만 data로 넘겨줍니다.
    sns.boxplot(
        data=df[score_columns], 
        palette="Set3",   # 파스텔 톤의 부드러운 색상 테마
        width=0.5         # 박스 두께
    )

    # 6. 그래프 꾸미기
    plt.title("다중 RAG 파이프라인 평가 점수 분포", fontsize=16, pad=15)
    plt.ylabel("점수 (Score)", fontsize=12)

    # 이름이 길어서 겹치는 것을 방지하기 위해 x축 라벨 45도 회전
    plt.xticks(rotation=45, ha='right') 

    plt.grid(axis='y', linestyle='--', alpha=0.7) # y축 가이드라인 추가

    # 7. 고화질 PNG 파일로 저장
    # bbox_inches='tight': 45도 기울인 글자가 이미지 밖으로 잘리지 않도록 여백을 자동 조정해줍니다.
    
    plt.savefig(save_path, dpi=300, bbox_inches='tight')

    # 메모리 누수 방지를 위해 figure 닫기 (여러 번 반복 실행할 때 필수)
    plt.close()

    print(f"✨ 여러 모델의 평가 결과가 담긴 Boxplot이 '{save_path}'에 성공적으로 저장되었습니다!")

def save_csv_file(df):
    # 2. '점수'라는 단어가 포함된 모든 컬럼 이름을 자동으로 추출
    score_columns = [col for col in df.columns if '점수' in col]

    time_columns = [col for col in df.columns if 'time_sec' in col]

    time_data = {"비고": "평균 소요시간 (time)"}
    mean_data = {"비고": "평균 (Mean)"}
    std_data = {"비고": "표준편차 (Std)"}

    # 4. 추출한 점수 컬럼들을 순회하며 계산
    for col in score_columns:
        mean_data[col] = df[col].mean()
        std_data[col] = df[col].std()

    for tic in time_columns:
        time_data[col] = df[tic].mean()

    # 5. 계산된 통계를 데이터프레임으로 변환 후 기존 df에 이어붙이기
    summary_rows = pd.DataFrame([time_data, mean_data, std_data])
    df_final = pd.concat([df, summary_rows], ignore_index=True)

    # 6. 보기 좋게 정리 ('비고' 컬럼의 빈칸 처리 및 맨 앞으로 이동)
    df_final["비고"] = df_final["비고"].fillna("")
    cols = ["비고"] + [c for c in df_final.columns if c != "비고"]
    df_final = df_final[cols]
        
    df_final.to_csv("rag_performance_benchmark.csv", index=False, encoding="utf-8-sig")
    print("\n✨ 벤치마크가 성공적으로 완료되었습니다! 'default_rag_performance_benchmark.csv' 파일을 확인하세요.")

# ==========================================
# 4. 전체 벤치마크 가동 메인 함수
# ==========================================
async def main():
    # 🌟 실제 데이터셋 JSON 파일 불러오기 (경로를 맞게 수정해 주세요!)
    with open("golden_answers_final_master_file.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    total_items = len(dataset)
    print(f"📊 총 {total_items}개의 데이터를 불러왔습니다. 평가 파이프라인 가동 시작...\n")

    # 테스트를 위한 4가지 RAG 파이프라인 딕셔너리 (실제 컴파일된 랭그래프 객체를 할당하세요)
    # 여기서는 예시를 위해 가상의 객체명을 적어두었습니다.
    rag_pipelines = {
        # "Basic_RAG": naive_rag,
        # "RAG_rel": rag_relevant,
        # "RAG_halu": rag_rel_halu,
        "Adaptive_RAG": adaptive_rag
    }

    print("📊 RAG 벤치마크 평가 파이프라인 가동 시작...")
    
    final_reports = []
    
    # 🌟 데이터셋 폭주 방지를 위해 한 개씩 차례대로(순차) 루프를 돕니다.
    for i, item in enumerate(dataset, 1):
        report = await evaluate_single_item(item, rag_pipelines, i, total_items)
        final_reports.append(report)
        
        # 중간 저장 (만약 중간에 끊기더라도 지금까지의 데이터를 살리기 위해)
        if i % 5 == 0:
            # pd.DataFrame(final_reports).to_csv("rag_benchmark_backup.csv", index=False, encoding="utf-8-sig")
            # JSON 중간 저장
            with open("testing_change_hal_back.json", "w", encoding="utf-8") as f:
                json.dump(final_reports, f, ensure_ascii=False, indent=4)
            print(f"💾 {i}개 데이터 백업 완료!")
    
    # 판다스 데이터프레임으로 변환 후 CSV 저장
    # df = pd.DataFrame(final_reports)
    # save_boxplot_img(df)
    # save_csv_file(df)

    # 2. JSON 파일로 저장 (추가된 부분)
    with open("testing_change_hal.json", "w", encoding="utf-8") as f:
        # ensure_ascii=False: 한글 깨짐 방지
        # indent=4: 들여쓰기를 적용해 사람이 읽기 좋게(Pretty Print) 포맷팅
        json.dump(final_reports, f, ensure_ascii=False, indent=4)
    print("\n✨ 벤치마크가 성공적으로 완료되었습니다! 'testing.json' 파일을 확인하세요.")


if __name__ == "__main__":
    asyncio.run(main())