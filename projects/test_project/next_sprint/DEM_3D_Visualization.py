import rasterio
import numpy as np
import plotly.graph_objects as go

# ====================================================
# 1. DEM 파일 경로 설정 및 데이터 읽기
# ====================================================
dem_path = "testing_DEM.tif"  # 사용 중인 DEM 파일 경로로 지정하세요.

print(f"'{dem_path}' 3D 시각화 데이터 처리 중...")

with rasterio.open(dem_path) as src:
    # 3D 웹 렌더링 성능 최적화를 위한 리샘플링 (1/2 해상도)
    scale_factor = 0.5 
    new_height = int(src.height * scale_factor)
    new_width = int(src.width * scale_factor)
    
    # float32 타입으로 읽어와서 NaN 및 NoData 변환 오류 방지
    dem_data = src.read(
        1,
        out_shape=(new_height, new_width),
        resampling=rasterio.enums.Resampling.bilinear
    ).astype(np.float32)

    nodata = src.nodata

# NoData 예외 처리 (최저 고도로 채움)
if nodata is not None and np.any(dem_data == nodata):
    valid_mask = dem_data != nodata
    if np.any(valid_mask):
        min_elevation = np.min(dem_data[valid_mask])
        dem_data[~valid_mask] = min_elevation
    else:
        dem_data[dem_data == nodata] = np.nan

print(f"- 시각화 격자 크기: {dem_data.shape[1]} x {dem_data.shape[0]}")
print(f"- 고도 범위: {np.nanmin(dem_data):.1f}m ~ {np.nanmax(dem_data):.1f}m")

# ====================================================
# 2. Plotly 3D Surface 생성
# ====================================================
fig = go.Figure(data=[go.Surface(
    z=dem_data,
    colorscale='earth',  # [수정] Plotly 공식 지형 컬러 스케일 ('earth', 'viridis', 'geyser' 등)
    colorbar=dict(title='Elevation (m)')
)])

# ====================================================
# 3. 3D 시점 및 레이아웃 설정
# ====================================================
fig.update_layout(
    title='Interactive 3D DEM Terrain Map',
    autosize=True,
    width=900,
    height=700,
    scene=dict(
        xaxis=dict(title='X (Pixels)'),
        yaxis=dict(title='Y (Pixels)'),
        zaxis=dict(title='Elevation (m)'),
        aspectratio=dict(x=1, y=1, z=0.3),  # Z축 비율 조정 (고도감 강조)
        camera=dict(
            eye=dict(x=1.5, y=1.5, z=1.2)   # 초기 카메라 시점
        )
    )
)

# ====================================================
# 4. 웹 브라우저 띄우기 및 HTML 파일 내보내기
# ====================================================
# 1) 기본 웹 브라우저에서 3D 맵 바로 실행
fig.show()

# 2) 전시 및 단독 배포용 HTML 파일로 저장
output_html = "interactive_3d_dem.html"
fig.write_html(output_html)
print(f"3D 전시용 파일 생성 완료: '{output_html}'")