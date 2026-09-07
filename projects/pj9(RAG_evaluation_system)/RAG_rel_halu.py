from langchain_core.output_parsers import StrOutputParser
from langchain_core.utils.pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from langgraph.graph import END, StateGraph, START

from typing import List
from typing_extensions import TypedDict

class RAG_Rel_Halu:
    def __init__(self, retriever):
        self.retriever = retriever

    def build_graph(self):
        ### Retrieval Grader
        # Data model
        class GradeDocuments(BaseModel):
            """Binary score for relevance check on retrieved documents."""

            binary_score: str = Field(
                description="Documents are relevant to the question, 'yes' or 'no'"
            )
        # LLM with function call
        llm = ChatOpenAI(
            api_key="ai",
            model="openai/gpt-oss-20b",
            base_url="http://192.168.0.110:8000/v1",
            temperature=0,
        )

        structured_llm_grader = llm.with_structured_output(GradeDocuments)

        # Prompt
        system = """You are an objective evaluator assessing the relevance of a retrieved document to a user's question.
            Your task is to filter out completely off-topic or entirely irrelevant documents.

            CRITICAL INSTRUCTIONS:
            1. 'yes' means the document contains relevant background, context, or specific facts that directly or partially help answer the question.
            2. 'no' means the document is completely off-topic and lacks any semantic connection to the user's inquiry.
            3. DO NOT require exact keyword matches. Be lenient; if there is any topical connection or underlying semantic overlap, grade it as 'yes'.

            Give a binary score 'yes' or 'no'."""
        grade_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
            ]
        )

        retrieval_grader = grade_prompt | structured_llm_grader

        ### Generate
        pull = """
            You are a helpful and highly accurate assistant for question-answering tasks.
            Your primary task is to answer the user's question based strictly on the provided Context.

            CRITICAL INSTRUCTIONS:
            1. Grounding: Use ONLY the information provided in the Context. Do not use your pre-trained outside knowledge or fabricate any information.
            2. Fallback: If the provided Context does not contain the information needed to answer the question, answer using the knowledge you possess.
            3. Adaptive Detail: Match the length and detail of your answer to the complexity of the user's question. If the question requires a comprehensive explanation, provide a detailed response. If it asks for a simple fact, keep it concise
        """
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", pull),
                ("human", "Question: {question}, Context: {context} "),
            ]
        )

        # Chain
        rag_chain = prompt | llm | StrOutputParser()


        ### Hallucination Grader
        # Data model
        class GradeHallucinations(BaseModel):
            """Binary score for hallucination present in generation answer."""

            binary_score: str = Field(
                description="Answer is grounded in the facts, 'yes' or 'no'"
            )

        structured_llm_grader = llm.with_structured_output(GradeHallucinations)

        # Prompt
        system = """
            Your task is to determine if the answer suffers from severe hallucinations that distort the main facts.

            CRITICAL INSTRUCTIONS:
            1. 'yes' means the core message and primary facts in the answer are supported by the context. Minor additions of general knowledge, conversational filler, or slight deviations are acceptable as long as they do not contradict the provided context.
            2. 'no' means the answer fundamentally contradicts the context, or the main points are entirely fabricated and unrelated to the provided facts.
            3. Focus ONLY on general groundedness. Do not evaluate whether the answer completely resolves the user's question, only whether its main ideas are faithful to the context.

            Give a binary score 'yes' or 'no'.
        """
        hallucination_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Set of facts: \n\n {documents} \n\n LLM generation: {generation}"),
            ]
        )

        hallucination_grader = hallucination_prompt | structured_llm_grader

        ### Question Re-writer
        # Prompt
        system = """You are an expert question re-writer that converts an input question to a better version optimized for vectorstore retrieval. 
            Look at the input and reason about the underlying semantic intent and key entities.

            CRITICAL INSTRUCTIONS:
            1. Add relevant keywords, synonyms, or broader context that would improve search results.
            2. Remove conversational filler words.
            3. OUTPUT ONLY THE REWRITTEN QUERY. Do not include any introductory text, explanations, or quotes. Just the raw optimized string."""
        re_write_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                (
                    "human",
                    "Here is the initial question: \n\n {question} \n Formulate an improved question.",
                ),
            ]
        )

        question_rewriter = re_write_prompt | llm | StrOutputParser()

        class GraphState(TypedDict):
            """
            Represents the state of our graph.

            Attributes:
                question: question
                generation: LLM generation
                documents: list of documents
                hallucination_count: the maximum number counted by the hallucinatory response
            """
            question: str
            generation: str
            documents: List[str]
            rag_name: str
            hallucination_count: int


        def retrieve(state):
            """
            Retrieve documents

            Args:
                state (dict): The current graph state

            Returns:
                state (dict): New key added to state, documents, that contains retrieved documents
            """
            print(f"---[{state.get("rag_name","Unknown_RAG")}] RETRIEVE---")
            question = state["question"]

            # Retrieval
            documents = self.retriever.invoke(question)
            return {"documents": documents, "question": question, "hallucination_count": 0}


        def generate(state):
            """
            Generate answer

            Args:
                state (dict): The current graph state

            Returns:
                state (dict): New key added to state, generation, that contains LLM generation
            """
            print(f"---[{state.get("rag_name","Unknown_RAG")}] GENERATE---")
            question = state["question"]
            documents = state["documents"]

            # RAG generation
            generation = rag_chain.invoke({"context": documents, "question": question})
            return {"documents": documents, "question": question, "generation": generation}


        def grade_documents(state):
            """
            Determines whether the retrieved documents are relevant to the question.

            Args:
                state (dict): The current graph state

            Returns:
                state (dict): Updates documents key with only filtered relevant documents
            """

            print(f"---[{state.get("rag_name","Unknown_RAG")}] CHECK DOCUMENT RELEVANCE TO QUESTION---")
            question = state["question"]
            documents = state["documents"]

            # Score each doc
            filtered_docs = []
            for d in documents:
                score = retrieval_grader.invoke(
                    {"question": question, "document": d.page_content}
                )
                grade = score.binary_score
                if grade == "yes":
                    print(f"---[{state.get("rag_name","Unknown_RAG")}] GRADE: DOCUMENT RELEVANT---")
                    filtered_docs.append(d)
                else:
                    print(f"---[{state.get("rag_name","Unknown_RAG")}] GRADE: DOCUMENT NOT RELEVANT---")
                    continue
            return {"documents": filtered_docs, "question": question}


        def transform_query(state):
            """
            Transform the query to produce a better question.

            Args:
                state (dict): The current graph state

            Returns:
                state (dict): Updates question key with a re-phrased question
            """

            print(f"---[{state.get("rag_name","Unknown_RAG")}] TRANSFORM QUERY---")
            question = state["question"]
            documents = state["documents"]

            # Re-write question
            better_question = question_rewriter.invoke({"question": question})
            return {"documents": documents, "question": better_question}


        def decide_to_generate(state):
            """
            Determines whether to generate an answer, or re-generate a question.

            Args:
                state (dict): The current graph state

            Returns:
                str: Binary decision for next node to call
            """

            print(f"---[{state.get("rag_name","Unknown_RAG")}] ASSESS GRADED DOCUMENTS---")
            state["question"]
            filtered_documents = state["documents"]

            if not filtered_documents:
                # All documents have been filtered check_relevance
                # We will re-generate a new query
                print(
                    "---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, TRANSFORM QUERY---"
                )
                return "transform_query"
            else:
                # We have relevant documents, so generate answer
                print(f"---[{state.get("rag_name","Unknown_RAG")}] DECISION: GENERATE---")
                return "generate"


        def grade_generation_v_documents_and_question(state):
            """
            Determines whether the generation is grounded in the document and answers question.

            Args:
                state (dict): The current graph state

            Returns:
                str: Decision for next node to call
            """
            count = state["hallucination_count"]
            if count > 2:
                print(f"---[{state.get("rag_name","Unknown_RAG")}] HALLUCINATION COUNTING OVER---")
                return "fail"

            print(f"---[{state.get("rag_name","Unknown_RAG")}] CHECK HALLUCINATIONS---")
            documents = state["documents"]
            generation = state["generation"]

            score = hallucination_grader.invoke(
                {"documents": documents, "generation": generation}
            )
            grade = score.binary_score

            # Check hallucination
            if grade == "yes":
                print(f"---[{state.get("rag_name","Unknown_RAG")}] DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
                return "useful"
            else:
                print(f"---[{state.get("rag_name","Unknown_RAG")}] DECISION: GENERATION IS NOT GROUNDED IN DOCUMENTS, RE-TRY---")
                return "not supported"
            
        def check_hallucination_count(state):
            """
            Counts when hallucinations occur

            Arguments:
                state (dictionary): Current graph state

            Return:
                int: Total number of hallucinations
            """
            current_h_count = state["hallucination_count"]
            print(f"---[{state.get("rag_name","Unknown_RAG")}] HALLUCINATION COUNT: {current_h_count+1} ---")
            return {"hallucination_count": current_h_count + 1}

        workflow = StateGraph(GraphState)

        # Define the nodes
        workflow.add_node("retrieve", retrieve)  # retrieve
        workflow.add_node("grade_documents", grade_documents)  # grade documents
        workflow.add_node("generate", generate)  # generate
        workflow.add_node("transform_query", transform_query)  # transform_query
        workflow.add_node("check", check_hallucination_count)

        # Build graph
        workflow.add_edge(
            START, "retrieve"
        )

        workflow.add_edge("retrieve", "grade_documents")
        workflow.add_conditional_edges(
            "grade_documents",
            decide_to_generate,
            {
                "transform_query": "transform_query",
                "generate": "generate",
            },
        )
        workflow.add_edge("transform_query", "retrieve")
        workflow.add_conditional_edges(
            "generate",
            grade_generation_v_documents_and_question,
            {
                "fail": END,
                "not supported": "check",
                "useful": END,
            },
        )
        workflow.add_edge("check", "generate")

        # Compile
        adaptive_graph = workflow.compile()

        return adaptive_graph