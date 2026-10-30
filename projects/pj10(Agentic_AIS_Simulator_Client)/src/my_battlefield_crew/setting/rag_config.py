from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class QuestionTransformType(str, Enum):
    DEFAULT = "Default"
    REWRITE_RETRIEVE_READ = "Rewrite-Retrieve-Read Generator"
    MULTIPLE_QUESTIONS = "Multiple Questions Generator"
    STEP_BACK = "Step-Back Question Generator"


class IndexingType(str, Enum):
    DEFAULT = "Default"
    PARENT_RETRIEVER = "ParentRetriverPipeline"
    SUMMARY = "Summary"
    HYPOTHETICAL = "Hypothetical"
    GRANULAR = "Granular"
    PARENT_KEYWORD = "ParentKeywordRetriever"


class IndexingConfig(BaseModel):
    strategy: IndexingType = IndexingType.DEFAULT
    parent_chunk_size: int = 0
    child_chunk_size: int = 0
    chunk_size: int = 0
    k: int = 0
    weight: int = 0


class PostProcessingConfig(BaseModel):
    use_similarity: bool = False
    similarity_threshold: float = 0.0
    use_keywords: bool = False
    keywords: str = ""
    use_rrf: bool = False  # Reciprocal Rank Fusion


class RAGConfig(BaseModel):
    question_transform: QuestionTransformType = QuestionTransformType.DEFAULT
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    post_processing: PostProcessingConfig = Field(default_factory=PostProcessingConfig)
    source_path: str = ""