import os
from pathlib import Path
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# -------------------------------------------------------------
# 1. 로컬 LLM 연결 설정 (Gemma 26B - vLLM / Ollama 호환 엔드포인트)
# -------------------------------------------------------------
# 로컬 서버 주소에 맞게 포트 번호(vLLM: 8000, Ollama: 11434 등)를 조정하세요.

local_llm = LLM(
    # model="hosted_vllm/nvidia/nemotron-3-nano",
    # model="hosted_vllm/nvidia/nemotron-3-nano",
    # model="hosted_vllm/nvidia/nemotron-3.5-lightning-30b-a3b",
    # model="hosted_vllm/openai/gpt-oss-120b",
    # model="hosted_vllm/google/gemma-4-26b-a4b",
    # model="hosted_vllm/google/gemma-4-31b",
    # model="hosted_vllm/qwen/qwen3.6-35b-a3b",
    # model="hosted_vllm/qwen/qwen3.8-27b",
    # model="hosted_vllm/zai-org/glm-4.7-flash",
    # base_url="http://192.168.0.110:9000/v1"

    model="hosted_vllm/RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic",
    base_url="http://192.168.0.110:8000/v1",
    api_key="ai",
    temperature=0.1


    # model="fireworks_ai/accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    # model="fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    # model="fireworks_ai/accounts/fireworks/models/muse-glimmer-30b",
    # model="fireworks_ai/accounts/fireworks/models/deepseek-v4p1-flash",
    # base_url="https://api.fireworks.ai/inference/v1",
    # api_key=os.getenv("FIREWORKS_API_KEY"),
    # max_retries=3,
    # temperature=0
)



# -------------------------------------------------------------
# 2. 실행 도구(Tools) 정의 (기존 3개 + 신규 2개)
# -------------------------------------------------------------
@tool("load_dataset_tool")
def load_dataset_tool(variable: str, lon_range: str, lat_range: str, time_range: str) -> str:
    """Load raw ocean grid data within a spatial-temporal bounding box."""
    print(f"\n[Tool 1] Loading {variable} ({lon_range}, {lat_range}, {time_range})")
    return "raw_dataset_ref_001"

@tool("apply_qc_mask_tool")
def apply_qc_mask_tool(dataset_ref: str, qc_threshold: float = 0.95) -> str:
    """Filter out invalid flags, land points, and abnormal spikes using quality control flags."""
    print(f"\n[Tool 2] Applying QC mask on {dataset_ref} (Threshold: {qc_threshold})")
    return "masked_dataset_ref_002"

@tool("regional_mean_tool")
def regional_mean_tool(dataset_ref: str) -> str:
    """Compute spatial average across lat/lon to reduce data to a 1D timeseries."""
    print(f"\n[Tool 3] Computing spatial mean on {dataset_ref}")
    return "timeseries_ref_003"

@tool("resample_tool")
def resample_tool(timeseries_ref: str, freq: str) -> str:
    """Resample 1D timeseries to a coarser frequency (e.g., 'M' for monthly, 'W' for weekly)."""
    print(f"\n[Tool 4] Resampling {timeseries_ref} to frequency '{freq}'")
    return "resampled_timeseries_ref_004"

@tool("plot_timeseries_tool")
def plot_timeseries_tool(timeseries_ref: str, title: str, output_path: str = "output_plot.png") -> str:
    """Render and save a line chart of the final resampled timeseries."""
    print(f"\n[Tool 5] Plotting chart from {timeseries_ref} -> '{output_path}' (Title: {title})")
    return f"Plot generated successfully at {output_path}"

# -------------------------------------------------------------
# 3. 스킬 파일 로드
# -------------------------------------------------------------
def load_skill_file(skill_path: str) -> str:
    path = Path(skill_path)
    if not path.exists():
        raise FileNotFoundError(f"스킬 파일을 찾을 수 없습니다: {skill_path}")
    return path.read_text(encoding="utf-8")

skill_doc = load_skill_file("skills/ocean_resampling.md")

# -------------------------------------------------------------
# 4. 에이전트 & 태스크 정의
# -------------------------------------------------------------
tool_list = [
    load_dataset_tool,
    apply_qc_mask_tool,
    regional_mean_tool,
    resample_tool,
    plot_timeseries_tool,
]

ocean_analyst = Agent(
    role="Senior Ocean Data Analyst",
    goal="정해진 스킬 절차서(Skill MD)의 5단계 순서와 인자를 철저히 지켜 분석 및 시각화를 완료한다.",
    backstory=(
        "당신은 해양 데이터 분석 파이프라인 전문가입니다. 제공된 매뉴얼에 명시되지 않은 "
        "임의의 순서로 도구를 호출하지 않으며, 전단계의 결과 참조자(Reference ID)를 다음 단계로 정확히 연결합니다."
    ),
    tools=tool_list,
    llm=local_llm,
    verbose=True,
)

user_query = "2023년 북서태평양(경도 120-140, 위도 20-35) 표층 수온(sst)을 로드하고, QC 마스크를 적용한 뒤 월별 평균으로 리샘플링하여 그래프로 저장해줘."

analysis_task = Task(
    description=f"""
사용자 요청:
\"{user_query}\"

아래 [스킬 매뉴얼]의 규칙과 5단계 순서를 엄격히 준수하여 도구를 순차 실행하세요:
---------------------------------------------
{skill_doc}
---------------------------------------------
반드시 Stage 1(Load) -> Stage 2(QC Mask) -> Stage 3(Regional Mean) -> Stage 4(Resample) -> Stage 5(Plot) 순서를 유지해야 합니다.
""",
    expected_output="5단계 도구 호출 실행 로그 및 최종 시각화 파일 저장 결과 요약",
    agent=ocean_analyst,
)

# -------------------------------------------------------------
# 5. 크루 실행
# -------------------------------------------------------------
crew = Crew(
    agents=[ocean_analyst],
    tasks=[analysis_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = crew.kickoff()
    print("\n================ [최종 산출물] ================")
    print(result)