import os
import json
import re
import glob
from typing import List, Dict, Any


# Markdown 파싱 툴
def parse_markdown_dataset(md_text: str) -> List[Dict[str, Any]]:
    """마크다운 텍스트에서 Q 번호, 질문, 평가 포인트를 자동으로 추출합니다."""
    dataset = []
    # Q01, Q02 패턴 단위로 블록 분할
    raw_blocks = re.split(r'(###\s*Q\d+\.)', md_text)
    
    for i in range(1, len(raw_blocks), 2):
        q_num = raw_blocks[i].replace('###', '').strip()
        block_content = raw_blocks[i+1]
        
        # 질문 텍스트 추출 (Q 번호 직후부터 첫 번째 '*' 전까지)
        q_match = re.search(r'^(?:\s*\[.*?\])?\s*(.*?)(?=\n\*|\Z)', block_content, re.DOTALL)
        question = q_match.group(1).strip() if q_match else "질문 추출 실패"
        
        # RAG 핵심 평가 포인트 / 평가 포인트 섹션 추출 (두 포맷 모두 대응)
        eval_points = []
        points_section = re.search(r'(?:RAG\s*)?평가\s*포인트.*?:(.*?)(?=\n###|\Z)', block_content, re.DOTALL)
        
        if points_section:
            section_content = points_section.group(1).strip()
            
            # 1) '1.', '2.' 형태의 숫자 번호 추출 시도
            raw_points = re.findall(r'\d+\.\s*(.*?)(?=\n\s*\d+\.|\Z)', section_content, re.DOTALL)
            
            # 2) 만약 숫자 목록이 없으면 '*' 또는 '-' 형태의 불릿 항목 추출 시도
            if not raw_points:
                raw_points = re.findall(r'^\s*[\*\-]\s*(.*?)(?=\n\s*[\*\-]|\Z)', section_content, re.MULTILINE | re.DOTALL)
            
            # 줄바꿈 제거 및 공백 정리
            eval_points = [p.strip().replace('\n', ' ') for p in raw_points if p.strip()]
            
        dataset.append({
            "id": q_num,
            "question": question,
            "eval_points": eval_points
        })
        
    return dataset


def format_questions_for_rag_crew(dataset: List[Dict[str, Any]]) -> List[str]:
    formatted_list = []

    for item in dataset:
        q_text = item["question"]
        q_text = re.sub(r'^\[.*?\]\s*', '', q_text)
        clean_question = q_text.strip().strip('"').replace('\n',' ')

        formatted_text = f'"{clean_question}":["RagCrew"],'
        formatted_list.append(formatted_text)

    return formatted_list

# if __name__ == "__main__":
    # 1. raw string(r"...")을 사용하여 경로 역슬래시 에러 방지
    # target_dir = r"D:\업무\2024\Artificial_Intteligence\coding\python\ai_agent\crewai-in-action-main\chapter-06-mod\my_battlefield_crew\src\my_battlefield_crew\data\doctrine_data\rag_evaluation_data"

    # # 2. 파일 내용을 읽어오는(open/read) 과정 추가
    # try:
    #     md_files = glob.glob(os.path.join(target_dir, "*.md"))
    #     print(f"📁 발견된 .md 파일 목록 ({len(md_files)}개):")
    #     for f in md_files:
    #         print(f" - {os.path.basename(f)}")

    #     if not md_files:
    #         print("❌ 해당 폴더에 .md 파일이 존재하지 않습니다.")
    #         exit()

    #     # 2) 파일 내용 통합하기 (파일과 파일 사이에 줄바꿈 추가)
    #     combined_md_content = ""
    #     for file_path in md_files:
    #         with open(file_path, "r", encoding="utf-8") as f:
    #             combined_md_content += f.read() + "\n\n"

    #     # 3. 읽어온 텍스트(md_content)를 파서 함수에 전달
    #     parsed_data = parse_markdown_dataset(combined_md_content)
    #     # ragcrew_questions = format_questions_for_rag_crew(parsed_data)

        
    #     print("--- [전환 결과] ---")
    #     for p in parsed_data:
    #         print(p)

    #     output_path = os.path.join(target_dir, "ragcrew_evaluation_dataset.json")
    #     with open(output_path, "w", encoding="utf-8") as out_f:
    #         json.dump(parsed_data, out_f, ensure_ascii=False, indent=4)

    #     print(f"\n✅ 총 {len(parsed_data)}개 질문 추출 완료!")
    #     print(f"✅ 통합 파일 저장 위치:\n{output_path}")

    # except FileNotFoundError:
    #     print(f"❌ 파일을 찾을 수 없습니다. 경로를 확인해주세요:\n{target_dir}")
    # except Exception as e:
    #     print(f"❌ 에러 발생: {e}")

    # json_path = r"src/my_battlefield_crew/data/doctrine_data/rag_evaluation_data/ragcrew_evaluation_dataset.json"

    # with open(json_path, "r", encoding="utf-8") as f:
    #     json_dataset = json.load(f)

    # print(f"총 {len(json_dataset)}개의 데이터가 로드 됐습니다!")

    # eval_points_extract = []

    # for idx, item in enumerate(json_dataset, 1):
    #     q_id = item.get("id", f"Q{idx:02d}")
    #     question = item.get("question", "")
    #     eval_points =item.get("eval_points", [])

    #     eval_points_extract.append({
    #         "Q_ID": q_id,
    #         # "Question": question,
    #         "Eval_Points": "\n".join([f"- {pt}" for pt in eval_points])
    #     })

    # print(eval_points_extract)