import os
from pathlib import Path
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# -------------------------------------------------------------
# 1. 로컬 LLM 설정 (Gemma 26B)
# -------------------------------------------------------------
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
# 2. 공용 실행 도구 풀 (Shared Tools Pool)
# -------------------------------------------------------------
@tool("load_dataset_tool")
def load_dataset_tool(variable: str, lon_range: str, lat_range: str, time_range: str) -> str:
    """Load raw ocean grid data within a spatial-temporal bounding box."""
    print(f"\n[Tool Execution] Loading {variable} ({lon_range}, {lat_range}, {time_range})")
    return "raw_dataset_ref_001"

@tool("apply_qc_mask_tool")
def apply_qc_mask_tool(dataset_ref: str, qc_threshold: float = 0.95) -> str:
    """Filter out invalid flags, abnormal spikes, and land points."""
    print(f"\n[Tool Execution] Applying QC mask on {dataset_ref} (Threshold: {qc_threshold})")
    return "masked_dataset_ref_002"

@tool("regional_mean_tool")
def regional_mean_tool(dataset_ref: str) -> str:
    """Compute spatial average across lat/lon to produce a 1D timeseries."""
    print(f"\n[Tool Execution] Computing spatial mean on {dataset_ref}")
    return "timeseries_ref_003"

@tool("resample_tool")
def resample_tool(timeseries_ref: str, freq: str) -> str:
    """Resample 1D timeseries to a coarser frequency (e.g., 'M' for monthly, 'W' for weekly)."""
    print(f"\n[Tool Execution] Resampling {timeseries_ref} to frequency '{freq}'")
    return "resampled_timeseries_ref_004"

@tool("plot_timeseries_tool")
def plot_timeseries_tool(timeseries_ref: str, title: str, output_path: str = "output_plot.png") -> str:
    """Render and save a chart of the processed data."""
    print(f"\n[Tool Execution] Plotting chart from {timeseries_ref} -> '{output_path}' ({title})")
    return f"Plot successfully saved to {output_path}"

# -------------------------------------------------------------
# 3. 스킬 레지스트리 및 라우터 (Skill Registry & Router)
# -------------------------------------------------------------
SKILLS = {
    "ocean_resampling": {
        "file": "skills/ocean_resampling.md",
        "description": "시계열 데이터를 로드하여 QC 마스킹 후 공간 평균을 구하고, 주간/월간 등으로 리샘플링하여 시각화할 때 사용.",
    },
    "spatial_anomaly": {
        "file": "skills/ocean_spatial_anomaly.md",
        "description": "리샘플링 없이 특정 시점의 데이터에서 이상치/결측치를 필터링하고 이상치 분포를 즉시 시각화할 때 사용.",
    },
}

def route_skill(query: str) -> str:
    """사용자 질의를 기반으로 가장 적합한 스킬 ID를 판별합니다."""
    prompt = f"""
다음은 지원하는 분석 스킬 목록입니다:
1. ocean_resampling: {SKILLS['ocean_resampling']['description']}
2. spatial_anomaly: {SKILLS['spatial_anomaly']['description']}

사용자 질문: "{query}"

위 사용자 질문에 가장 적합한 스킬 ID 1개만 출력하세요 (예: ocean_resampling 또는 spatial_anomaly). 다른 설명이나 문장은 출력하지 마세요.
"""
    response = local_llm.call([{"role": "user", "content": prompt}])
    selected = response.strip().lower()
    
    if "anomaly" in selected:
        return "spatial_anomaly"
    return "ocean_resampling"

def load_skill_content(skill_id: str) -> str:
    file_path = SKILLS[skill_id]["file"]
    return Path(file_path).read_text(encoding="utf-8")

