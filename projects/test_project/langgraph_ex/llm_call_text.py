# =====================================================================
# 🔥 [1단계. 필수 패치] Ragas 최신버전의 랭체인 레거시 경로 버그 우회
import sys
import os
from unittest.mock import MagicMock
sys.modules['langchain_community.chat_models.vertexai'] = MagicMock()
sys.modules['langchain_community.llms.vertexai'] = MagicMock()
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# =====================================================================

import json
import asyncio
import pandas as pd
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings as emb
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
# Ragas 0.4.x Collections 지표 및 임베딩
from ragas.llms import llm_factory
from ragas.embeddings import OpenAIEmbeddings
from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextRecall

from typing import TypedDict, List, Dict, Any, Annotated
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_community.vectorstores import FAISS

local_llm = ChatOpenAI(
    api_key="ai",
    model="meta-llama/Llama-3.1-8B-Instruct",
    base_url="http://192.168.0.110:8001/v1",
    temperature=0,
)

res = local_llm.invoke("데드리프트에 대해 알려줘")
print(res.content)
    
