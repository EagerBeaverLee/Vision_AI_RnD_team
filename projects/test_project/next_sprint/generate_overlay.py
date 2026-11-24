import json
import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import Button

# 1. JSON 설정 파일 로드
CONFIG_FILE = 'scenario_config.json'

if not os.path.exists(CONFIG_FILE):
    print(f"Error: '{CONFIG_FILE}' 파일이 존재하지 않습니다.")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    scenario_data = json.load(f)

# 2. Matplotlib 피겨 및 축 설정
fig, ax = plt.subplots(figsize=(11, 7.5))
plt.subplots_adjust(bottom=0.15) # 하단 버튼 배치 영역 확보

ax.set_xlim(0, 1100)
ax.set_ylim(750, 0) # Pygame Y축 좌표계와 동일하게 설정 (Top-Left 0,0)
ax.set_facecolor('#e1ebe1')

# 전역 상태 변수
current_coa = 'COA1'
show_range_circles = True

# 3. 지형 및 배경 렌더링 함수
def draw_map_base():
    ax.clear()
    ax.set_xlim(0, 1100)
    ax.set_ylim(750, 0)
    ax.set_facecolor('#e1ebe1')
    ax.grid(True, linestyle=':', alpha=0.4, color='#888888')

    # 도로
    ax.add_patch(patches.Rectangle((480, 0), 50, 750, color='#787878', zorder=1))
    ax.text(505, 700, 'ROAD', color='white', rotation=90, ha='center', va='center', weight='bold', alpha=0.7)

    # 능선 (Ridge Lines)
    ax.add_patch(patches.Rectangle((80, 240), 300, 35, color='#b48c64', zorder=1))
    ax.add_patch(patches.Rectangle((420, 280), 160, 35, color='#b48c64', zorder=1))
    ax.add_patch(patches.Rectangle((650, 320), 180, 35, color='#b48c64', zorder=1))
    ax.text(230, 257, 'Ridge Line (Cover +35%)', color='white', ha='center', va='center', fontsize=8, weight='bold')

    # 500 고지 & 최종 목표(OBJ)
    ax.add_patch(patches.Circle((610, 150), 40, color='#c8a078', zorder=1))
    ax.text(610, 150, '500 Hill', color='white', ha='center', va='center', fontsize=8, weight='bold')
    
    ax.add_patch(patches.Circle((630, 70), 28, color='#7828a0', zorder=2))
    ax.text(630, 70, 'OBJ', color='white', ha='center', va='center', weight='bold', fontsize=10)

    # 접적선 (FLOT)
    ax.plot([30, 810], [420, 420], color='#2864dc', linestyle='--', linewidth=1.5, alpha=0.7)
    ax.text(45, 410, 'FLOT', color='#2864dc', weight='bold', fontsize=9)

# 4. 투명도(Overlay) 동적 렌더링 함수
def update_overlay(selected_coa):
    global current_coa
    current_coa = selected_coa

    draw_map_base()

    # --- A. RED 부대 렌더링 ---
    for r in scenario_data.get('RED_UNITS', []):
        # 사거리/탐지 반경 투명 원
        if show_range_circles:
            circle = patches.Circle((r['x'], r['y']), r['rng'], color='red', alpha=0.12, zorder=2)
            ax.add_patch(circle)
            edge_circle = patches.Circle((r['x'], r['y']), r['rng'], color='red', fill=False, linestyle=':', alpha=0.4, zorder=2)
            ax.add_patch(edge_circle)

        # 적군 심볼 (Square)
        ax.plot(r['x'], r['y'], 'rs', markersize=9, markeredgecolor='black', zorder=5)
        
        # 텍스트 라벨 (공격력 및 탐지확률)
        det_pct = int(r.get('detect_prob', 0.7) * 100)
        label = f"{r['name']}\n(ATK:{r['attack']} / DET:{det_pct}%)"
        ax.text(r['x'], r['y'] - 14, label, color='#8b0000', fontsize=8, ha='center', va='bottom', weight='bold', zorder=6)

    # --- B. BLUE 부대 및 선택된 COA 기동 축선 렌더링 ---
    waypoints_data = scenario_data.get('WAYPOINTS', {}).get(selected_coa, {})

    for b in scenario_data.get('BLUE_UNITS', []):
        unit_name = b['name']
        start_x, start_y = b['x'], b['y']

        # 아군 심볼 (Circle)
        symbol = 'b^' if b.get('type') == 'TANK' else 'bo' # 탱크는 삼각형, 보병은 원형
        ax.plot(start_x, start_y, symbol, markersize=10, markeredgecolor='black', zorder=5)
        
        # 텍스트 라벨
        speed_val = b['speed']
        det_pct = int(b.get('detect_prob', 0.7) * 100)
        label = f"{unit_name}\n(SPD:{speed_val} / DET:{det_pct}%)"
        ax.text(start_x, start_y + 14, label, color='#00008b', fontsize=8, ha='center', va='top', weight='bold', zorder=6)

        # COA 기동 경로(Waypoints) 화살표 그리기
        if unit_name in waypoints_data:
            pts = [[start_x, start_y]] + waypoints_data[unit_name]
            
            # 경로선 연계
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color='#1e90ff', linestyle='--', linewidth=2, alpha=0.8, zorder=3)
            
            # 중간 기동 화살표 표출
            for i in range(len(pts) - 1):
                p1 = pts[i]
                p2 = pts[i+1]
                ax.annotate('', xy=(p2[0], p2[1]), xytext=(p1[0], p1[1]),
                            arrowprops=dict(arrowstyle="-|>", color="#0055ff", lw=2, mutation_scale=12),
                            zorder=4)

    plt.title(f"Military Operational Overlay - Selected [{selected_coa}] Mode", fontsize=13, weight='bold', loc='center')
    fig.canvas.draw_idle()

# 5. UI 버튼 및 이벤트 핸들러
ax_btn1 = plt.axes([0.15, 0.03, 0.15, 0.05])
ax_btn2 = plt.axes([0.32, 0.03, 0.15, 0.05])
ax_btn3 = plt.axes([0.49, 0.03, 0.15, 0.05])
ax_btn_toggle = plt.axes([0.68, 0.03, 0.18, 0.05])

btn_coa1 = Button(ax_btn1, 'COA 1 (Center)', color='#dddddd', hovercolor='#ffd700')
btn_coa2 = Button(ax_btn2, 'COA 2 (Right)', color='#dddddd', hovercolor='#ffd700')
btn_coa3 = Button(ax_btn3, 'COA 3 (Left)', color='#dddddd', hovercolor='#ffd700')
btn_toggle = Button(ax_btn_toggle, 'Toggle Ranges', color='#b0e0e6', hovercolor='#00bfff')

def on_click_coa1(event): update_overlay('COA1')
def on_click_coa2(event): update_overlay('COA2')
def on_click_coa3(event): update_overlay('COA3')

def on_click_toggle(event):
    global show_range_circles
    show_range_circles = not show_range_circles
    update_overlay(current_coa)

btn_coa1.on_clicked(on_click_coa1)
btn_coa2.on_clicked(on_click_coa2)
btn_coa3.on_clicked(on_click_coa3)
btn_toggle.on_clicked(on_click_toggle)

# 최초 실행 시 COA1 선택 상태로 표출
update_overlay('COA1')
plt.show()