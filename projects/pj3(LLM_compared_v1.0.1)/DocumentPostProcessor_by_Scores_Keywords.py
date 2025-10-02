
################################################################
### 1) & 2) score_threshold & keyword 기반 후처리 함수 클래스화 ###
################################################################

# Retriever는 외부에서 정의하고 시작함
import re

class DocumentPostProcessor:
    def __init__(self, retriever):
        self.retriever = retriever
        self.vectorstore = retriever.vectorstore

    def _filter_by_threshold(self, user_question: str, score_threshold: float):
        """score_threshold 기반 문서 필터링"""
        retr = self.vectorstore.as_retriever(
            search_type = "similarity_score_threshold",
            search_kwargs = {"score_threshold": score_threshold}
        )
        # return retr.get_relevant_documents(user_question)
        return retr.invoke(user_question)
    
    def get_threshold_retriver(self, score_threshold: float):
        """score_threshold 기반 문서 필터링"""
        retriever = self.retriever
        if not score_threshold:
            retriever = self.vectorstore.as_retriever(
                search_type = "similarity_score_threshold",
                search_kwargs = {"score_threshold": score_threshold}
            )
        return retriever

    def _filter_by_keywords(self, docs, required_keywords: set[str]):
        print("docs========")
        print(docs)
        print(required_keywords)
        """키워드 기반 문서 필터링"""
        # result = docs
        # if required_keywords:
        #     result = [doc for doc in docs if set(doc.page_content.split()).intersection(required_keywords)]
        # return result
        # res = [doc for doc in docs if set(doc.page_content.split()).intersection(required_keywords)]
        res = [doc for doc in docs if any(keyword in doc.page_content for keyword in required_keywords)]
        print("result========")
        print(res)
        return res

    def post_processor(
        self,
        user_question: str,
        score_threshold: float | None = None,
        required_keywords: set[str] | None = None
    ):
        # 1) score_threshold와 keywor 둘 다 없는 경우
        if score_threshold is None and not required_keywords:
            print(1)
            # return self.retriever.get_relevant_documents(user_question)
            return self.retriever.invoke(user_question)

        # 2) score_threshold만 있는 경우 
        if score_threshold is not None and not required_keywords:
            print(2)
            return self._filter_by_threshold(user_question, score_threshold)

        # 3) keywords만 있는 경우
        if score_threshold is None and required_keywords:
            print(3)
            # docs = self.retriever.get_relevant_documents(user_question)
            docs = self.retriever.invoke(user_question)
            return self._filter_by_keywords(docs, required_keywords)

        # 4) score_threshold & required_keywords 둘 다 있는 경우
        if score_threshold is not None and required_keywords:
            print(4)
            docs = self._filter_by_threshold(user_question, score_threshold)
            return self._filter_by_keywords(docs, required_keywords)