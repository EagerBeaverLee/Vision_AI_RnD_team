import json

from datasets import load_dataset 
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from naiveRAG import naiveRAG
from ragas_Adaptive_RAG import ragas_Adaptive_RAG
from ragas import evaluate 
from ragas.metrics import (
    answer_relevancy, 
    faithfulness, 
    context_recall, 
    context_precision, 
) 
from dotenv import load_dotenv

load_dotenv()

amnesty_qa = load_dataset("explodinggradients/amnesty_qa", "english_v2") 
amnesty_qa 

embedded = OpenAIEmbeddings()
retriever = naiveRAG(embedded).ragas_retrieve()

adaptive_rag = ragas_Adaptive_RAG(retriever).build_graph()

with open("golden_answers_final_master_file.json", "r", encoding="utf-8") as f:
    dataset = json.load(f)

total_items = len(dataset)
print(f"📊 총 {total_items}개의 데이터를 불러왔습니다. 평가 파이프라인 가동 시작...\n")

name = "Adaptive_RAG"

final_reports = []

for i, item in enumerate(dataset, 1):
    report = adaptive_rag.invoke({"question": item["input"], "rag_name": name, "expected_document": item["context"], "expected_answer": item["expected_output"]})
    final_reports.append(report)
    
    # 중간 저장 (만약 중간에 끊기더라도 지금까지의 데이터를 살리기 위해)
    if i % 5 == 0:
        # pd.DataFrame(final_reports).to_csv("rag_benchmark_backup.csv", index=False, encoding="utf-8-sig")
        # JSON 중간 저장
        with open("testing_backup.json", "w", encoding="utf-8") as f:
            json.dump(final_reports, f, ensure_ascii=False, indent=4)
        print(f"💾 {i}개 데이터 백업 완료!")

    print("*" * 55)
    print(report)
    print("*" * 55)

    # if isinstance(report, dict) and "generation" in report:
    #     answer = report["generation"]
    # elif isinstance(report, dict) and "output" in report:
    #     answer = report["output"]

    result = evaluate( 
        amnesty_qa["eval"], 
        metrics=[ 
            context_precision, 
            faithfulness, 
            answer_relevancy, 
            context_recall, 
        ], 
        llm=ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=0,
        ), 
        embeddings=embedded, 
        column_map={"user_input": item["input"], "response": report["generation"], "retrieved_contexts": report["documents"], "reference": item["expected_output"]}, 
    ) 