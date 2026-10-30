# Skill: ocean_spatial_anomaly_detection

## Description
특정 시점 또는 기간의 해양 격자 데이터에 품질 마스크(QC)를 적용하고, 이상치가 발생한 공간 영역을 식별하여 시각화 차트를 생성한다. (시간 리샘플링은 수행하지 않음)

## Allowed Tools
1. `load_dataset_tool`: 원본 격자 데이터 로드
2. `apply_qc_mask_tool`: 결측치 및 비정상 스파이크 제거
3. `plot_timeseries_tool`: 이상치 식별 공간 분포/차트 저장

## Execution Rules
- Stage 1: `load_dataset_tool`로 지정 영역 원본 데이터 로드
- Stage 2: `apply_qc_mask_tool`로 이상치 필터링 마스크 적용 (임계값 설정 필수)
- Stage 3: `plot_timeseries_tool`을 호출해 최종 이상치 마스크 결과 시각화
- 주의: 시계열 다운샘플링이나 평균 추출(resample_tool, regional_mean_tool)은 호출하지 말 것.