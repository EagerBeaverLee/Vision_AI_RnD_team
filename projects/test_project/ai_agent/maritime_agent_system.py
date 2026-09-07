from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Literal, Protocol, TypedDict

from pydantic import BaseModel, Field

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


ToolId = Literal[
    "weather_korean_peninsula",
    "vessel_track_detail",
    "fleet_od_flow",
    "fleet_density_by_area",
    "fleet_speed_by_area",
    "fleet_anomalous_movement",
    "fleet_direction_8way",
]


class Intent(str, Enum):
    WEATHER = "weather"
    VESSEL_DETAIL = "vessel_detail"
    OD_FLOW = "od_flow"
    FLEET_DENSITY = "fleet_density"
    FLEET_SPEED = "fleet_speed"
    ANOMALOUS_MOVEMENT = "anomalous_movement"
    FLEET_DIRECTION = "fleet_direction"
    TRAFFIC_SUMMARY = "traffic_summary"
    MARITIME_RISK_SUMMARY = "maritime_risk_summary"
    FLEET_OVERVIEW = "fleet_overview"
    MULTI_TOOL_ANALYSIS = "multi_tool_analysis"
    UNKNOWN = "unknown"


class AgentName(str, Enum):
    WEATHER = "WeatherAgent"
    VESSEL_DETAIL = "VesselDetailAgent"
    FLEET_ANALYTICS = "FleetAnalyticsAgent"
    INSIGHT = "InsightAgent"
    CLARIFICATION = "ClarificationAgent"
    VERIFIER = "VerifierAgent"


class ToolMetadata(BaseModel):
    tool_id: ToolId
    source_number: int
    agent: AgentName
    name: str
    description: str
    required_slots: list[str] = Field(default_factory=list)
    optional_slots: list[str] = Field(default_factory=list)
    output_type: str
    freshness: str = "realtime"
    cache_ttl_seconds: int = 60
    keywords: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    can_parallelize: bool = True


class CandidateIntent(BaseModel):
    intent: Intent
    score: float
    required_tools: list[ToolId]
    reason: str


class RouteDecision(BaseModel):
    selected_intent: Intent
    intent_candidates: list[CandidateIntent]
    required_tools: list[ToolId]
    confidence: float
    needs_clarification: bool
    reason: str


class ToolCall(BaseModel):
    tool_id: ToolId
    agent: AgentName
    args: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    steps: list[ToolCall]
    parallel_groups: list[list[ToolId]]
    rationale: str


class ToolResult(BaseModel):
    tool_id: ToolId
    agent: AgentName
    status: Literal["ok", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: utc_now_iso())
    cached: bool = False