# -------------------------------------------------------------
# 4. 동적 에이전트 파이프라인 실행
# -------------------------------------------------------------
def run_dynamic_pipeline(user_query: str):
    # Step 1: 질의 의도에 부합하는 스킬 선택
    selected_skill_id = route_skill(user_query)
    print(f"\n[Router] 선택된 스킬 ID: {selected_skill_id}")
    
    # Step 2: 해당 스킬 파일 로드
    selected_skill_doc = load_skill_content(selected_skill_id)

    # Step 3: 에이전트 및 태스크 구성
    ocean_analyst = Agent(
        role="Ocean Data Workflow Specialist",
        goal="선택된 스킬 가이드(Skill MD)의 절차를 위반하지 않고 정확하게 도구를 호출해 분석을 완료한다.",
        backstory="당신은 엄격한 절차형 에이전트입니다. 주입된 지침에 정의된 순서와 도구만 실행합니다.",
        tools=[load_dataset_tool, apply_qc_mask_tool, regional_mean_tool, resample_tool, plot_timeseries_tool],
        llm=local_llm,
        verbose=True,
    )

    analysis_task = Task(
        description=f"""
사용자 요청:
\"{user_query}\"

아래 [동적 주입된 스킬 가이드]를 철저히 준수하여 도구를 호출하세요:
---------------------------------------------
{selected_skill_doc}
---------------------------------------------
스킬 가이드의 Execution Rules에 명시된 순서대로만 도구를 체이닝하세요.
""",
        expected_output="스킬 단계별 실행 내역 및 최종 산출물 요약",
        agent=ocean_analyst,
    )

    crew = Crew(
        agents=[ocean_analyst],
        tasks=[analysis_task],
        process=Process.sequential,
        verbose=True,
    )
    return crew.kickoff()

# -------------------------------------------------------------
# 5. 실행 테스트
# -------------------------------------------------------------
if __name__ == "__main__":
    # Case A: 리샘플링 의도 질문
    query_a = "2023년 동해 수온을 가져와서 QC 마스크 씌우고 월별 평균으로 다운샘플링해서 차트로 뽑아줘."
    print("\n================== [테스트 1: 리샘플링 요청] ==================")
    run_dynamic_pipeline(query_a)

    # Case B: 이상치 감지 의도 질문
    # query_b = "지난달 북서태평양 수온 데이터에서 비정상적인 스파이크와 결측치를 걸러내고 이상치 분포 그래프를 확인하고 싶어."
    # print("\n================== [테스트 2: 이상치 감지 요청] ==================")
    # run_dynamic_pipeline(query_b)

    # query = "최근 관측된 동해 수온 데이터에서 품질 기준(임계값 0.90)에 미달하는 불량 관측 지점 및 이상치 격자 분포를 시각화해서 확인하고 싶어."
    # print("\n================== [테스트 1: 리샘플링 요청] ==================")
    # run_dynamic_pipeline(query)

# 시나리오 1: 시간 축 리샘플링 및 다운샘플링 (ocean_resampling)

# "2023년 한반도 연안(경도 124~132, 위도 33~39)의 일별 표층 염분(so) 데이터를 QC 필터링 거친 뒤, 주간(Weekly) 평균 시계열로 집계해서 선 그래프로 그려줘."

# "지난 5년간 북태평양 아열대 해역의 수온 데이터를 로드해서 이상치를 제거하고, 월별 평균 변화 추이를 비교할 수 있는 시계열 차트를 생성해줘."

# "작년 남해안 해수면 온도 데이터를 불러와서 품질 검증 마스크를 적용한 다음, 분기별(Quarterly) 평균으로 다운샘플링한 결과를 확인하고 싶어."

# "2022년 여름철 동해 중부 격자 수온 자료의 불량 플래그를 정제하고, 10일 단위(10-day mean) 평균 시계열로 변환해서 플롯 파일로 저장해줘."

# "경도 130~145, 위도 25~35 구역의 일일 해류 유속(uo) 데이터를 로드해서 결측치를 걸러낸 후, 월 단위 평균 시계열로 변환해 시각화해줘."



# 시나리오 2: 이상치 필터링 및 공간 분포 시각화 (spatial_anomaly)

# "지난주 태풍 통과 직후 동중국해 해수면 온도 격자 데이터에서 비정상적인 급변 스파이크와 결측치 영역을 QC 마스크로 걸러내고 그 분포를 차트로 보여줘."

# "2023년 8월 15일 기준 북서태평양 표층 염분 데이터에서 센서 오류로 의심되는 이상치 플래그 구역을 추출해서 플롯으로 저장해줘."

# "최근 관측된 동해 수온 데이터에서 품질 기준(임계값 0.90)에 미달하는 불량 관측 지점 및 이상치 격자 분포를 시각화해서 확인하고 싶어."

# "올해 1월 쿠로시오 해류 유역의 수온 데이터셋을 로드해서 극단값(Outlier)과 육지 마스크를 적용한 뒤 남은 유효 영역 분포를 바로 시각화해줘."

# "2023년 특정 일자의 황해 수온 관측값 중 QC 임계치를 벗어난 비정상 고온/저온 이상치 영역을 필터링해서 즉각 그래프로 확인하게 해줘."