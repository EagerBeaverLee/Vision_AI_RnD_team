import rasterio
import numpy as np
import pyvista as pv

# ====================================================
# 1. DEM 데이터 로딩 및 좌표계 정규화
# ====================================================
dem_path = "testing_DEM.tif"

print("1. DEM 데이터 로딩 중...")

with rasterio.open(dem_path) as src:
    scale = 0.25
    new_h, new_w = int(src.height * scale), int(src.width * scale)

    dem_data = src.read(
        1,
        out_shape=(new_h, new_w),
        resampling=rasterio.enums.Resampling.bilinear
    ).astype(np.float32)

    nodata = src.nodata

if nodata is not None and np.any(dem_data == nodata):
    valid_mask = dem_data != nodata
    min_elev = np.min(dem_data[valid_mask]) if np.any(valid_mask) else 0
    dem_data[~valid_mask] = min_elev

height, width = dem_data.shape

# 1000m 가상 미터 좌표 그리드
x_range = np.linspace(0, 1000, width)
y_range = np.linspace(0, 1000, height)
X, Y = np.meshgrid(x_range, y_range)

min_z, max_z = np.min(dem_data), np.max(dem_data)
elev_span = max_z - min_z if max_z != min_z else 1.0

grid = pv.StructuredGrid(X, Y, dem_data)
grid["Elevation"] = dem_data.ravel(order="F")

# ====================================================
# 2. 부대 데이터 및 밀착 오프셋 설정
# ====================================================
unit_positions = [
    {"name": "HQ (1여단 본부)", "px": int(width * 0.3), "py": int(height * 0.4), "color": "red"},
    {"name": "Recon (수색대대)", "px": int(width * 0.7), "py": int(height * 0.3), "color": "orange"},
    {"name": "Artillery (포병대대)", "px": int(width * 0.2), "py": int(height * 0.7), "color": "purple"},
    {"name": "Comms (통신대)", "px": int(width * 0.5), "py": int(height * 0.5), "color": "green"},
]

# 마커 및 핀 오프셋 조정 (자연스럽게 낮춤)
sphere_radius = 20.0                     # 마커 구체 크기
marker_offset = 1.0   # 지면에서 마커까지 높이 (기존보다 낮춤)

# ====================================================
# 3. 3D 렌더링
# ====================================================
plotter = pv.Plotter(window_size=[1200, 800])
plotter.set_background("#1e1e24")

# 지형 추가
plotter.add_mesh(
    grid,
    scalars="Elevation",
    cmap="terrain",
    show_edges=False,
    smooth_shading=True,
    scalar_bar_args={"title": "Elevation (m)"}
)

# ----------------------------------------------------
# 지형 표면에 착 붙이는 밀착 오프셋 설정
# ----------------------------------------------------
sphere_radius = 10   # 구체 마커 크기 소형화
ground_margin = 3.0   # 지면에서 마커까지 띄우는 거리 (1m)

for unit in unit_positions:
    px, py = unit["px"], unit["py"]
    ux = x_range[px]
    uy = y_range[py]
    
    # 해당 픽셀 위치의 실제 지형 고도(Z)
    ground_z = dem_data[py, px]
    
    # 1) 마커 구체 위치: 지형 고도 + 약간의 마진
    target_z = ground_z + ground_margin + sphere_radius

    # 2) 지면 연결선 (지면 -> 마커 중심)
    line = pv.Line([ux, uy, ground_z], [ux, uy, target_z])
    plotter.add_mesh(line, color=unit["color"], line_width=2)

    # 3) 3D 구형 마커 생성
    sphere = pv.Sphere(radius=sphere_radius, center=(ux, uy, target_z))
    plotter.add_mesh(sphere, color=unit["color"])

    # 4) [핵심] 라벨 위치: 구체 바로 위 1m 지점
    label_z = target_z + sphere_radius + 1.0
    
    plotter.add_point_labels(
        points=np.array([[ux, uy, label_z]]),
        labels=[unit["name"]],
        font_size=10,
        text_color="white",
        shadow=True,
        always_visible=True
    )

# 고도 비율 교정
plotter.set_scale(xscale=1.0, yscale=1.0, zscale=0.3)

plotter.show_axes()
print("Label 위치 밀착 조율 완료!")
plotter.show()