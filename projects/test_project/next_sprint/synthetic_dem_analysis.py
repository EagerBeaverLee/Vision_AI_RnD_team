import rasterio
import numpy as np
from scipy.ndimage import uniform_filter
import matplotlib.pyplot as plt

# ====================================================
# 1. 실제 DEM 파일 불러오기
# ====================================================
# 다운로드받은 DEM 파일 경로로 변경하세요.
dem_path = "testing_DEM.tif" 

print(f"1. '{dem_path}' 데이터 읽는 중...")

with rasterio.open(dem_path) as src:
    # 고도 데이터 읽기 (1번째 밴드)
    dem_data = src.read(1).astype(np.float32)
    nodata_val = src.nodata
    meta = src.meta
    res_x, res_y = src.res # 픽셀 해상도 (예: 30m, 10m 등)

# NoData 값(해당 영역 외)을 NaN으로 처리하여 연산 에러 방지
if nodata_val is not None:
    dem_data[dem_data == nodata_val] = np.nan

print(f"- 데이터 크기: {dem_data.shape[0]} x {dem_data.shape[1]} 픽셀")
print(f"- 해상도: 약 {abs(res_x):.1f}m x {abs(res_y):.1f}m")
print(f"- 고도 범위: {np.nanmin(dem_data):.1f}m ~ {np.nanmax(dem_data):.1f}m")

# ====================================================
# 2. 실제 DEM 지형 지표 연산 (TPI 기반)
# ====================================================
print("2. 지형 특성 연산 중...")

# [핵심] 해상도에 맞춰 분석 윈도우 크기(픽셀 수) 결정
# 예: 30m 해상도 DEM에서 주변 300m 범위(10픽셀) 비교
window_size = 11  # 홀수 사용 (11x11 픽셀 창)

# NaN 값이 포함된 경우를 고려한 주변 평균 고도 계산
nan_mask = np.isnan(dem_data)
dem_filled = np.where(nan_mask, np.nanmean(dem_data), dem_data)

mean_elevation = uniform_filter(dem_filled, size=window_size, mode='reflect')
tpi = dem_data - mean_elevation

# Standardized TPI (표준화 TPI): 지형의 굴곡에 맞춰 스케일링
tpi_std = (tpi - np.nanmean(tpi)) / np.nanstd(tpi)

# ====================================================
# 3. High Ground 및 Valley 임계값 적용
# ====================================================
# 표준편차 기준 임계값 (보통 +1.0 이상은 High Ground, -1.0 이하/양수 변환은 Valley)
high_ground_threshold = 1.0
valley_threshold = -1.0

high_ground_mask = np.where(tpi_std > high_ground_threshold, 1, 0)
valley_mask = np.where(tpi_std < valley_threshold, 1, 0)

# 배경(NoData) 지점 마스킹 해제
high_ground_mask[nan_mask] = 0
valley_mask[nan_mask] = 0

# ====================================================
# 4. 결과 저장 (GeoTIFF)
# ====================================================
# 추출된 High Ground 마스크를 GeoTIFF로 저장하여 QGIS 등에서 바로 열어볼 수 있게 함
output_meta = meta.copy()
output_meta.update(dtype=rasterio.uint8, count=1, nodata=0)

with rasterio.open("extracted_high_ground.tif", "w", **output_meta) as dst:
    dst.write(high_ground_mask.astype(rasterio.uint8), 1)

with rasterio.open("extracted_valley.tif", "w", **output_meta) as dst:
    dst.write(valley_mask.astype(rasterio.uint8), 1)

print("결과 파일 저장 완료: 'extracted_high_ground.tif', 'extracted_valley.tif'")

# ====================================================
# 5. 결과 시각화
# ====================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# 1) 실제 DEM 고도
im0 = axes[0].imshow(dem_data, cmap='terrain')
axes[0].set_title("Real DEM (Elevation)")
plt.colorbar(im0, ax=axes[0], label="Elevation (m)")

# 2) Valley (계곡 / 곡저)
axes[1].imshow(dem_data, cmap='gray')
axes[1].imshow(np.ma.masked_where(valley_mask == 0, valley_mask), cmap='cool', alpha=0.7)
axes[1].set_title("Extracted Valleys (Blue)")

# 3) High Ground (고지 / 능선)
axes[2].imshow(dem_data, cmap='gray')
axes[2].imshow(np.ma.masked_where(high_ground_mask == 0, high_ground_mask), cmap='autumn', alpha=0.7)
axes[2].set_title("Extracted High Ground (Red/Yellow)")

for ax in axes:
    ax.axis('off')

plt.tight_layout()
plt.show()