class ValidationReport(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    retryable: bool = False


class Slots(BaseModel):
    vessel_name: str | None = None
    mmsi: str | None = None
    region: str | None = None
    metrics: list[str] = Field(default_factory=list)
    time_scope: str = "current"

    @property
    def vessel_name_or_mmsi(self) -> str | None:
        return self.mmsi or self.vessel_name


class GraphState(TypedDict, total=False):
    raw_query: str
    normalized_query: str
    slots: dict[str, Any]
    route_decision: dict[str, Any]
    selected_intent: str
    plan: dict[str, Any]
    tool_results: dict[str, Any]
    normalized_results: dict[str, Any]
    validation: dict[str, Any]
    answer: str
    clarification_question: str
    trace: dict[str, Any]
    retry_count: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_tool_registry() -> dict[ToolId, ToolMetadata]:
    registry = [
        ToolMetadata(
            tool_id="weather_korean_peninsula",
            source_number=1,
            agent=AgentName.WEATHER,
            name="현재 한반도 평균 날씨",
            description=(
                "현재 한반도의 평균 풍향, 풍속, 기온, 수온, 최대파고, "
                "유의파고, 평균파고, 순간풍속, 습도 결과를 반환"
            ),
            required_slots=[],
            optional_slots=["region", "time_scope"],
            output_type="weather_and_sea_state",
            cache_ttl_seconds=300,
            keywords=[
                "날씨",
                "기상",
                "풍향",
                "풍속",
                "기온",
                "수온",
                "파고",
                "최대파고",
                "유의파고",
                "평균파고",
                "순간풍속",
                "습도",
                "해상상태",
            ],
            metrics=["wind_direction", "wind_speed", "air_temperature", "water_temperature", "wave_height"],
        ),
        ToolMetadata(
            tool_id="vessel_track_detail",
            source_number=2,
            agent=AgentName.VESSEL_DETAIL,
            name="특정 선박 상세 항적",
            description="선박의 이름 또는 MMSI를 명시했을 때 특정 선박에 대한 자세한 항적 정보를 반환",
            required_slots=["vessel_name_or_mmsi"],
            optional_slots=["time_scope"],
            output_type="vessel_track",
            cache_ttl_seconds=30,
            keywords=[
                "항적",
                "선박명",
                "선명",
                "mmsi",
                "선박",
                "특정",
                "위치",
                "경로",
                "이동경로",
                "추적",
            ],
            metrics=["position", "course", "speed", "track"],
        ),
        ToolMetadata(
            tool_id="fleet_od_flow",
            source_number=3,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 OD flow 분석",
            description="현재 운항중인 전체 선박의 OD flow 분석 결과를 반환",
            required_slots=[],
            optional_slots=["region", "time_scope"],
            output_type="fleet_od_flow",
            cache_ttl_seconds=120,
            keywords=["od", "o/d", "origin", "destination", "출발", "도착", "흐름", "flow", "이동흐름", "항로"],
            metrics=["origin", "destination", "flow_count"],
        ),
        ToolMetadata(
            tool_id="fleet_density_by_area",
            source_number=4,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 구역별 밀집 현황",
            description="현재 운항중인 전체 선박의 구역별 밀집 현황 분석 결과를 반환",
            required_slots=[],
            optional_slots=["region", "time_scope"],
            output_type="fleet_density_by_area",
            cache_ttl_seconds=60,
            keywords=["밀집", "밀도", "혼잡", "구역별", "분포", "붐비", "많은", "선박수", "집중"],
            metrics=["area", "vessel_count", "density_level"],
        ),
        ToolMetadata(
            tool_id="fleet_speed_by_area",
            source_number=5,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 구역별 이동속도 요약",
            description="현재 운항중인 전체 선박의 구역별 이동속도 요약 결과를 반환",
            required_slots=[],
            optional_slots=["region", "time_scope"],
            output_type="fleet_speed_by_area",
            cache_ttl_seconds=60,
            keywords=["속도", "이동속도", "저속", "고속", "평균속도", "감속", "정체", "느린", "빠른"],
            metrics=["area", "avg_speed", "min_speed", "max_speed"],
        ),
        ToolMetadata(
            tool_id="fleet_anomalous_movement",
            source_number=6,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 특이기동 분석",
            description="현재 운항중인 전체 선박 중 특이 기동 선박의 기동결과 및 선정 기준 결과를 반환",
            required_slots=[],
            optional_slots=["region", "time_scope"],
            output_type="fleet_anomalous_movement",
            cache_ttl_seconds=60,
            keywords=[
                "특이기동",
                "이상기동",
                "이상운항",
                "급선회",
                "급가속",
                "급감속",
                "비정상",
                "선정기준",
                "기준",
                "위험",
                "주의",
            ],
            metrics=["vessel", "anomaly_type", "criteria"],
        ),
        ToolMetadata(
            tool_id="fleet_direction_8way",
            source_number=7,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 8방위 이동방향 분석",
            description="현재 운항중인 전체 선박이 8방위 중 어디로 이동중인지 분석 결과를 반환",
            required_slots=[],
            optional_slots=["region", "time_scope"],
            output_type="fleet_direction_8way",
            cache_ttl_seconds=60,
            keywords=[
                "방향",
                "이동방향",
                "8방위",
                "팔방위",
                "북쪽",
                "남쪽",
                "동쪽",
                "서쪽",
                "북동",
                "북서",
                "남동",
                "남서",
                "침로",
            ],
            metrics=["direction", "count", "ratio"],
        ),
    ]
    return {tool.tool_id: tool for tool in registry}


INTENT_TOOLS: dict[Intent, list[ToolId]] = {
    Intent.WEATHER: ["weather_korean_peninsula"],
    Intent.VESSEL_DETAIL: ["vessel_track_detail"],
    Intent.OD_FLOW: ["fleet_od_flow"],
    Intent.FLEET_DENSITY: ["fleet_density_by_area"],
    Intent.FLEET_SPEED: ["fleet_speed_by_area"],
    Intent.ANOMALOUS_MOVEMENT: ["fleet_anomalous_movement"],
    Intent.FLEET_DIRECTION: ["fleet_direction_8way"],
    Intent.TRAFFIC_SUMMARY: [
        "fleet_density_by_area",
        "fleet_speed_by_area",
        "fleet_direction_8way",
        "fleet_od_flow",
    ],
    Intent.MARITIME_RISK_SUMMARY: [
        "weather_korean_peninsula",
        "fleet_density_by_area",
        "fleet_speed_by_area",
        "fleet_anomalous_movement",
        "fleet_direction_8way",
    ],
    Intent.FLEET_OVERVIEW: [
        "fleet_od_flow",
        "fleet_density_by_area",
        "fleet_speed_by_area",
        "fleet_anomalous_movement",
        "fleet_direction_8way",
    ],
    Intent.MULTI_TOOL_ANALYSIS: [],
    Intent.UNKNOWN: [],
}


TOOL_TO_INTENT: dict[ToolId, Intent] = {
    "weather_korean_peninsula": Intent.WEATHER,
    "vessel_track_detail": Intent.VESSEL_DETAIL,
    "fleet_od_flow": Intent.OD_FLOW,
    "fleet_density_by_area": Intent.FLEET_DENSITY,
    "fleet_speed_by_area": Intent.FLEET_SPEED,
    "fleet_anomalous_movement": Intent.ANOMALOUS_MOVEMENT,
    "fleet_direction_8way": Intent.FLEET_DIRECTION,
}


class LLMRouter(Protocol):
    def route(self, normalized_query: str, slots: Slots, registry: dict[ToolId, ToolMetadata]) -> RouteDecision | None:
        """Return a structured route decision, or None when the LLM is unavailable."""


class NoopLLMRouter:
    def route(self, normalized_query: str, slots: Slots, registry: dict[ToolId, ToolMetadata]) -> RouteDecision | None:
        return None


class QueryNormalizer:
    MMSI_PATTERN = re.compile(r"\b\d{9}\b")
    VESSEL_PATTERNS = [
        re.compile(r"(?:선박명|선명|선박 이름|이름)\s*[:은는이가]*\s*([A-Za-z0-9가-힣 _.-]{2,40})"),
        re.compile(r"([A-Za-z][A-Za-z0-9 _.-]{2,40})\s*(?:호|선박)?\s*(?:항적|위치|경로|추적)"),
    ]
    REGIONS = ["서해", "남해", "동해", "부산", "인천", "울산", "제주", "목포", "여수", "포항", "군산", "마산"]
    METRIC_SYNONYMS = {
        "풍향": "wind_direction",
        "풍속": "wind_speed",
        "순간풍속": "gust_speed",
        "기온": "air_temperature",
        "수온": "water_temperature",
        "최대파고": "max_wave_height",
        "유의파고": "significant_wave_height",
        "평균파고": "avg_wave_height",
        "파고": "wave_height",
        "습도": "humidity",
        "밀집": "density",
        "혼잡": "density",
        "속도": "speed",
        "특이기동": "anomaly",
        "이상운항": "anomaly",
        "방향": "direction",
        "8방위": "direction_8way",
        "od": "od_flow",
    }

    def normalize(self, raw_query: str) -> tuple[str, Slots]:
        normalized = " ".join(raw_query.strip().lower().split())
        slots = Slots()

        mmsi_match = self.MMSI_PATTERN.search(raw_query)
        if mmsi_match:
            slots.mmsi = mmsi_match.group(0)

        if slots.mmsi is None:
            for pattern in self.VESSEL_PATTERNS:
                match = pattern.search(raw_query)
                if match:
                    candidate = match.group(1).strip(" .,:;")
                    if not self._looks_like_metric_phrase(candidate):
                        slots.vessel_name = candidate
                        break

        for region in self.REGIONS:
            if region in raw_query:
                slots.region = region
                break

        metrics = []
        for source, canonical in self.METRIC_SYNONYMS.items():
            if source in normalized or source in raw_query:
                metrics.append(canonical)
        slots.metrics = sorted(set(metrics))

        if any(token in raw_query for token in ["현재", "지금", "운항중", "운항 중"]):
            slots.time_scope = "current"

        return normalized, slots

    @staticmethod
    def _looks_like_metric_phrase(value: str) -> bool:
        blocked = ["전체", "현재", "운항", "날씨", "밀집", "속도", "방향", "특이", "위험"]
        return any(token in value for token in blocked)


class HybridRouter:
    HIGH_CONFIDENCE = 0.75
    LOW_CONFIDENCE = 0.45

    def __init__(self, registry: dict[ToolId, ToolMetadata], llm_router: LLMRouter | None = None) -> None:
        self.registry = registry
        self.llm_router = llm_router or NoopLLMRouter()

    def route(self, normalized_query: str, slots: Slots) -> RouteDecision:
        deterministic_decision = self._deterministic_route(normalized_query, slots)
        if deterministic_decision.confidence >= self.HIGH_CONFIDENCE:
            return deterministic_decision

        llm_decision = self.llm_router.route(normalized_query, slots, self.registry)
        if llm_decision is not None and llm_decision.confidence > deterministic_decision.confidence:
            return llm_decision

        if self.LOW_CONFIDENCE <= deterministic_decision.confidence < self.HIGH_CONFIDENCE:
            return self._expand_medium_confidence_plan(deterministic_decision)

        return deterministic_decision

    def _deterministic_route(self, query: str, slots: Slots) -> RouteDecision:
        scores: dict[ToolId, float] = {tool_id: 0.0 for tool_id in self.registry}
        reasons: dict[ToolId, list[str]] = {tool_id: [] for tool_id in self.registry}

        if slots.mmsi:
            scores["vessel_track_detail"] += 1.2
            reasons["vessel_track_detail"].append("9자리 MMSI 감지")

        if slots.vessel_name:
            scores["vessel_track_detail"] += 0.85
            reasons["vessel_track_detail"].append("선박명 후보 감지")

        for tool_id, metadata in self.registry.items():
            for keyword in metadata.keywords:
                if keyword.lower() in query:
                    scores[tool_id] += 0.22
                    reasons[tool_id].append(f"키워드 '{keyword}'")

        fleet_words = ["전체", "운항중", "운항 중", "모든 선박", "전체 선박", "현황", "요약"]
        risk_words = ["위험", "주의", "위험해", "사고", "이상", "비정상", "혼잡"]
        traffic_words = ["교통", "운항상황", "운항 상황", "해역 상황", "혼잡", "정체"]

        if any(word in query for word in fleet_words):
            for tool_id in [
                "fleet_od_flow",
                "fleet_density_by_area",
                "fleet_speed_by_area",
                "fleet_anomalous_movement",
                "fleet_direction_8way",
            ]:
                scores[tool_id] += 0.12
                reasons[tool_id].append("전체 선박 맥락")

        if any(word in query for word in risk_words):
            for tool_id in [
                "weather_korean_peninsula",
                "fleet_density_by_area",
                "fleet_speed_by_area",
                "fleet_anomalous_movement",
                "fleet_direction_8way",
            ]:
                scores[tool_id] += 0.2
                reasons[tool_id].append("위험/주의 판단 맥락")

        if any(word in query for word in traffic_words):
            for tool_id in [
                "fleet_density_by_area",
                "fleet_speed_by_area",
                "fleet_direction_8way",
                "fleet_od_flow",
            ]:
                scores[tool_id] += 0.16
                reasons[tool_id].append("교통/운항 상황 맥락")

        if "기준" in query or "선정 기준" in query:
            scores["fleet_anomalous_movement"] += 0.3
            reasons["fleet_anomalous_movement"].append("특이기동 선정 기준 요청")

        ranked_tools = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_tool, top_score = ranked_tools[0]

        if top_score <= 0:
            return RouteDecision(
                selected_intent=Intent.UNKNOWN,
                intent_candidates=[],
                required_tools=[],
                confidence=0.0,
                needs_clarification=True,
                reason="질의에서 현재 tool registry와 연결되는 신호를 찾지 못함",
            )

        selected_intent, required_tools, composite_reason = self._select_intent(query, scores)
        confidence = min(0.98, max(0.1, top_score))
        if selected_intent == Intent.MARITIME_RISK_SUMMARY:
            confidence = max(confidence, 0.82)
        elif selected_intent == Intent.TRAFFIC_SUMMARY:
            confidence = max(confidence, 0.78)
        elif selected_intent == Intent.FLEET_OVERVIEW:
            confidence = max(confidence, 0.76)
        elif selected_intent == Intent.MULTI_TOOL_ANALYSIS:
            confidence = max(confidence, 0.78)

        candidates = [
            CandidateIntent(
                intent=TOOL_TO_INTENT[tool_id],
                score=round(min(score, 0.99), 3),
                required_tools=[tool_id],
                reason=", ".join(reasons[tool_id][:4]) or "도구 메타데이터 기반 점수",
            )
            for tool_id, score in ranked_tools
            if score > 0
        ]

        needs_clarification = False
        if selected_intent == Intent.VESSEL_DETAIL and not slots.vessel_name_or_mmsi:
            needs_clarification = True
            confidence = min(confidence, 0.42)

        return RouteDecision(
            selected_intent=selected_intent,
            intent_candidates=candidates,
            required_tools=required_tools,
            confidence=round(confidence, 3),
            needs_clarification=needs_clarification,
            reason=composite_reason or candidates[0].reason,
        )

    def _select_intent(self, query: str, scores: dict[ToolId, float]) -> tuple[Intent, list[ToolId], str]:
        risk_markers = ["위험", "주의", "위험해", "사고", "이상", "비정상"]
        overview_markers = ["전체", "종합", "요약", "상황", "현황", "브리핑"]
        traffic_markers = ["교통", "혼잡", "정체", "운항상황", "운항 상황"]

        if any(marker in query for marker in risk_markers):
            return (
                Intent.MARITIME_RISK_SUMMARY,
                INTENT_TOOLS[Intent.MARITIME_RISK_SUMMARY],
                "위험/주의 판단은 기상, 밀집도, 속도, 특이기동, 이동방향을 함께 확인",
            )

        if any(marker in query for marker in traffic_markers):
            return (
                Intent.TRAFFIC_SUMMARY,
                INTENT_TOOLS[Intent.TRAFFIC_SUMMARY],
                "운항/교통 상황은 밀집도, 속도, 이동방향, OD 흐름을 함께 확인",
            )

        positive_tools = [tool_id for tool_id, score in scores.items() if score >= 0.22]
        explicit_analysis_tools = [tool_id for tool_id in positive_tools if tool_id != "vessel_track_detail"]
        if len(explicit_analysis_tools) >= 2:
            return (
                Intent.MULTI_TOOL_ANALYSIS,
                explicit_analysis_tools,
                "사용자가 여러 분석 지표를 직접 요청했으므로 명시된 도구만 병렬 실행",
            )

        if len([tool for tool in positive_tools if tool != "vessel_track_detail"]) >= 3 and any(
            marker in query for marker in overview_markers
        ):
            return (
                Intent.FLEET_OVERVIEW,
                INTENT_TOOLS[Intent.FLEET_OVERVIEW],
                "전체 선박 현황 요약 요청으로 판단",
            )

        top_tool = max(scores.items(), key=lambda item: item[1])[0]
        return TOOL_TO_INTENT[top_tool], INTENT_TOOLS[TOOL_TO_INTENT[top_tool]], ""

    def _expand_medium_confidence_plan(self, decision: RouteDecision) -> RouteDecision:
        if decision.selected_intent in {
            Intent.TRAFFIC_SUMMARY,
            Intent.MARITIME_RISK_SUMMARY,
            Intent.FLEET_OVERVIEW,
            Intent.VESSEL_DETAIL,
        }:
            return decision

        extra_tools = [
            candidate.required_tools[0]
            for candidate in decision.intent_candidates[:3]
            if candidate.score >= 0.45
        ]
        required_tools = list(dict.fromkeys(decision.required_tools + extra_tools))
        return decision.model_copy(
            update={
                "required_tools": required_tools,
                "reason": f"{decision.reason}; 중간 신뢰도라 read-only 후보 도구를 함께 실행",
            }
        )


class SlotValidator:
    def __init__(self, registry: dict[ToolId, ToolMetadata]) -> None:
        self.registry = registry

    def validate(self, decision: RouteDecision, slots: Slots) -> tuple[bool, str | None]:
        if decision.needs_clarification:
            return False, self._question_for(decision, slots)

        missing = []
        for tool_id in decision.required_tools:
            metadata = self.registry[tool_id]
            for slot in metadata.required_slots:
                if slot == "vessel_name_or_mmsi" and not slots.vessel_name_or_mmsi:
                    missing.append("선박명 또는 MMSI")

        if missing:
            return False, f"{', '.join(sorted(set(missing)))}를 알려주시면 정확히 조회할 수 있습니다."

        return True, None

    @staticmethod
    def _question_for(decision: RouteDecision, slots: Slots) -> str:
        if decision.selected_intent == Intent.VESSEL_DETAIL and not slots.vessel_name_or_mmsi:
            return "특정 선박의 항적을 조회하려면 선박명 또는 9자리 MMSI를 알려주세요."
        return "질의가 조금 모호합니다. 날씨, 특정 선박 항적, OD flow, 밀집도, 속도, 특이기동, 8방위 중 어떤 분석이 필요한가요?"


class PlanBuilder:
    def __init__(self, registry: dict[ToolId, ToolMetadata]) -> None:
        self.registry = registry

    def build(self, decision: RouteDecision, slots: Slots) -> ExecutionPlan:
        calls = []
        for tool_id in decision.required_tools:
            metadata = self.registry[tool_id]
            args = self._args_for_tool(metadata, slots)
            calls.append(ToolCall(tool_id=tool_id, agent=metadata.agent, args=args))

        parallel_tools = [call.tool_id for call in calls if self.registry[call.tool_id].can_parallelize]
        serial_tools = [call.tool_id for call in calls if not self.registry[call.tool_id].can_parallelize]
        parallel_groups = []
        if parallel_tools:
            parallel_groups.append(parallel_tools)
        for tool_id in serial_tools:
            parallel_groups.append([tool_id])

        return ExecutionPlan(
            steps=calls,
            parallel_groups=parallel_groups,
            rationale=(
                f"{decision.selected_intent.value} 의도를 처리하기 위해 "
                f"{len(calls)}개 도구를 {'병렬' if len(calls) > 1 else '단일'} 실행"
            ),
        )

    @staticmethod
    def _args_for_tool(metadata: ToolMetadata, slots: Slots) -> dict[str, Any]:
        args: dict[str, Any] = {"time_scope": slots.time_scope}
        if slots.region:
            args["region"] = slots.region
        if metadata.tool_id == "vessel_track_detail":
            if slots.mmsi:
                args["mmsi"] = slots.mmsi
            if slots.vessel_name:
                args["vessel_name"] = slots.vessel_name
        if slots.metrics:
            args["requested_metrics"] = slots.metrics
        return args


class ToolAdapter(Protocol):
    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a real tool and return JSON-serializable data."""


@dataclass
class CachedValue:
    value: ToolResult
    expires_at: float


class ToolExecutor:
    def __init__(self, registry: dict[ToolId, ToolMetadata], adapters: dict[ToolId, ToolAdapter]) -> None:
        self.registry = registry
        self.adapters = adapters
        self.cache: dict[tuple[ToolId, str], CachedValue] = {}

    def execute_plan(self, plan: ExecutionPlan) -> dict[ToolId, ToolResult]:
        calls_by_id = {call.tool_id: call for call in plan.steps}
        results: dict[ToolId, ToolResult] = {}

        for group in plan.parallel_groups:
            if len(group) == 1:
                tool_id = group[0]
                results[tool_id] = self._execute_call(calls_by_id[tool_id])
                continue

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(group), 8)) as pool:
                future_to_tool = {
                    pool.submit(self._execute_call, calls_by_id[tool_id]): tool_id
                    for tool_id in group
                }
                for future in concurrent.futures.as_completed(future_to_tool):
                    tool_id = future_to_tool[future]
                    results[tool_id] = future.result()

        return results

    def _execute_call(self, call: ToolCall) -> ToolResult:
        metadata = self.registry[call.tool_id]
        cache_key = (call.tool_id, json.dumps(call.args, ensure_ascii=False, sort_keys=True))
        now = time.time()
        cached = self.cache.get(cache_key)
        if cached and cached.expires_at > now:
            return cached.value.model_copy(update={"cached": True})

        adapter = self.adapters[call.tool_id]
        try:
            data = adapter(**call.args)
            result = ToolResult(tool_id=call.tool_id, agent=call.agent, status="ok", data=data)
        except Exception as exc:
            result = ToolResult(tool_id=call.tool_id, agent=call.agent, status="error", error=str(exc))

        self.cache[cache_key] = CachedValue(value=result, expires_at=now + metadata.cache_ttl_seconds)
        return result


class ResultNormalizer:
    UNIT_MAP = {
        "wind_speed": "m/s",
        "gust_speed": "m/s",
        "air_temperature": "°C",
        "water_temperature": "°C",
        "max_wave_height": "m",
        "significant_wave_height": "m",
        "avg_wave_height": "m",
        "humidity": "%",
        "avg_speed": "kn",
        "min_speed": "kn",
        "max_speed": "kn",
    }

    def normalize(self, results: dict[ToolId, ToolResult]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for tool_id, result in results.items():
            payload = result.model_dump()
            payload["units"] = self._units_for(result.data)
            normalized[tool_id] = payload
        return normalized

    def _units_for(self, data: dict[str, Any]) -> dict[str, str]:
        units = {}
        for key in self.UNIT_MAP:
            if key in data or self._key_in_nested(data, key):
                units[key] = self.UNIT_MAP[key]
        return units

    @staticmethod
    def _key_in_nested(value: Any, key: str) -> bool:
        if isinstance(value, dict):
            return key in value or any(ResultNormalizer._key_in_nested(child, key) for child in value.values())
        if isinstance(value, list):
            return any(ResultNormalizer._key_in_nested(child, key) for child in value)
        return False


class VerifierAgent:
    def verify(
        self,
        raw_query: str,
        decision: RouteDecision,
        plan: ExecutionPlan,
        results: dict[ToolId, ToolResult],
        retry_count: int,
    ) -> ValidationReport:
        issues = []

        missing_tools = [call.tool_id for call in plan.steps if call.tool_id not in results]
        if missing_tools:
            issues.append(f"실행 결과가 누락된 도구: {missing_tools}")

        error_tools = [tool_id for tool_id, result in results.items() if result.status == "error"]
        if error_tools:
            issues.append(f"오류가 발생한 도구: {error_tools}")

        if "기준" in raw_query and "fleet_anomalous_movement" in decision.required_tools:
            anomaly = results.get("fleet_anomalous_movement")
            criteria = None if anomaly is None else anomaly.data.get("selection_criteria")
            if not criteria:
                issues.append("특이기동 선정 기준이 결과에 포함되지 않음")

        if decision.selected_intent == Intent.VESSEL_DETAIL:
            detail = results.get("vessel_track_detail")
            if detail and not detail.data.get("track_points"):
                issues.append("특정 선박 항적 포인트가 비어 있음")

        retryable = bool(issues) and retry_count < 1
        return ValidationReport(passed=not issues, issues=issues, retryable=retryable)


class AnswerSynthesizer:
    def __init__(self, registry: dict[ToolId, ToolMetadata]) -> None:
        self.registry = registry

    def synthesize(
        self,
        raw_query: str,
        decision: RouteDecision,
        slots: Slots,
        normalized_results: dict[str, Any],
        validation: ValidationReport,
    ) -> str:
        if not validation.passed:
            return self._failure_answer(decision, validation, normalized_results)

        if decision.selected_intent == Intent.WEATHER:
            return self._weather_answer(normalized_results)
        if decision.selected_intent == Intent.VESSEL_DETAIL:
            return self._vessel_answer(normalized_results)
        if decision.selected_intent == Intent.MARITIME_RISK_SUMMARY:
            return self._risk_answer(normalized_results)
        if decision.selected_intent in {Intent.TRAFFIC_SUMMARY, Intent.FLEET_OVERVIEW}:
            return self._fleet_summary_answer(decision, normalized_results)

        return self._single_or_multi_tool_answer(decision, normalized_results)

    def _weather_answer(self, normalized_results: dict[str, Any]) -> str:
        result = normalized_results.get("weather_korean_peninsula", {})
        data = result.get("data", {})
        if not data:
            return "현재 한반도 평균 날씨 결과를 가져오지 못했습니다."

        return (
            "현재 한반도 평균 기상/해상 상태입니다.\n"
            f"- 풍향: {data.get('wind_direction', 'N/A')}\n"
            f"- 풍속: {data.get('wind_speed', 'N/A')} m/s, 순간풍속: {data.get('gust_speed', 'N/A')} m/s\n"
            f"- 기온: {data.get('air_temperature', 'N/A')} °C, 수온: {data.get('water_temperature', 'N/A')} °C\n"
            f"- 최대파고: {data.get('max_wave_height', 'N/A')} m, 유의파고: {data.get('significant_wave_height', 'N/A')} m, "
            f"평균파고: {data.get('avg_wave_height', 'N/A')} m\n"
            f"- 습도: {data.get('humidity', 'N/A')}%\n"
            f"- 기준 시각: {result.get('timestamp', 'N/A')}"
        )

    def _vessel_answer(self, normalized_results: dict[str, Any]) -> str:
        result = normalized_results.get("vessel_track_detail", {})
        data = result.get("data", {})
        points = data.get("track_points", [])
        latest = points[-1] if points else {}
        return (
            "특정 선박 상세 항적 조회 결과입니다.\n"
            f"- 선박명: {data.get('vessel_name', 'N/A')}\n"
            f"- MMSI: {data.get('mmsi', 'N/A')}\n"
            f"- 항적 포인트 수: {len(points)}\n"
            f"- 최신 위치: lat={latest.get('lat', 'N/A')}, lon={latest.get('lon', 'N/A')}\n"
            f"- 최신 속도/침로: {latest.get('speed', 'N/A')} kn / {latest.get('course', 'N/A')}°\n"
            f"- 기준 시각: {result.get('timestamp', 'N/A')}"
        )

    def _risk_answer(self, normalized_results: dict[str, Any]) -> str:
        risk_signals = []

        density = normalized_results.get("fleet_density_by_area", {}).get("data", {}).get("areas", [])
        high_density = [area for area in density if area.get("density_level") in {"high", "very_high"}]
        if high_density:
            names = ", ".join(area.get("area", "N/A") for area in high_density[:3])
            risk_signals.append(f"밀집도가 높은 구역: {names}")

        speed = normalized_results.get("fleet_speed_by_area", {}).get("data", {}).get("areas", [])
        slow_areas = [area for area in speed if area.get("avg_speed", 99) <= 5]
        if slow_areas:
            names = ", ".join(area.get("area", "N/A") for area in slow_areas[:3])
            risk_signals.append(f"평균 속도가 낮은 구역: {names}")

        anomalies = normalized_results.get("fleet_anomalous_movement", {}).get("data", {}).get("anomalous_vessels", [])
        if anomalies:
            risk_signals.append(f"특이기동 선박 {len(anomalies)}척 감지")

        weather = normalized_results.get("weather_korean_peninsula", {}).get("data", {})
        if weather:
            if weather.get("significant_wave_height", 0) >= 2.5 or weather.get("gust_speed", 0) >= 14:
                risk_signals.append("파고 또는 순간풍속이 주의 수준")

        if not risk_signals:
            risk_text = "현재 도구 결과만 보면 뚜렷한 위험 신호는 크지 않습니다."
        else:
            risk_text = "현재 주의가 필요한 신호가 있습니다: " + "; ".join(risk_signals)

        used = self._used_tools_text(normalized_results)
        return f"{risk_text}\n사용한 분석: {used}"

    def _fleet_summary_answer(self, decision: RouteDecision, normalized_results: dict[str, Any]) -> str:
        lines = ["현재 전체 선박 운항 분석 요약입니다."]

        od = normalized_results.get("fleet_od_flow", {}).get("data", {}).get("top_flows", [])
        if od:
            top = od[0]
            lines.append(f"- 주요 OD flow: {top.get('origin')} -> {top.get('destination')} ({top.get('vessel_count')}척)")

        density = normalized_results.get("fleet_density_by_area", {}).get("data", {}).get("areas", [])
        if density:
            top = sorted(density, key=lambda item: item.get("vessel_count", 0), reverse=True)[0]
            lines.append(f"- 최다 밀집 구역: {top.get('area')} ({top.get('vessel_count')}척, {top.get('density_level')})")

        speed = normalized_results.get("fleet_speed_by_area", {}).get("data", {}).get("areas", [])
        if speed:
            slow = sorted(speed, key=lambda item: item.get("avg_speed", 99))[0]
            lines.append(f"- 평균 속도 최저 구역: {slow.get('area')} ({slow.get('avg_speed')} kn)")

        anomalies = normalized_results.get("fleet_anomalous_movement", {}).get("data", {}).get("anomalous_vessels", [])
        if anomalies:
            lines.append(f"- 특이기동 선박: {len(anomalies)}척")

        directions = normalized_results.get("fleet_direction_8way", {}).get("data", {}).get("directions", [])
        if directions:
            top_direction = sorted(directions, key=lambda item: item.get("count", 0), reverse=True)[0]
            lines.append(f"- 우세 이동방향: {top_direction.get('direction')} ({top_direction.get('ratio')}%)")

        lines.append(f"사용한 분석: {self._used_tools_text(normalized_results)}")
        return "\n".join(lines)

    def _single_or_multi_tool_answer(self, decision: RouteDecision, normalized_results: dict[str, Any]) -> str:
        if decision.selected_intent == Intent.MULTI_TOOL_ANALYSIS:
            lines = ["요청하신 여러 분석 결과입니다."]
        else:
            lines = [f"{decision.selected_intent.value} 분석 결과입니다."]
        for tool_id, payload in normalized_results.items():
            metadata = self.registry[tool_id]  # type: ignore[index]
            data = payload.get("data", {})
            lines.append(f"- {metadata.name}: {self._compact_data_summary(data)}")
        lines.append(f"사용한 분석: {self._used_tools_text(normalized_results)}")
        return "\n".join(lines)

    def _failure_answer(
        self,
        decision: RouteDecision,
        validation: ValidationReport,
        normalized_results: dict[str, Any],
    ) -> str:
        return (
            "분석을 완료했지만 검증 단계에서 문제가 발견되었습니다.\n"
            f"- 의도: {decision.selected_intent.value}\n"
            f"- 문제: {'; '.join(validation.issues)}\n"
            f"- 일부 결과: {self._used_tools_text(normalized_results) if normalized_results else '없음'}"
        )

    def _used_tools_text(self, normalized_results: dict[str, Any]) -> str:
        names = []
        for tool_id in normalized_results:
            metadata = self.registry.get(tool_id)  # type: ignore[arg-type]
            names.append(metadata.name if metadata else tool_id)
        return ", ".join(names)

    @staticmethod
    def _compact_data_summary(data: dict[str, Any]) -> str:
        if "areas" in data:
            return f"{len(data['areas'])}개 구역"
        if "top_flows" in data:
            return f"{len(data['top_flows'])}개 OD flow"
        if "anomalous_vessels" in data:
            return f"{len(data['anomalous_vessels'])}척"
        if "directions" in data:
            return f"{len(data['directions'])}개 방향"
        return json.dumps(data, ensure_ascii=False)[:200]


class MaritimeAgentRuntime:
    def __init__(self, adapters: dict[ToolId, ToolAdapter], llm_router: LLMRouter | None = None) -> None:
        self.registry = build_tool_registry()
        self.normalizer = QueryNormalizer()
        self.router = HybridRouter(self.registry, llm_router)
        self.slot_validator = SlotValidator(self.registry)
        self.plan_builder = PlanBuilder(self.registry)
        self.executor = ToolExecutor(self.registry, adapters)
        self.result_normalizer = ResultNormalizer()
        self.verifier = VerifierAgent()
        self.synthesizer = AnswerSynthesizer(self.registry)

    def query_normalizer_node(self, state: GraphState) -> GraphState:
        raw_query = state["raw_query"]
        normalized_query, slots = self.normalizer.normalize(raw_query)
        return {
            "normalized_query": normalized_query,
            "slots": slots.model_dump(),
            "trace": self._merge_trace(state, {"normalized_at": utc_now_iso()}),
        }

    def router_node(self, state: GraphState) -> GraphState:
        slots = Slots(**state["slots"])
        decision = self.router.route(state["normalized_query"], slots)
        return {
            "route_decision": decision.model_dump(),
            "selected_intent": decision.selected_intent.value,
            "trace": self._merge_trace(
                state,
                {
                    "selected_tools": decision.required_tools,
                    "confidence": decision.confidence,
                    "router_reason": decision.reason,
                },
            ),
        }

    def slot_validator_node(self, state: GraphState) -> GraphState:
        slots = Slots(**state["slots"])
        decision = RouteDecision(**state["route_decision"])
        ok, question = self.slot_validator.validate(decision, slots)
        update: GraphState = {
            "trace": self._merge_trace(state, {"slot_validation_passed": ok}),
        }
        if not ok and question:
            update["clarification_question"] = question
        return update

    def clarification_node(self, state: GraphState) -> GraphState:
        question = state.get("clarification_question") or "추가 정보가 필요합니다."
        return {"answer": question}

    def plan_builder_node(self, state: GraphState) -> GraphState:
        slots = Slots(**state["slots"])
        decision = RouteDecision(**state["route_decision"])
        plan = self.plan_builder.build(decision, slots)
        return {
            "plan": plan.model_dump(),
            "trace": self._merge_trace(state, {"plan_rationale": plan.rationale}),
        }

    def tool_executor_node(self, state: GraphState) -> GraphState:
        plan = ExecutionPlan(**state["plan"])
        results = self.executor.execute_plan(plan)
        return {
            "tool_results": {tool_id: result.model_dump() for tool_id, result in results.items()},
            "trace": self._merge_trace(state, {"executed_at": utc_now_iso()}),
        }

    def result_normalizer_node(self, state: GraphState) -> GraphState:
        results = {
            tool_id: ToolResult(**result)
            for tool_id, result in state.get("tool_results", {}).items()
        }
        normalized = self.result_normalizer.normalize(results)
        return {"normalized_results": normalized}

    def verifier_node(self, state: GraphState) -> GraphState:
        retry_count = int(state.get("retry_count", 0))
        decision = RouteDecision(**state["route_decision"])
        plan = ExecutionPlan(**state["plan"])
        results = {
            tool_id: ToolResult(**result)
            for tool_id, result in state.get("tool_results", {}).items()
        }
        report = self.verifier.verify(state["raw_query"], decision, plan, results, retry_count)
        return {
            "validation": report.model_dump(),
            "retry_count": retry_count + 1 if report.retryable else retry_count,
            "trace": self._merge_trace(state, {"validation_passed": report.passed, "validation_issues": report.issues}),
        }

    def answer_synthesizer_node(self, state: GraphState) -> GraphState:
        decision = RouteDecision(**state["route_decision"])
        slots = Slots(**state["slots"])
        validation = ValidationReport(**state["validation"])
        answer = self.synthesizer.synthesize(
            raw_query=state["raw_query"],
            decision=decision,
            slots=slots,
            normalized_results=state.get("normalized_results", {}),
            validation=validation,
        )
        return {"answer": answer}

    @staticmethod
    def _merge_trace(state: GraphState, values: dict[str, Any]) -> dict[str, Any]:
        trace = dict(state.get("trace", {}))
        trace.update(values)
        return trace


def route_after_slot_validation(state: GraphState) -> Literal["clarify", "plan"]:
    return "clarify" if state.get("clarification_question") else "plan"


def route_after_verification(state: GraphState) -> Literal["retry", "answer"]:
    validation = ValidationReport(**state["validation"])
    return "retry" if validation.retryable else "answer"


class FallbackGraph:
    """Small runner that mimics compiled LangGraph.invoke for local demos without langgraph installed."""

    def __init__(self, runtime: MaritimeAgentRuntime) -> None:
        self.runtime = runtime

    def invoke(self, initial_state: GraphState) -> GraphState:
        state = dict(initial_state)
        for node in [
            self.runtime.query_normalizer_node,
            self.runtime.router_node,
            self.runtime.slot_validator_node,
        ]:
            state.update(node(state))

        if route_after_slot_validation(state) == "clarify":
            state.update(self.runtime.clarification_node(state))
            return state

        while True:
            for node in [
                self.runtime.plan_builder_node,
                self.runtime.tool_executor_node,
                self.runtime.result_normalizer_node,
                self.runtime.verifier_node,
            ]:
                state.update(node(state))
            if route_after_verification(state) != "retry":
                break

        state.update(self.runtime.answer_synthesizer_node(state))
        return state


def build_maritime_graph(runtime: MaritimeAgentRuntime) -> Any:
    if not LANGGRAPH_AVAILABLE:
        return FallbackGraph(runtime)

    graph = StateGraph(GraphState)
    graph.add_node("query_normalizer", runtime.query_normalizer_node)
    graph.add_node("router", runtime.router_node)
    graph.add_node("slot_validator", runtime.slot_validator_node)
    graph.add_node("clarification", runtime.clarification_node)
    graph.add_node("plan_builder", runtime.plan_builder_node)
    graph.add_node("tool_executor", runtime.tool_executor_node)
    graph.add_node("result_normalizer", runtime.result_normalizer_node)
    graph.add_node("verifier", runtime.verifier_node)
    graph.add_node("answer_synthesizer", runtime.answer_synthesizer_node)

    graph.add_edge(START, "query_normalizer")
    graph.add_edge("query_normalizer", "router")
    graph.add_edge("router", "slot_validator")
    graph.add_conditional_edges(
        "slot_validator",
        route_after_slot_validation,
        {"clarify": "clarification", "plan": "plan_builder"},
    )
    graph.add_edge("clarification", END)
    graph.add_edge("plan_builder", "tool_executor")
    graph.add_edge("tool_executor", "result_normalizer")
    graph.add_edge("result_normalizer", "verifier")
    graph.add_conditional_edges(
        "verifier",
        route_after_verification,
        {"retry": "plan_builder", "answer": "answer_synthesizer"},
    )
    graph.add_edge("answer_synthesizer", END)

    return graph.compile()


def demo_weather_tool(**kwargs: Any) -> dict[str, Any]:
    return {
        "scope": "korean_peninsula",
        "wind_direction": "NW",
        "wind_speed": 7.2,
        "gust_speed": 12.6,
        "air_temperature": 18.4,
        "water_temperature": 15.9,
        "max_wave_height": 2.1,
        "significant_wave_height": 1.4,
        "avg_wave_height": 0.9,
        "humidity": 72,
        "tool_args": kwargs,
    }


def demo_vessel_track_tool(**kwargs: Any) -> dict[str, Any]:
    vessel_name = kwargs.get("vessel_name") or "DEMO VESSEL"
    mmsi = kwargs.get("mmsi") or "440123456"
    return {
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "track_points": [
            {"ts": "2026-05-22T00:00:00Z", "lat": 35.08, "lon": 129.04, "speed": 10.2, "course": 68},
            {"ts": "2026-05-22T00:05:00Z", "lat": 35.10, "lon": 129.12, "speed": 11.1, "course": 72},
            {"ts": "2026-05-22T00:10:00Z", "lat": 35.13, "lon": 129.20, "speed": 10.8, "course": 75},
        ],
        "tool_args": kwargs,
    }


def demo_od_flow_tool(**kwargs: Any) -> dict[str, Any]:
    return {
        "top_flows": [
            {"origin": "Busan", "destination": "Tsushima Strait", "vessel_count": 47},
            {"origin": "Incheon", "destination": "Yellow Sea", "vessel_count": 32},
            {"origin": "Yeosu", "destination": "Jeju", "vessel_count": 21},
        ],
        "tool_args": kwargs,
    }


def demo_density_tool(**kwargs: Any) -> dict[str, Any]:
    return {
        "areas": [
            {"area": "Busan Approach", "vessel_count": 82, "density_level": "very_high"},
            {"area": "Incheon Anchorage", "vessel_count": 54, "density_level": "high"},
            {"area": "East Sea Offshore", "vessel_count": 18, "density_level": "medium"},
        ],
        "tool_args": kwargs,
    }


def demo_speed_tool(**kwargs: Any) -> dict[str, Any]:
    return {
        "areas": [
            {"area": "Busan Approach", "avg_speed": 4.6, "min_speed": 0.8, "max_speed": 13.2},
            {"area": "Incheon Anchorage", "avg_speed": 3.1, "min_speed": 0.0, "max_speed": 9.7},
            {"area": "East Sea Offshore", "avg_speed": 12.4, "min_speed": 7.3, "max_speed": 18.5},
        ],
        "tool_args": kwargs,
    }


def demo_anomaly_tool(**kwargs: Any) -> dict[str, Any]:
    return {
        "selection_criteria": {
            "rapid_course_change": "5분 이내 침로 변화 45도 이상",
            "rapid_speed_change": "5분 이내 속도 변화 7kn 이상",
            "loitering": "좁은 반경 내 20분 이상 반복 이동",
        },
        "anomalous_vessels": [
            {
                "vessel_name": "DEMO-ALPHA",
                "mmsi": "440111111",
                "area": "Busan Approach",
                "anomaly_type": "rapid_course_change",
                "score": 0.91,
            },
            {
                "vessel_name": "DEMO-BRAVO",
                "mmsi": "440222222",
                "area": "Incheon Anchorage",
                "anomaly_type": "loitering",
                "score": 0.83,
            },
        ],
        "tool_args": kwargs,
    }


def demo_direction_tool(**kwargs: Any) -> dict[str, Any]:
    return {
        "directions": [
            {"direction": "NE", "count": 64, "ratio": 28.1},
            {"direction": "E", "count": 48, "ratio": 21.1},
            {"direction": "SW", "count": 39, "ratio": 17.1},
            {"direction": "N", "count": 24, "ratio": 10.5},
        ],
        "tool_args": kwargs,
    }


def build_demo_adapters() -> dict[ToolId, ToolAdapter]:
    return {
        "weather_korean_peninsula": demo_weather_tool,
        "vessel_track_detail": demo_vessel_track_tool,
        "fleet_od_flow": demo_od_flow_tool,
        "fleet_density_by_area": demo_density_tool,
        "fleet_speed_by_area": demo_speed_tool,
        "fleet_anomalous_movement": demo_anomaly_tool,
        "fleet_direction_8way": demo_direction_tool,
    }


def create_demo_app() -> Any:
    runtime = MaritimeAgentRuntime(adapters=build_demo_adapters())
    return build_maritime_graph(runtime)


def run_query(query: str, include_trace: bool = False) -> dict[str, Any]:
    app = create_demo_app()
    state = app.invoke({"raw_query": query, "retry_count": 0})
    output = {
        "answer": state.get("answer"),
        "selected_intent": state.get("selected_intent"),
        "selected_tools": state.get("trace", {}).get("selected_tools", []),
        "confidence": state.get("trace", {}).get("confidence"),
    }
    if include_trace:
        output["state"] = state
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Maritime LangGraph agent architecture demo")
    parser.add_argument(
        "query",
        nargs="*",
        default=["지금 위험해 보이는 해역 있어?"],
        help="User query to run through the maritime agent graph",
    )
    parser.add_argument("--trace", action="store_true", help="Include full graph state in the output")
    args = parser.parse_args()

    query = " ".join(args.query)
    output = run_query(query, include_trace=args.trace)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
