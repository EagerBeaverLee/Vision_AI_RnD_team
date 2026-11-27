from my_battlefield_crew.crews.battlefield_models import MaritimeSituationReport
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


def build_final_markdown(report: MaritimeSituationReport, context: SimulationContext) -> str:
    """Pydantic 리포트와 context.artifacts의 HTML 블록을 결합해 단일 Markdown 문서 생성"""
    sections = []
    step_num = 1

    # (artifact_key, 섹션 제목, 데이터 존재 여부, LLM 분석 텍스트)
    section_specs = [
        ("top_dense_zones", "[구역별 밀집 현황]", report.top_dense_zones),
        ("main_routes", "[주요 항로 흐름 분석]", report.main_routes),
        ("main_directions", "[주요 이동 방향 분석]", report.main_directions),
        ("zone_speeds", "[해역별 선박 속도 분석]", report.zone_speeds),
        ("port_activities", "[주요 항만 입출항 및 정박 현황]", report.port_activities),
        ("ship_voyage_status", "[선박 유형별 항해 및 기동 상태]", report.ship_voyage_status),
        ("unusual_ships", "[주요 선박 특이 기동 상세 분석]", report.unusual_ships),
    ]

    for key, title, data_obj in section_specs:
        # 해당 도구가 호출되지 않았으면 섹션 자체를 생략
        if not data_obj:
            continue

        block_parts = [f"### {step_num}. {title}"]

        if key == "top_dense_zones":
            clusters_rows = [
                f"| {z.name} | {z.total_stay_index} | {getattr(z, 'military_implication', '주요 해역')} |"
                for z in report.top_dense_zones[:5]
            ]
            block_parts.append(
                "| 해역명 | 총 정박 지수 | 비고 |\n|---|---|---|\n"
                + "\n".join(clusters_rows)
            )
    
        # 3. 구역별 이동 속도 현황
        if key == "zone_speeds":
            block_parts.append("\n".join(
                    [
                        f"- {s.name}: 평균 {s.mean:.2f} Knot (최대 {s.max:.2f} Knot)"
                        for s in report.zone_speeds
                    ]
                )
            )
    
        # 4. 주요 교통 흐름
        if key == "main_directions":
            block_parts.append("\n".join(
                    [
                        f"- {d.direction} 방향: {d.ship_count}척 (평균 속도 {d.average_speed_knot} Knot)"
                        for d in report.main_directions
                    ]
                )
            )
    
        # 5. 구역 간 주요 항로(OD Flow)
        if key == "main_routes":
            block_parts.append("\n".join(
                    [
                        f"- {r.origin_zone} -> {r.dest_zone} (가중치: {r.weight})"
                        for r in report.main_routes[:5]
                    ]
                )
            )
    
    
        # 7. 주요 항만별 입출항 현황 (표준 중첩 리스트 문법 적용: 2칸 공백 들여쓰기)
        if key == "port_activities":
            port_blocks = []
            for p in report.port_activities:
                count = 0
                lines = [f"* **{p.port_name}**"]
                if getattr(p, "anchored_ships_detail", None):
                    lines.append(
                        f"  * **정박/대기 중인 선박 (총 {p.anchored_count}척)**"
                    )
                    lines.extend([f"    - {s}" for s in p.anchored_ships_detail])
                    count += 1
                if getattr(p, "departures_detail", None):
                    lines.append(
                        f"  * **출발/기동 선박 (총 {p.departure_count}척)**"
                    )
                    lines.extend([f"    - {s}" for s in p.departures_detail])
                    count += 1
                if getattr(p, "arrivals_detail", None):
                    lines.append(
                        f"  * **도착/진입 선박 (총 {p.arrival_count}척)**"
                    )
                    lines.extend([f"    - {s}" for s in p.arrivals_detail])
                    count += 1
                if(count != 0):
                    port_blocks.append("\n".join(lines))
            block_parts.append("\n\n".join(port_blocks))
    
        # 8. 선박 상태별 현황 요약 (표준 마크다운 리스트 형태로 안전하게 감싸기)
        def format_status_group(title: str, ships: list) -> str:
            if not ships:
                return f"* **{title}**: 없음"
            ship_lines = "\n".join([f"  * {s.ShipName}({s.mmsi})" for s in ships])
            return f"* **{title}**\n{ship_lines}"
        
        if key == "ship_voyage_status":
            status_blocks = []
            v = report.ship_voyage_status
            status_blocks.append(
                format_status_group(
                    "순항 중인 선박 리스트", getattr(v, "moving_ships", [])
                )
            )
            status_blocks.append(
                format_status_group(
                    "정박/대기 중인 선박 리스트", getattr(v, "stop_ships", [])
                )
            )
            status_blocks.append(
                format_status_group(
                    "저속 운항 중인 선박 리스트", getattr(v, "slow_ships", [])
                )
            )
            block_parts.append("\n\n".join(status_blocks))
    
        # 9. 특이 기동 선박
        if key == "unusual_ships":
            block_parts.append("\n".join(
                    [
                        f"- **[{u.ShipName}]**: {u.turn_count}회의 변침과 {u.speed_change_count}회의 속도 변화 포착."
                        for u in report.unusual_ships
                    ]
                )
            )
        
        # 해당 도구가 저장해 둔 HTML 블록(지도/이미지/테이블 위젯)이 있으면 바로 아래에 부착
        media_html = context.artifacts.get(key)
        if media_html:
            block_parts.append(media_html)

        sections.append("\n\n".join(block_parts))
        step_num += 1

    # 마지막에 교차 분석된 최종 종합 결론 추가
    if report.final_answer:
        sections.append(f"### {step_num}. [종합 결론]\n\n{report.final_answer.strip()}")

    return "\n\n---\n\n".join(sections)