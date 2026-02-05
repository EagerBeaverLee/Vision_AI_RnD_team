#######################################
### 3) Reciprocal Rank Fusion Class ### 
#######################################
from langchain_core.runnables import RunnableLambda, RunnablePassthrough #RunnableParallel
from langchain_core.prompts import ChatPromptTemplate

class ReciprocalRankFusionClass:
    def __init__(self, llm, chain): #vllm외부에서 정의 필요!

        self.llm = llm
        # self.multiple_question_class = MultipleQuestionGenerator()
        # self.multi_questions_gen_chain = self.multiple_question_class.multi_query_gen_chain
        self.multi_questions_gen_chain = chain

        self.rag_prompt_template = """
        Given a question and some context, answer the question. 
        If you do not know the answer, just say I do not know. 
        
        Context: {context}
        Question: {question}
        """
        
        self.init_prompts()

        
    def init_prompts(self):
        self.rag_prompt = ChatPromptTemplate.from_template(self.rag_prompt_template)

    def reciprocal_rank_fusion(self, results_groups: list[list], k=60):
        """ Reciprocal_rank_fusion that takes multiple groups of ranked documents 
            and an optional parameter k used in the Reciprocal Rank Fusion (RRF) formula """
        
        fused_scores = {}
        doc_lookup = {}
    
        for results_group in results_groups:
            for local_rank, doc in enumerate(results_group):
                doc_id = doc.id  # or doc.id, str(doc), etc.
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = 0
                    doc_lookup[doc_id] = doc
                fused_scores[doc_id] += 1 / (local_rank + k)
    
        reranked_results = [
            (doc_lookup[doc_id], score)
            for doc_id, score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        ]
        return reranked_results

    def build_reciprocal_rank_fusion_retriever(self, retriever=None, top_k=3):
        if not retriever:
            raise ValueError("Retriever is required to execute RRF retriever")

        top_k_results = RunnableLambda(lambda x: x[0:top_k])
        rag_fusion_retrieval_chain = (
            self.multi_questions_gen_chain
            | retriever.map() 
            | self.reciprocal_rank_fusion
            | top_k_results
        )
        
        return rag_fusion_retrieval_chain
        

    def build_RRF_rag_chain(self, retriever=None):
        if not retriever:
            raise ValueError("Retriever is required to execute RRF rag chain")

        rrf_rag_chain = (
            {
                "context": {"question": RunnablePassthrough()} | self.build_reciprocal_rank_fusion_retriever(retriever),
                "question": RunnablePassthrough(),
            }
            | RunnableLambda(self.print)
            | self.rag_prompt
            | self.llm
            # | StrOutputParser()
        )
        return rrf_rag_chain

    def generate_answer(self, user_question: str, retriever=None):
        if not retriever:
            raise ValueError("Retriever is required to execute RRF rag chain")

        final_rag_chain = self.build_RRF_rag_chain(retriever)
        rrf_final_result = final_rag_chain.invoke({"question": user_question})

        return rrf_final_result
    
    def print(self, val):
        print(val)
        return val




####사용예제
# Reciprocal_RRF 활성화
# testing_rrf = ReciprocalRankFusionClass()

# Reciprocal_RRF에서 multiple_question_generation 기능을 이용한 질문 생성
# testing_rrf.multi_questions_gen_chain.invoke(user_question) 

# 다양한 retriever를 이용한 RRF 기능 TEST
# retriever = default_pipeline.default_db.as_retriever()
# retriever = parent_pipeline.retriever
# retriever = summary_pipeline_testing.retriever
# retriever = hypothetical_pipe.retriever
# retriever = granular_exp_pipeline.retriever


# RRF_chain = testing_rrf.build_reciprocal_rank_fusion_retriever(retriever,top_k=4)
# RRF_chain.invoke({"question": results[8]})

# rrf_rag_chain = testing_rrf.build_RRF_rag_chain(retriever) 
# rrf_rag_chain.invoke({"question": results[16]})

# rrf_final_answer = testing_rrf.generate_answer(user_question=results[11], retriever=retriever)
# rrf_final_answer