
################################################################
### 1) & 2) score_threshold & keyword 기반 후처리 함수 클래스화 ###
################################################################

# Retriever는 외부에서 정의하고 시작함
from typing import Optional, List
from langchain_core.documents import Document

class DocumentPostProcessor:
    def __init__(self, retriever):
        self.retriever = retriever

    def _filter_by_threshold(self, user_question: str, score_threshold: float) -> List[Document]:
        """
        Retriever의 원본 종류(Default, ParentDocumentRetriever 등)를 보존하면서
        유사도 임계값(score_threshold)을 적용하여 검색
        """
        # 기존 retriever의 상태 백업
        orig_search_type = getattr(self.retriever, "search_type", "similarity")
        orig_search_kwargs = dict(getattr(self.retriever, "search_kwargs", {}))

        try:
            # 임계값 검색 모드로 임시 전환
            self.retriever.search_type = "similarity_score_threshold"
            self.retriever.search_kwargs = {
                **orig_search_kwargs,
                "score_threshold": score_threshold
            }
            return self.retriever.invoke(user_question)

        except Exception as e:
            print(f"[DocumentPostProcessor] 임계값 필터링 검색 중 오류: {e}")
            return []

        finally:
            # 다음 검색에 영향이 가지 않도록 원래 설정으로 복원
            self.retriever.search_type = orig_search_type
            self.retriever.search_kwargs = orig_search_kwargs
    
    def get_threshold_retriver(self, score_threshold: float):
        """score_threshold 기반 문서 필터링"""
        retriever = self.retriever
        if not score_threshold:
            retriever = self.vectorstore.as_retriever(
                search_type = "similarity_score_threshold",
                search_kwargs = {"score_threshold": score_threshold}
            )
        return retriever

    # def _filter_by_keywords(self, docs, required_keywords: Set[str]):
    #     print("docs========")
    #     print(docs)
    #     print(required_keywords)
    #     res = None
    #     """키워드 기반 문서 필터링"""
    #     # result = docs
    #     # if required_keywords:
    #     #     result = [doc for doc in docs if set(doc.page_content.split()).intersection(required_keywords)]
    #     # return result
    #     # res = [doc for doc in docs if set(doc.page_content.split()).intersection(required_keywords)]
    #     if required_keywords:
    #         res = [doc for doc in docs if any(keyword in doc.page_content for keyword in required_keywords)]
    #         print("result========")
    #         print(res)
    #     res = docs
    #     return res

    def _filter_by_keywords(self, docs: List[Document], required_keywords: set[str]) -> List[Document]:
        """필수 키워드가 포함된 문서만 남기는 사후 필터링"""
        if not docs or not required_keywords:
            return docs

        filtered = [
            doc for doc in docs 
            if any(keyword in doc.page_content for keyword in required_keywords)
        ]
        return filtered

    def post_processor(
        self,
        user_question: str,
        score_threshold: Optional[float] = None,
        required_keywords: Optional[set[str]] = None
    ) -> List[Document]:
        """1단계: 유사도 임계값 검색 -> 2단계: 키워드 필터링을 순차 적용"""
        
        # 1. 문서 검색 (Threshold 유무에 따라 분기)
        if score_threshold is not None and score_threshold > 0:
            docs = self._filter_by_threshold(user_question, score_threshold)
        else:
            docs = self.retriever.invoke(user_question)

        # 2. 키워드 후처리 필터링
        if required_keywords:
            docs = self._filter_by_keywords(docs, required_keywords)

        return docs