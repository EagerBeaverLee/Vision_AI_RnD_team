# Skill: ocean_timeseries_resampling_with_qc_and_plot

## Description
시계열 데이터에서 품질 마스크(QC)를 적용한 뒤 지정된 영역의 평균값을 추출하고, 리샘플링 및 최종 시계열 그래프를 생성한다.

## Allowed Tools
1. `load_dataset_tool`: 원본 격자 데이터 로드
2. `apply_qc_mask_tool`: 결측치 및 이상치 플래그 필터링 마스크 적용
3. `regional_mean_tool`: 공간 평균값 추출 및 1차원 시계열 변환
4. `resample_tool`: 시간 주기 변경 (freq='M', 'W' 등)
5. `plot_timeseries_tool`: 최종 리샘플링 시계열 그래프 렌더링 및 이미지 저장

## Execution Rules
- Stage 1: `load_dataset_tool`로 지정 영역 원본 데이터 로드
- Stage 2: `apply_qc_mask_tool`을 호출해 Stage 1 데이터에 품질 마스크 적용 (중요: 마스킹을 평균 계산보다 먼저 수행해야 왜곡 방지)
- Stage 3: `regional_mean_tool`로 공간 차원 축소 (마스킹된 데이터 참조)
- Stage 4: `resample_tool`을 호출해 지정된 주기로 리샘플링
- Stage 5: `plot_timeseries_tool`을 호출해 최종 차트 파일 생성