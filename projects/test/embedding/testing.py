import os
import sys

# 이 부분에서 import 오류가 발생하면, langchain-openai가 제대로 설치되지 않은 것입니다.
from langchain_openai import OpenAIEmbeddings

# 임베딩 테스트에 사용할 간단한 텍스트 데이터
sample_texts = [
    "임베딩 모델이 잘 작동하는지 확인하기 위한 첫 번째 문장입니다.",
    "네트워크 연결에 문제가 없는지 확인하기 위한 두 번째 문장입니다.",
    "이 코드가 정상적으로 실행되면 문제가 임베딩 모델에 있지 않은 것입니다."
]

# API 키를 환경 변수에서 가져오는 것이 좋습니다.
# 여기서는 테스트를 위해 직접 입력합니다.
api_key = "api_key"

try:
    print("OpenAI 임베딩 모델을 초기화하는 중...")
    # OpenAIEmbeddings 객체를 생성합니다.
    embedding_model = OpenAIEmbeddings(openai_api_key=api_key)

    print("샘플 텍스트를 임베딩하는 중...")
    # embed_documents 메소드를 호출하여 임베딩을 생성합니다.
    embeddings = embedding_model.embed_documents(sample_texts)
    
    print("임베딩이 성공적으로 완료되었습니다!")
    # 결과 확인 (첫 번째 임베딩 벡터의 차원을 출력)
    print(f"생성된 임베딩 벡터의 수: {len(embeddings)}")
    print(f"첫 번째 임베딩 벡터의 차원: {len(embeddings[0])}")

except Exception as e:
    print(f"오류가 발생했습니다: {e}")
    sys.exit(1)