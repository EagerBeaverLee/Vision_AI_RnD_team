from crewai import LLM

lms_llm = LLM(
    model="hosted_vllm/google/gemma-4-26b-a4b",
    base_url="http://192.168.0.110:9000/v1"
)