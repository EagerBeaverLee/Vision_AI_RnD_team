from crewai import LLM
from langchain_openai import ChatOpenAI

lms_llm = LLM(
    model="hosted_vllm/RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic",
    base_url="http://192.168.0.110:8000/v1",
    api_key="ai"
)

vllm_llm = ChatOpenAI(
    model="RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic",
    base_url="http://192.168.0.110:8000/v1",
    api_key="ai",
)