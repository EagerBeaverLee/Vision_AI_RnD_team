# Maritime LangGraph Agent Architecture

이 예제는 한반도 해상/선박 분석 tool 7개를 기반으로 한 LangGraph agent 시스템 구현입니다.

## 구조

```text
User Query
  -> QueryNormalizer
  -> HybridRouter
  -> SlotValidator
  -> PlanBuilder
  -> ToolExecutor
  -> ResultNormalizer
  -> Verifier
  -> AnswerSynthesizer
```

## Agent

- `WeatherAgent`: 현재 한반도 평균 날씨 tool 담당
- `VesselDetailAgent`: 특정 선박명 또는 MMSI 기반 상세 항적 tool 담당
- `FleetAnalyticsAgent`: OD flow, 밀집도, 속도, 특이기동, 8방위 분석 tool 담당
- `InsightAgent`: 여러 분석 결과를 종합해 위험/운항 상황을 해석
- `ClarificationAgent`: 필수 slot 누락 시 재질문
- `VerifierAgent`: tool 결과와 사용자 의도 간 일치 여부 검증

## 실행

```powershell
python maritime_agent_system.py "지금 위험해 보이는 해역 있어?"
python maritime_agent_system.py "440123456 선박 항적 보여줘"
python maritime_agent_system.py "현재 전체 선박 밀집도와 속도 요약해줘"
```

현재 파일에는 데모용 tool adapter가 포함되어 있습니다.
실제 서비스에서는 `build_demo_adapters()` 대신 실제 tool 함수를 연결하면 됩니다.

```python
runtime = MaritimeAgentRuntime(
    adapters={
        "weather_korean_peninsula": real_weather_tool,
        "vessel_track_detail": real_vessel_track_tool,
        "fleet_od_flow": real_od_flow_tool,
        "fleet_density_by_area": real_density_tool,
        "fleet_speed_by_area": real_speed_tool,
        "fleet_anomalous_movement": real_anomaly_tool,
        "fleet_direction_8way": real_direction_tool,
    }
)
app = build_maritime_graph(runtime)
result = app.invoke({"raw_query": "지금 위험해 보이는 해역 있어?", "retry_count": 0})
```

## LangGraph 미설치 환경

`langgraph`가 설치되어 있으면 `StateGraph`로 그래프를 컴파일합니다.
설치되어 있지 않으면 로컬 데모 실행을 위해 `FallbackGraph`가 같은 노드 순서로 실행됩니다.
