from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Literal, Mapping, Protocol, TypedDict, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, field_validator


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


class Slots(BaseModel):
    vessel_name: str | None = None
    mmsi: str | None = None
    region: str | None = None
    metrics: list[str] = Field(default_factory=list)
    time_scope: str = "current"

    @property
    def vessel_name_or_mmsi(self) -> str | None:
        return self.mmsi or self.vessel_name


class CandidateIntent(BaseModel):
    intent: Intent
    score: float = Field(ge=0.0, le=1.0)
    required_tools: list[ToolId]
    reason: str


class RouteDecision(BaseModel):
    selected_intent: Intent
    intent_candidates: list[CandidateIntent] = Field(default_factory=list)
    required_tools: list[ToolId] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool
    clarification_question: str | None = None
    reason: str

    @field_validator("required_tools")
    @classmethod
    def dedupe_tools(cls, value: list[ToolId]) -> list[ToolId]:
        return list(dict.fromkeys(value))


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


class VerificationDecision(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    retryable: bool = False
    reason: str


class FinalAnswer(BaseModel):
    answer: str


class GraphState(TypedDict, total=False):
    raw_query: str
    normalized_query: str
    slots: dict[str, Any]
    deterministic_hints: dict[str, Any]
    route_decision: dict[str, Any]
    selected_intent: str
    plan: dict[str, Any]
    tool_results: dict[str, Any]
    normalized_results: dict[str, Any]
    verification: dict[str, Any]
    answer: str
    retry_count: int
    trace: dict[str, Any]


class ToolAdapter(Protocol):
    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a real production tool and return JSON-serializable data."""


@dataclass
class CachedValue:
    value: ToolResult
    expires_at: float


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_tool_registry() -> dict[ToolId, ToolMetadata]:
    tools = [
        ToolMetadata(
            tool_id="weather_korean_peninsula",
            source_number=1,
            agent=AgentName.WEATHER,
            name="현재 한반도 평균 날씨",
            description=(
                "현재 한반도의 평균 풍향, 풍속, 기온, 수온, 최대파고, 유의파고, "
                "평균파고, 순간풍속, 습도 결과 값을 반환한다."
            ),
            output_type="weather_and_sea_state",
            cache_ttl_seconds=300,
            keywords=["날씨", "기상", "풍향", "풍속", "기온", "수온", "파고", "습도", "해상상태"],
            metrics=[
                "wind_direction",
                "wind_speed",
                "air_temperature",
                "water_temperature",
                "max_wave_height",
                "significant_wave_height",
                "avg_wave_height",
                "gust_speed",
                "humidity",
            ],
        ),
        ToolMetadata(
            tool_id="vessel_track_detail",
            source_number=2,
            agent=AgentName.VESSEL_DETAIL,
            name="특정 선박 상세 항적",
            description="선박의 이름 또는 MMSI를 명시했을 때 특정 선박에 대한 자세한 항적 정보를 반환한다.",
            required_slots=["vessel_name_or_mmsi"],
            optional_slots=["time_scope"],
            output_type="vessel_track",
            cache_ttl_seconds=30,
            keywords=["항적", "선박명", "선명", "mmsi", "선박", "위치", "경로", "추적"],
            metrics=["position", "course", "speed", "track"],
        ),
        ToolMetadata(
            tool_id="fleet_od_flow",
            source_number=3,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 OD flow 분석",
            description="현재 운항중인 전체 선박의 OD flow 분석 결과를 반환한다.",
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
            description="현재 운항중인 전체 선박의 구역별 밀집 현황 분석 결과를 반환한다.",
            output_type="fleet_density_by_area",
            cache_ttl_seconds=60,
            keywords=["밀집", "밀도", "혼잡", "구역별", "분포", "붐비", "선박수", "집중"],
            metrics=["area", "vessel_count", "density_level"],
        ),
        ToolMetadata(
            tool_id="fleet_speed_by_area",
            source_number=5,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 구역별 이동속도 요약",
            description="현재 운항중인 전체 선박의 구역별 이동속도 요약 결과를 반환한다.",
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
            description="현재 운항중인 전체 선박 중 특이 기동 선박의 기동결과 및 특이기동 선박 선정 기준 결과를 반환한다.",
            output_type="fleet_anomalous_movement",
            cache_ttl_seconds=60,
            keywords=["특이기동", "이상기동", "이상운항", "급선회", "급가속", "급감속", "비정상", "선정기준", "기준"],
            metrics=["vessel", "anomaly_type", "criteria"],
        ),
        ToolMetadata(
            tool_id="fleet_direction_8way",
            source_number=7,
            agent=AgentName.FLEET_ANALYTICS,
            name="전체 선박 8방위 이동방향 분석",
            description="현재 운항중인 전체 선박이 8방위 중 어디로 이동중인지 분석 결과를 반환한다.",
            output_type="fleet_direction_8way",
            cache_ttl_seconds=60,
            keywords=["방향", "이동방향", "8방위", "팔방위", "북쪽", "남쪽", "동쪽", "서쪽", "북동", "북서", "남동", "남서", "침로"],
            metrics=["direction", "count", "ratio"],
        ),
    ]
    return {tool.tool_id: tool for tool in tools}


REQUIRED_TOOLS_BY_INTENT: dict[Intent, list[ToolId]] = {
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

    def normalize(self, raw_query: str, registry: Mapping[ToolId, ToolMetadata]) -> tuple[str, Slots, dict[str, Any]]:
        normalized = " ".join(raw_query.strip().lower().split())
        slots = Slots()

        mmsi_match = self.MMSI_PATTERN.search(raw_query)
        if mmsi_match:
            slots.mmsi = mmsi_match.group(0)

        if slots.mmsi is None:
            for pattern in self.VESSEL_PATTERNS:
                match = pattern.search(raw_query)
                if not match:
                    continue
                candidate = match.group(1).strip(" .,:;")
                if not self._looks_like_metric_phrase(candidate):
                    slots.vessel_name = candidate
                    break

        for region in self.REGIONS:
            if region in raw_query:
                slots.region = region
                break

        slots.metrics = sorted(
            {
                canonical
                for source, canonical in self.METRIC_SYNONYMS.items()
                if source in normalized or source in raw_query
            }
        )

        if any(token in raw_query for token in ["현재", "지금", "운항중", "운항 중"]):
            slots.time_scope = "current"

        deterministic_hints = self._build_hints(normalized, slots, registry)
        return normalized, slots, deterministic_hints

    def _build_hints(
        self,
        normalized_query: str,
        slots: Slots,
        registry: Mapping[ToolId, ToolMetadata],
    ) -> dict[str, Any]:
        keyword_hits: dict[ToolId, list[str]] = {}
        for tool_id, metadata in registry.items():
            hits = [keyword for keyword in metadata.keywords if keyword.lower() in normalized_query]
            if hits:
                keyword_hits[tool_id] = hits

        must_use_tools: list[ToolId] = []
        if slots.mmsi or slots.vessel_name:
            must_use_tools.append("vessel_track_detail")

        if any(word in normalized_query for word in ["위험", "주의", "사고", "비정상"]):
            must_use_tools.extend(REQUIRED_TOOLS_BY_INTENT[Intent.MARITIME_RISK_SUMMARY])

        return {
            "keyword_hits": keyword_hits,
            "must_use_tools": list(dict.fromkeys(must_use_tools)),
            "possible_metrics": slots.metrics,
            "routing_policy": {
                "vessel_track_detail_requires": "vessel_name or mmsi",
                "risk_summary_tools": REQUIRED_TOOLS_BY_INTENT[Intent.MARITIME_RISK_SUMMARY],
                "traffic_summary_tools": REQUIRED_TOOLS_BY_INTENT[Intent.TRAFFIC_SUMMARY],
                "fleet_overview_tools": REQUIRED_TOOLS_BY_INTENT[Intent.FLEET_OVERVIEW],
            },
        }

    @staticmethod
    def _looks_like_metric_phrase(value: str) -> bool:
        blocked = ["전체", "현재", "운항", "날씨", "밀집", "속도", "방향", "특이", "위험"]
        return any(token in value for token in blocked)


class ChatOpenAIRouter:
    def __init__(self, llm: ChatOpenAI, registry: Mapping[ToolId, ToolMetadata]) -> None:
        self.llm = llm.with_structured_output(RouteDecision)
        self.registry = registry

    def route(self, raw_query: str, normalized_query: str, slots: Slots, deterministic_hints: dict[str, Any]) -> RouteDecision:
        messages = [
            SystemMessage(content=self._system_prompt()),
            HumanMessage(
                content=json.dumps(
                    {
                        "raw_query": raw_query,
                        "normalized_query": normalized_query,
                        "slots": slots.model_dump(),
                        "deterministic_hints": deterministic_hints,
                        "tool_registry": self._compact_registry(),
                        "allowed_intents": [intent.value for intent in Intent],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            ),
        ]
        decision = cast(RouteDecision, self.llm.invoke(messages))
        return self._repair_route_decision(decision, slots)

    def _system_prompt(self) -> str:
        return (
            "You are the routing brain for a maritime analytics LangGraph system.\n"
            "Return only the structured schema requested by the caller.\n"
            "Routing rules:\n"
            "1. Select the smallest sufficient set of tools.\n"
            "2. For vessel_track_detail, require vessel_name or mmsi. If missing, set needs_clarification=true.\n"
            "3. Risk or caution questions should combine weather, density, speed, anomalous movement, and 8-way direction.\n"
            "4. Traffic or operational situation questions should combine density, speed, direction, and OD flow.\n"
            "5. If the user explicitly asks multiple metrics, use multi_tool_analysis with those exact tools.\n"
            "6. Do not invent tools outside the registry.\n"
            "7. The answer language should match the user's Korean maritime domain context."
        )

    def _compact_registry(self) -> list[dict[str, Any]]:
        return [
            {
                "tool_id": metadata.tool_id,
                "source_number": metadata.source_number,
                "agent": metadata.agent.value,
                "description": metadata.description,
                "required_slots": metadata.required_slots,
                "keywords": metadata.keywords,
                "metrics": metadata.metrics,
            }
            for metadata in self.registry.values()
        ]

    def _repair_route_decision(self, decision: RouteDecision, slots: Slots) -> RouteDecision:
        required_tools = list(dict.fromkeys(decision.required_tools))
        if decision.selected_intent != Intent.MULTI_TOOL_ANALYSIS:
            canonical_tools = REQUIRED_TOOLS_BY_INTENT[decision.selected_intent]
            if canonical_tools:
                required_tools = canonical_tools

        if decision.selected_intent == Intent.VESSEL_DETAIL and not slots.vessel_name_or_mmsi:
            return decision.model_copy(
                update={
                    "required_tools": ["vessel_track_detail"],
                    "needs_clarification": True,
                    "clarification_question": "특정 선박의 항적을 조회하려면 선박명 또는 9자리 MMSI를 알려주세요.",
                    "confidence": min(decision.confidence, 0.5),
                }
            )

        return decision.model_copy(update={"required_tools": required_tools})


class SlotValidator:
    def __init__(self, registry: Mapping[ToolId, ToolMetadata]) -> None:
        self.registry = registry

    def validate(self, decision: RouteDecision, slots: Slots) -> RouteDecision:
        if decision.needs_clarification:
            return decision

        missing: list[str] = []
        for tool_id in decision.required_tools:
            metadata = self.registry[tool_id]
            for slot in metadata.required_slots:
                if slot == "vessel_name_or_mmsi" and not slots.vessel_name_or_mmsi:
                    missing.append("선박명 또는 MMSI")

        if not missing:
            return decision

        return decision.model_copy(
            update={
                "needs_clarification": True,
                "clarification_question": f"{', '.join(sorted(set(missing)))}를 알려주시면 정확히 조회할 수 있습니다.",
                "confidence": min(decision.confidence, 0.5),
            }
        )


class PlanBuilder:
    def __init__(self, registry: Mapping[ToolId, ToolMetadata]) -> None:
        self.registry = registry

    def build(self, decision: RouteDecision, slots: Slots) -> ExecutionPlan:
        calls = [
            ToolCall(
                tool_id=tool_id,
                agent=self.registry[tool_id].agent,
                args=self._args_for_tool(tool_id, slots),
            )
            for tool_id in decision.required_tools
        ]

        parallel_tools = [call.tool_id for call in calls if self.registry[call.tool_id].can_parallelize]
        serial_tools = [call.tool_id for call in calls if not self.registry[call.tool_id].can_parallelize]
        parallel_groups = [parallel_tools] if parallel_tools else []
        parallel_groups.extend([[tool_id] for tool_id in serial_tools])

        return ExecutionPlan(
            steps=calls,
            parallel_groups=parallel_groups,
            rationale=(
                f"{decision.selected_intent.value} intent, "
                f"{len(calls)} tool call(s), "
                f"{'parallel execution' if len(calls) > 1 else 'single execution'}"
            ),
        )

    def _args_for_tool(self, tool_id: ToolId, slots: Slots) -> dict[str, Any]:
        args: dict[str, Any] = {"time_scope": slots.time_scope}
        if slots.region:
            args["region"] = slots.region
        if slots.metrics:
            args["requested_metrics"] = slots.metrics
        if tool_id == "vessel_track_detail":
            if slots.mmsi:
                args["mmsi"] = slots.mmsi
            if slots.vessel_name:
                args["vessel_name"] = slots.vessel_name
        return args


class ToolExecutor:
    def __init__(self, registry: Mapping[ToolId, ToolMetadata], adapters: Mapping[ToolId, ToolAdapter]) -> None:
        missing = sorted(set(registry) - set(adapters))
        if missing:
            raise ValueError(f"Missing tool adapters: {missing}")
        self.registry = registry
        self.adapters = adapters
        self.cache: dict[tuple[ToolId, str], CachedValue] = {}

    def execute(self, plan: ExecutionPlan) -> dict[ToolId, ToolResult]:
        calls_by_id = {call.tool_id: call for call in plan.steps}
        results: dict[ToolId, ToolResult] = {}

        for group in plan.parallel_groups:
            if len(group) == 1:
                tool_id = group[0]
                results[tool_id] = self._execute_one(calls_by_id[tool_id])
                continue

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(group))) as pool:
                futures = {pool.submit(self._execute_one, calls_by_id[tool_id]): tool_id for tool_id in group}
                for future in concurrent.futures.as_completed(futures):
                    tool_id = futures[future]
                    results[tool_id] = future.result()

        return results

    def _execute_one(self, call: ToolCall) -> ToolResult:
        metadata = self.registry[call.tool_id]
        cache_key = (call.tool_id, json.dumps(call.args, ensure_ascii=False, sort_keys=True))
        now = time.time()
        cached = self.cache.get(cache_key)
        if cached and cached.expires_at > now:
            return cached.value.model_copy(update={"cached": True})

        try:
            data = self.adapters[call.tool_id](**call.args)
            if not isinstance(data, dict):
                raise TypeError(f"{call.tool_id} returned {type(data).__name__}, expected dict")
            result = ToolResult(tool_id=call.tool_id, agent=metadata.agent, status="ok", data=data)
        except Exception as exc:
            result = ToolResult(tool_id=call.tool_id, agent=metadata.agent, status="error", error=str(exc))

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

    def normalize(self, results: Mapping[ToolId, ToolResult]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for tool_id, result in results.items():
            payload = result.model_dump()
            payload["units"] = self._units_for(result.data)
            normalized[tool_id] = payload
        return normalized

    def _units_for(self, data: dict[str, Any]) -> dict[str, str]:
        units = {}
        for key, unit in self.UNIT_MAP.items():
            if self._contains_key(data, key):
                units[key] = unit
        return units

    def _contains_key(self, value: Any, key: str) -> bool:
        if isinstance(value, dict):
            return key in value or any(self._contains_key(child, key) for child in value.values())
        if isinstance(value, list):
            return any(self._contains_key(child, key) for child in value)
        return False


class ChatOpenAIVerifier:
    def __init__(self, llm: ChatOpenAI, registry: Mapping[ToolId, ToolMetadata]) -> None:
        self.llm = llm.with_structured_output(VerificationDecision)
        self.registry = registry

    def verify(
        self,
        raw_query: str,
        decision: RouteDecision,
        plan: ExecutionPlan,
        normalized_results: dict[str, Any],
        retry_count: int,
    ) -> VerificationDecision:
        deterministic_issues = self._deterministic_issues(raw_query, decision, plan, normalized_results)
        if deterministic_issues:
            return VerificationDecision(
                passed=False,
                issues=deterministic_issues,
                retryable=retry_count < 1,
                reason="Deterministic validation failed before LLM verification.",
            )

        messages = [
            SystemMessage(
                content=(
                    "You verify whether maritime tool results are sufficient for the user's query.\n"
                    "Do not judge domain risk beyond the provided tool data.\n"
                    "Return structured verification only.\n"
                    "Set retryable=true only when rerunning the same planned tools could fix missing or malformed results."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "raw_query": raw_query,
                        "route_decision": decision.model_dump(),
                        "plan": plan.model_dump(),
                        "normalized_results": normalized_results,
                        "retry_count": retry_count,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            ),
        ]
        verified = cast(VerificationDecision, self.llm.invoke(messages))
        if retry_count >= 1 and verified.retryable:
            return verified.model_copy(update={"retryable": False})
        return verified

    def _deterministic_issues(
        self,
        raw_query: str,
        decision: RouteDecision,
        plan: ExecutionPlan,
        normalized_results: dict[str, Any],
    ) -> list[str]:
        issues: list[str] = []
        planned_tools = [call.tool_id for call in plan.steps]
        missing_results = [tool_id for tool_id in planned_tools if tool_id not in normalized_results]
        if missing_results:
            issues.append(f"Missing tool results: {missing_results}")

        error_tools = [
            tool_id
            for tool_id, payload in normalized_results.items()
            if payload.get("status") == "error"
        ]
        if error_tools:
            issues.append(f"Tool execution errors: {error_tools}")

        if "기준" in raw_query and "fleet_anomalous_movement" in decision.required_tools:
            anomaly_result = normalized_results.get("fleet_anomalous_movement", {})
            if not anomaly_result.get("data", {}).get("selection_criteria"):
                issues.append("fleet_anomalous_movement result lacks selection_criteria")

        return issues


class ChatOpenAIAnswerSynthesizer:
    def __init__(self, llm: ChatOpenAI, registry: Mapping[ToolId, ToolMetadata]) -> None:
        self.llm = llm.with_structured_output(FinalAnswer)
        self.registry = registry

    def synthesize(
        self,
        raw_query: str,
        decision: RouteDecision,
        slots: Slots,
        normalized_results: dict[str, Any],
        verification: VerificationDecision,
    ) -> str:
        messages = [
            SystemMessage(
                content=(
                    "You are a Korean maritime operations assistant.\n"
                    "Answer in Korean.\n"
                    "Use only provided tool results. Do not fabricate values.\n"
                    "For uncertainty, say what is and is not supported by the results.\n"
                    "Include the basis briefly: which analyses/tools were used.\n"
                    "Keep the response concise but operationally useful."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "raw_query": raw_query,
                        "route_decision": decision.model_dump(),
                        "slots": slots.model_dump(),
                        "verification": verification.model_dump(),
                        "normalized_results": normalized_results,
                        "tool_names": {
                            tool_id: metadata.name
                            for tool_id, metadata in self.registry.items()
                            if tool_id in normalized_results
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            ),
        ]
        final_answer = cast(FinalAnswer, self.llm.invoke(messages))
        return final_answer.answer


class MaritimeLangGraphRuntime:
    def __init__(
        self,
        llm: ChatOpenAI,
        tool_adapters: Mapping[ToolId, ToolAdapter],
        registry: Mapping[ToolId, ToolMetadata] | None = None,
    ) -> None:
        self.registry = registry or build_tool_registry()
        self.normalizer = QueryNormalizer()
        self.router = ChatOpenAIRouter(llm, self.registry)
        self.slot_validator = SlotValidator(self.registry)
        self.plan_builder = PlanBuilder(self.registry)
        self.executor = ToolExecutor(self.registry, tool_adapters)
        self.result_normalizer = ResultNormalizer()
        self.verifier = ChatOpenAIVerifier(llm, self.registry)
        self.answer_synthesizer = ChatOpenAIAnswerSynthesizer(llm, self.registry)

    def query_normalizer_node(self, state: GraphState) -> GraphState:
        normalized_query, slots, hints = self.normalizer.normalize(state["raw_query"], self.registry)
        return {
            "normalized_query": normalized_query,
            "slots": slots.model_dump(),
            "deterministic_hints": hints,
            "trace": merge_trace(state, {"normalized_at": utc_now_iso()}),
        }

    def router_node(self, state: GraphState) -> GraphState:
        slots = Slots(**state["slots"])
        decision = self.router.route(
            raw_query=state["raw_query"],
            normalized_query=state["normalized_query"],
            slots=slots,
            deterministic_hints=state["deterministic_hints"],
        )
        decision = self.slot_validator.validate(decision, slots)
        return {
            "route_decision": decision.model_dump(),
            "selected_intent": decision.selected_intent.value,
            "trace": merge_trace(
                state,
                {
                    "routed_at": utc_now_iso(),
                    "selected_tools": decision.required_tools,
                    "confidence": decision.confidence,
                    "router_reason": decision.reason,
                },
            ),
        }

    def clarification_node(self, state: GraphState) -> GraphState:
        decision = RouteDecision(**state["route_decision"])
        question = decision.clarification_question or "추가 정보가 필요합니다. 어떤 분석이 필요한지 조금 더 구체적으로 알려주세요."
        return {"answer": question}

    def plan_builder_node(self, state: GraphState) -> GraphState:
        decision = RouteDecision(**state["route_decision"])
        slots = Slots(**state["slots"])
        plan = self.plan_builder.build(decision, slots)
        return {
            "plan": plan.model_dump(),
            "trace": merge_trace(state, {"planned_at": utc_now_iso(), "plan_rationale": plan.rationale}),
        }

    def tool_executor_node(self, state: GraphState) -> GraphState:
        plan = ExecutionPlan(**state["plan"])
        results = self.executor.execute(plan)
        return {
            "tool_results": {tool_id: result.model_dump() for tool_id, result in results.items()},
            "trace": merge_trace(state, {"executed_at": utc_now_iso()}),
        }

    def result_normalizer_node(self, state: GraphState) -> GraphState:
        results = {
            cast(ToolId, tool_id): ToolResult(**payload)
            for tool_id, payload in state.get("tool_results", {}).items()
        }
        return {"normalized_results": self.result_normalizer.normalize(results)}

    def verifier_node(self, state: GraphState) -> GraphState:
        retry_count = int(state.get("retry_count", 0))
        decision = RouteDecision(**state["route_decision"])
        plan = ExecutionPlan(**state["plan"])
        verification = self.verifier.verify(
            raw_query=state["raw_query"],
            decision=decision,
            plan=plan,
            normalized_results=state.get("normalized_results", {}),
            retry_count=retry_count,
        )
        return {
            "verification": verification.model_dump(),
            "retry_count": retry_count + 1 if verification.retryable else retry_count,
            "trace": merge_trace(
                state,
                {
                    "verified_at": utc_now_iso(),
                    "verification_passed": verification.passed,
                    "verification_issues": verification.issues,
                },
            ),
        }

    def answer_synthesizer_node(self, state: GraphState) -> GraphState:
        decision = RouteDecision(**state["route_decision"])
        slots = Slots(**state["slots"])
        verification = VerificationDecision(**state["verification"])
        answer = self.answer_synthesizer.synthesize(
            raw_query=state["raw_query"],
            decision=decision,
            slots=slots,
            normalized_results=state.get("normalized_results", {}),
            verification=verification,
        )
        return {"answer": answer}


def merge_trace(state: GraphState, values: dict[str, Any]) -> dict[str, Any]:
    trace = dict(state.get("trace", {}))
    trace.update(values)
    return trace


def route_after_router(state: GraphState) -> Literal["clarify", "plan"]:
    decision = RouteDecision(**state["route_decision"])
    return "clarify" if decision.needs_clarification else "plan"


def route_after_verification(state: GraphState) -> Literal["retry", "answer"]:
    verification = VerificationDecision(**state["verification"])
    return "retry" if verification.retryable else "answer"


def build_maritime_graph(runtime: MaritimeLangGraphRuntime) -> Any:
    graph = StateGraph(GraphState)
    graph.add_node("query_normalizer", runtime.query_normalizer_node)
    graph.add_node("router", runtime.router_node)
    graph.add_node("clarification", runtime.clarification_node)
    graph.add_node("plan_builder", runtime.plan_builder_node)
    graph.add_node("tool_executor", runtime.tool_executor_node)
    graph.add_node("result_normalizer", runtime.result_normalizer_node)
    graph.add_node("verifier", runtime.verifier_node)
    graph.add_node("answer_synthesizer", runtime.answer_synthesizer_node)

    graph.add_edge(START, "query_normalizer")
    graph.add_edge("query_normalizer", "router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
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

def _print_tool_log(tool_id: ToolId, kwargs: Mapping[str, Any]) -> None:
    print(
        f"[ToolAdapter] executed={tool_id} args={json.dumps(dict(kwargs), ensure_ascii=False, default=str)}",
        flush=True,
    )


def logging_weather_korean_peninsula(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("weather_korean_peninsula", kwargs)
    return {
        "scope": "korean_peninsula",
        "wind_direction": "NW",
        "wind_speed": 7.2,
        "air_temperature": 18.4,
        "water_temperature": 15.9,
        "max_wave_height": 2.1,
        "significant_wave_height": 1.4,
        "avg_wave_height": 0.9,
        "gust_speed": 12.6,
        "humidity": 72,
        "observed_at": utc_now_iso(),
    }


def logging_vessel_track_detail(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("vessel_track_detail", kwargs)
    return {
        "vessel_name": kwargs.get("vessel_name") or "SAMPLE VESSEL",
        "mmsi": kwargs.get("mmsi") or "440123456",
        "track_points": [
            {"ts": "2026-05-22T00:00:00Z", "lat": 35.08, "lon": 129.04, "speed": 10.2, "course": 68},
            {"ts": "2026-05-22T00:05:00Z", "lat": 35.10, "lon": 129.12, "speed": 11.1, "course": 72},
            {"ts": "2026-05-22T00:10:00Z", "lat": 35.13, "lon": 129.20, "speed": 10.8, "course": 75},
        ],
        "observed_at": utc_now_iso(),
    }


def logging_fleet_od_flow(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("fleet_od_flow", kwargs)
    return {
        "top_flows": [
            {"origin": "Busan", "destination": "Tsushima Strait", "vessel_count": 47},
            {"origin": "Incheon", "destination": "Yellow Sea", "vessel_count": 32},
            {"origin": "Yeosu", "destination": "Jeju", "vessel_count": 21},
        ],
        "observed_at": utc_now_iso(),
    }


def logging_fleet_density_by_area(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("fleet_density_by_area", kwargs)
    return {
        "areas": [
            {"area": "Busan Approach", "vessel_count": 82, "density_level": "very_high"},
            {"area": "Incheon Anchorage", "vessel_count": 54, "density_level": "high"},
            {"area": "East Sea Offshore", "vessel_count": 18, "density_level": "medium"},
        ],
        "observed_at": utc_now_iso(),
    }


def logging_fleet_speed_by_area(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("fleet_speed_by_area", kwargs)
    return {
        "areas": [
            {"area": "Busan Approach", "avg_speed": 4.6, "min_speed": 0.8, "max_speed": 13.2},
            {"area": "Incheon Anchorage", "avg_speed": 3.1, "min_speed": 0.0, "max_speed": 9.7},
            {"area": "East Sea Offshore", "avg_speed": 12.4, "min_speed": 7.3, "max_speed": 18.5},
        ],
        "observed_at": utc_now_iso(),
    }


def logging_fleet_anomalous_movement(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("fleet_anomalous_movement", kwargs)
    return {
        "selection_criteria": {
            "rapid_course_change": "5분 이내 침로 변화 45도 이상",
            "rapid_speed_change": "5분 이내 속도 변화 7kn 이상",
            "loitering": "좁은 반경 내 20분 이상 반복 이동",
        },
        "anomalous_vessels": [
            {
                "vessel_name": "SAMPLE-ALPHA",
                "mmsi": "440111111",
                "area": "Busan Approach",
                "anomaly_type": "rapid_course_change",
                "score": 0.91,
            },
            {
                "vessel_name": "SAMPLE-BRAVO",
                "mmsi": "440222222",
                "area": "Incheon Anchorage",
                "anomaly_type": "loitering",
                "score": 0.83,
            },
        ],
        "observed_at": utc_now_iso(),
    }


def logging_fleet_direction_8way(**kwargs: Any) -> dict[str, Any]:
    _print_tool_log("fleet_direction_8way", kwargs)
    return {
        "directions": [
            {"direction": "NE", "count": 64, "ratio": 28.1},
            {"direction": "E", "count": 48, "ratio": 21.1},
            {"direction": "SW", "count": 39, "ratio": 17.1},
            {"direction": "N", "count": 24, "ratio": 10.5},
        ],
        "observed_at": utc_now_iso(),
    }


def build_logging_tool_adapters() -> dict[ToolId, ToolAdapter]:
    return {
        "weather_korean_peninsula": logging_weather_korean_peninsula,
        "vessel_track_detail": logging_vessel_track_detail,
        "fleet_od_flow": logging_fleet_od_flow,
        "fleet_density_by_area": logging_fleet_density_by_area,
        "fleet_speed_by_area": logging_fleet_speed_by_area,
        "fleet_anomalous_movement": logging_fleet_anomalous_movement,
        "fleet_direction_8way": logging_fleet_direction_8way,
    }


def create_maritime_app(
    *,
    tool_adapters: Mapping[ToolId, ToolAdapter],
    llm: ChatOpenAI | None = None,
    model: str | None = None,
) -> Any:
    runtime = MaritimeLangGraphRuntime(
        llm=ChatOpenAI(
            model="openai/gpt-oss-20b",
            api_key="ai",
            base_url="http://192.168.0.110:8000/v1"
        ),
        tool_adapters=tool_adapters,
    )
    return build_maritime_graph(runtime)


def invoke_maritime_app(app: Any, query: str, *, include_trace: bool = False) -> dict[str, Any]:
    state = app.invoke({"raw_query": query, "retry_count": 0})
    response = {
        "answer": state.get("answer"),
        "selected_intent": state.get("selected_intent"),
        "selected_tools": state.get("trace", {}).get("selected_tools", []),
        "confidence": state.get("trace", {}).get("confidence"),
    }
    if include_trace:
        response["state"] = state
    return response

def chat_loop():
    parser = argparse.ArgumentParser(description="Maritime LangGraph agent architecture demo")
    parser.add_argument(
        "query",
        nargs="*",
        default=["지금 위험해 보이는 해역 있어?"],
        help="User query to run through the maritime agent graph",
    )
    parser.add_argument("--trace", action="store_true", help="Include full graph state in the output")
    args = parser.parse_args()
    
    graph = create_maritime_app(tool_adapters=build_logging_tool_adapters())

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            print("테스트를 종료합니다.")
            break
            
        if not user_input:
            continue
        
        output = invoke_maritime_app(graph, user_input, include_trace=args.trace)
        print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    chat_loop()