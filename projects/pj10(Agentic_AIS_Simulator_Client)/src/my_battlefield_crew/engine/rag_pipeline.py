import os
import asyncio
import threading
from typing import AsyncGenerator, Optional, List
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from my_battlefield_crew.RAG.Retriever.DefaultRetriever import DefaultRetriever
from my_battlefield_crew.RAG.Retriever.ParentChildDocumentRetriever import ParentRetriverPipeline
from my_battlefield_crew.RAG.Retriever.SummaryDocumentRetriever import SummaryDocumentRetrieverPipeline
from my_battlefield_crew.RAG.Retriever.HypotheticalQuestionRetrieverPipeline import HypotheticalQuestionRetrieverPipeline
from my_battlefield_crew.RAG.Retriever.GranularChunkExpansionRetriever import GranularChunkExpansionRetriverPipeline
from my_battlefield_crew.RAG.Retriever.parent_keyword_retriever import ParentKeywordRetrieverPipeline


from my_battlefield_crew.setting.llm_config import LLMConfig
from my_battlefield_crew.setting.rag_config import (
    RAGConfig, IndexingType, QuestionTransformType
)
from my_battlefield_crew.RAG.DocumentPostProcessor import DocumentPostProcessor
from my_battlefield_crew.setting.LLM_model_set import vllm_llm

class RAGPipeline:
    """RAG 인덱싱, 진행률 스트리밍, 질문 변환, 검색 및 후처리를 총괄하는 통합 파이프라인"""
    def __init__(self, rag_config: Optional[RAGConfig] = None, llm_config: Optional[LLMConfig] = None):
        self.llm_config: LLMConfig = llm_config or LLMConfig()
        self.rag_config: RAGConfig = rag_config or RAGConfig()
        self.vector_store: Optional[FAISS] = None
        self.retriever = None
        self.post_processor: Optional[DocumentPostProcessor] = None
        
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.llm = vllm_llm

    def update_config(self, new_config: RAGConfig):
        """Qt 클라이언트로부터 변경된 설정을 런타임에 갱신"""
        self.rag_config = new_config

    def is_valid_retriever(self, target_obj) -> bool:
        """
        Retriever 또는 Pipeline 래퍼 객체의 정상 상태를 다각도로 검증
        """
        if target_obj is None:
            return False

        # 1. 래퍼 클래스인 경우 내부 retriever / vectorstore 추출
        retriever = getattr(target_obj, "retriever", target_obj)
        vectorstore = getattr(retriever, "vectorstore", None) or getattr(target_obj, "vector_store", None)

        # 2. FAISS 인덱스 적재량(ntotal) 검사
        if vectorstore is not None:
            if hasattr(vectorstore, "index") and hasattr(vectorstore.index, "ntotal"):
                if vectorstore.index.ntotal <= 0:
                    print("[검증 실패] FAISS 인덱스에 적재된 벡터가 0개입니다.")
                    return False
            else:
                print("[실패]index와 ntotal없음")
                return False
        else:
            # vectorstore 속성을 직접 노출하지 않는 retriever라면 invoke 가능 여부로 판단
            pass

        # 3. 런타임 검색 호출 가능 여부 테스트
        try:
            if hasattr(retriever, "invoke"):
                test_res = retriever.invoke("헬스체크")
                print("retriever에 invoke 존재")
                return isinstance(test_res, list)
            elif hasattr(retriever, "get_relevant_documents"):
                test_res = retriever.get_relevant_documents("헬스체크")
                print("retriever에 get_relevant_documents 존재")
                return isinstance(test_res, list)
        except Exception as e:
            print(f"[검증 실패] Retriever 쿼리 테스트 중 에러: {e}")
            return False

        print("전부 해당사항 없음")
        return True

    def _setup_retriever(self):
        strategy = self.rag_config.indexing.strategy
        strategy_key = strategy.value if hasattr(strategy, "value") else str(strategy)
        
        idx_cfg = self.rag_config.indexing
        api_key = os.getenv("OPENAI_API_KEY")
        source_path = self.rag_config.source_path

        # 💡 각 생성 로직을 람다로 묶어 지연 실행 테이블 구축
        retriever_factories = {
            IndexingType.DEFAULT.value: lambda: DefaultRetriever(
                folder_path=source_path, 
                api_key=api_key
            ),
            IndexingType.PARENT_RETRIEVER.value: lambda: ParentRetriverPipeline(
                folder_path=source_path,
                openai_api_key=api_key,
                parent_chunk_size=idx_cfg.parent_chunk_size,
                child_chunk_size=idx_cfg.child_chunk_size
            ),
            IndexingType.SUMMARY.value: lambda: SummaryDocumentRetrieverPipeline(
                folder_path=source_path,
                openai_api_key=api_key,
                parent_chunk_size=idx_cfg.parent_chunk_size,
                llm_model=self.llm
            ),
            IndexingType.HYPOTHETICAL.value: lambda: HypotheticalQuestionRetrieverPipeline(
                folder_path=source_path,
                openai_api_key=api_key,
                parent_chunk_size=idx_cfg.parent_chunk_size,
                llm_model=self.llm
            ),
            IndexingType.GRANULAR.value: lambda: GranularChunkExpansionRetriverPipeline(
                folder_path=source_path,
                openai_api_key=api_key,
                granular_chunk_size=idx_cfg.chunk_size
            ),
            IndexingType.PARENT_KEYWORD.value: lambda: ParentKeywordRetrieverPipeline(
                folder_path=source_path,
                openai_api_key=api_key,
                k=idx_cfg.k,
                weight=idx_cfg.weight
            ),
        }
        print(f"{self.rag_config.question_transform}\n{self.rag_config.post_processing}\n{self.rag_config.indexing.strategy}\n{self.rag_config.source_path}")

        # 선택된 것만 호출하여 인스턴스화
        creator = retriever_factories.get(strategy_key, retriever_factories[IndexingType.DEFAULT.value])
        return creator()

    async def _stream_thread_generator(self, retriever_class, cancel_event: asyncio.Event):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # 2. 동기 스레드에 넘겨줄 스레드 전용 취소 플래그 생성
        sync_cancel_flag = threading.Event()

        # 3. 비동기 취소 이벤트(cancel_event)가 켜지면 동기 플래그도 켜지도록 연동 타스크 실행
        async def watch_cancel():
            try:
                await cancel_event.wait()
                sync_cancel_flag.set() # 동기 스레드에 중단 신호 전달
            except asyncio.CancelledError:
                pass  

        cancel_wait_task = asyncio.create_task(watch_cancel())

        def worker_wrapper():
            try:
                # 동기 제너레이터를 돌리면서 나오는 값을 실시간으로 큐에 push
                for item in retriever_class.run(sync_cancel_flag):
                    loop.call_soon_threadsafe(queue.put_nowait, item)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                # 데이터가 끝났음을 알리는 종료 신호 (Sentinel)
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # 백엔드 스레드에서 작업을 시작 (await 하지 않고 백그라운드 구동)
        worker_task = asyncio.create_task(asyncio.to_thread(worker_wrapper))

        try:
            while True:
                if cancel_event.is_set():
                    print("스레드 내부에서 취소 신호 감지")
                    yield "CANCELLED\n"
                    return

                # 큐에서 데이터가 나오거나, 취소 이벤트가 켜지는 것 중 '먼저 일어나는 것'을 대기
                # 이 방식은 대기하는 동안 CPU 부하가 0% 입니다.
                queue_task = asyncio.create_task(queue.get())

                done, pending = await asyncio.wait(
                    {queue_task, cancel_wait_task},
                    return_when=asyncio.FIRST_COMPLETED
                )

                # 취소가 먼저 되었다면 즉시 루프 상단으로 이동해 CANCELLED 처리 (반응성 최고)
                if cancel_wait_task in done:
                    queue_task.cancel() # 미처 처리 안 된 큐 작업 취소
                    continue

                # 큐에서 정상적으로 데이터를 꺼낸 경우
                item = await queue_task
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                
                yield item
                
        finally:
            # 모든 태스크 및 스레드 안전하게 정리
            cancel_wait_task.cancel()
            sync_cancel_flag.set()
            await worker_task

    async def build_vectorstore(self, cancel_event: asyncio.Event) -> AsyncGenerator[str, None]:
        last_signal = None
        # 선택된 retriever 준비
        retriever_class = self._setup_retriever()
        # 준비된 retriever를 이용해 임베딩 벡터스토어 생성
        async for signal in self._stream_thread_generator(retriever_class=retriever_class, cancel_event=cancel_event):
            last_signal = signal
            yield signal

        if last_signal == "COMPLETE\n":
            # DefaultRetriever에 구현된 메서드를 통해 DB와 Retriever 추출
            self.retriever = retriever_class.copy_retriever()
            self.post_processor = DocumentPostProcessor(retriever=self.retriever)
            if hasattr(self.retriever, "vector_store"):
                self.vector_store = retriever_class.copy_vectorstore()
            print("[RAGPipeline] FAISS VectorStore 및 Retriever 인스턴스 저장 완료")
            yield "COMPLETE\n"
        else:
            print(f"[RAGPipeline] 작업이 정상 완료되지 않음: {last_signal}")
            yield "CANCELLED\n"