import pygame
import math
import random
import time

# --- 초깃값 및 색상 정의 ---
pygame.init()
pygame.font.init()

WIDTH, HEIGHT = 1100, 750
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Military M&S Simulation - COA Win Rate Tester")
clock = pygame.time.Clock()

# Color Palette
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
GRAY = (200, 200, 200)
DARK_GRAY = (50, 50, 50)
RED_TEAM = (220, 60, 60)
BLUE_TEAM = (40, 120, 220)
GREEN_TERRAIN = (180, 210, 180)
RIDGE_COLOR = (160, 120, 80)
ROAD_COLOR = (100, 100, 100)
PURPLE_OBJ = (140, 40, 180)
YELLOW_ACCENT = (240, 200, 40)

FONT_S = pygame.font.SysFont("malgungothic", 13)
FONT_M = pygame.font.SysFont("malgungothic", 16, bold=True)
FONT_L = pygame.font.SysFont("malgungothic", 22, bold=True)

# --- 지형 정의 ---
ROAD_RECT = pygame.Rect(480, 0, 50, 600)
OBJECTIVE_POS = (630, 70)
HILL_500_POS = (610, 150)
RIDGES = [
    pygame.Rect(100, 240, 300, 40),
    pygame.Rect(430, 280, 150, 40),
    pygame.Rect(650, 320, 200, 40)
]

class Unit:
    def __init__(self, name, side, unit_type, x, y, hp=100, attack=15, armor=1.0, speed=2.0, rng=100):
        self.name = name
        self.side = side  # 'BLUE' or 'RED'
        self.type = unit_type # 'INF', 'TANK'
        self.x = x
        self.y = y
        self.max_hp = hp
        self.hp = hp
        self.attack = attack
        self.armor = armor
        self.base_speed = speed
        self.rng = rng
        self.waypoints = []
        self.target = None
        self.morale = 100
        self.alive = True

    def update_movement(self):
        if not self.alive:
            return

        # 속도 계산 (지형 영향)
        speed = self.base_speed
        if ROAD_RECT.collidepoint(self.x, self.y):
            speed *= 1.5 # 도로 이용 시 속도 증가

        # 경로 이동
        if self.waypoints:
            tx, ty = self.waypoints[0]
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            if dist < speed:
                self.x, self.y = tx, ty
                self.waypoints.pop(0)
            else:
                self.x += (dx / dist) * speed
                self.y += (dy / dist) * speed

    def take_damage(self, dmg):
        # 고지대 및 능선 커버 방어 보정
        defense_bonus = 1.0
        for ridge in RIDGES:
            if ridge.collidepoint(self.x, self.y):
                defense_bonus *= 0.6 # 40% 피해 감소
        if math.hypot(self.x - HILL_500_POS[0], self.y - HILL_500_POS[1]) < 40:
            defense_bonus *= 0.5 # 50% 피해 감소

        actual_dmg = (dmg / self.armor) * defense_bonus * random.uniform(0.8, 1.2)
        self.hp -= actual_dmg
        self.morale -= actual_dmg * 0.3

        if self.hp <= 0:
            self.hp = 0
            self.alive = False

    def combat_step(self, enemies):
        if not self.alive:
            return

        # 가장 가까운 살아있는 적 탐색
        best_target = None
        min_dist = float('inf')
        for e in enemies:
            if not e.alive:
                continue
            d = math.hypot(e.x - self.x, e.y - self.y)
            if d < min_dist:
                min_dist = d
                best_target = e

        if best_target and min_dist <= self.rng:
            best_target.take_damage(self.attack * 0.05) # 프레임 단위 데미지

class SimulationEngine:
    def __init__(self):
        self.reset('COA1')

    def reset(self, coa='COA1'):
        self.coa = coa
        self.time_ticks = 0
        self.winner = None
        self.is_finished = False

        # --- 적군(RED) 배치 ---
        self.red_units = [
            Unit('RED 1 CO', 'RED', 'INF', 220, 180, hp=120, attack=14, speed=1.2, rng=110),
            Unit('RED 2 CO', 'RED', 'INF', 540, 240, hp=100, attack=12, speed=1.2, rng=100),
            Unit('RED 3 CO (-1)', 'RED', 'INF', 610, 150, hp=150, attack=16, speed=1.0, rng=120),
            Unit('RED 3 CO 1PLT', 'RED', 'INF', 750, 280, hp=80, attack=10, speed=1.2, rng=100)
        ]

        # --- 아군(BLUE) 기본 생성 ---
        self.blue_units = [
            Unit('BLUE 1 CO', 'BLUE', 'INF', 180, 520, hp=100, attack=15, speed=1.5, rng=110),
            Unit('BLUE 2 CO', 'BLUE', 'INF', 500, 520, hp=100, attack=15, speed=1.5, rng=110),
            Unit('BLUE 3 CO (-1)', 'BLUE', 'INF', 720, 520, hp=80, attack=13, speed=1.5, rng=100),
            Unit('BLUE Tank CO', 'BLUE', 'TANK', 120, 620, hp=250, attack=35, armor=2.5, speed=1.8, rng=150),
            Unit('BLUE 3 CO 1PLT', 'BLUE', 'INF', 200, 620, hp=80, attack=13, speed=1.5, rng=100)
        ]

        # --- COA별 웨이포인트(이동 경로) 설정 ---
        self.apply_coa_paths()

    def apply_coa_paths(self):
        b_dict = {u.name: u for u in self.blue_units}

        if self.coa == 'COA1': # 중앙 기동 타격
            b_dict['BLUE Tank CO'].waypoints = [(500, 500), (500, 250), (630, 120), OBJECTIVE_POS]
            b_dict['BLUE 2 CO'].waypoints = [(520, 350), (580, 200), OBJECTIVE_POS]
            b_dict['BLUE 1 CO'].waypoints = [(200, 350), (220, 220)]
            b_dict['BLUE 3 CO (-1)'].waypoints = [(720, 400), (750, 300)]
            b_dict['BLUE 3 CO 1PLT'].waypoints = [(480, 550), (500, 350)]

        elif self.coa == 'COA2': # 우측 우회 타격
            b_dict['BLUE 3 CO (-1)'].waypoints = [(750, 420), (760, 280), (630, 150)]
            b_dict['BLUE 3 CO 1PLT'].waypoints = [(700, 580), (740, 350), (630, 150)]
            b_dict['BLUE Tank CO'].waypoints = [(500, 600), (500, 350), (630, 100)]
            b_dict['BLUE 1 CO'].waypoints = [(200, 400)]
            b_dict['BLUE 2 CO'].waypoints = [(500, 400)]

        elif self.coa == 'COA3': # 좌측 고지 제압
            b_dict['BLUE 1 CO'].waypoints = [(180, 350), (200, 200)]
            b_dict['BLUE Tank CO'].waypoints = [(150, 450), (220, 220)]
            b_dict['BLUE 2 CO'].waypoints = [(450, 450), (500, 300)]
            b_dict['BLUE 3 CO (-1)'].waypoints = [(700, 450)]
            b_dict['BLUE 3 CO 1PLT'].waypoints = [(400, 500)]

    def step(self):
        if self.is_finished:
            return

        self.time_ticks += 1

        # 이동 및 전투 업데이트
        for u in self.blue_units:
            u.update_movement()
            u.combat_step(self.red_units)

        for u in self.red_units:
            u.update_movement()
            u.combat_step(self.blue_units)

        # 승리 조건 검사
        blue_alive = any(u.alive for u in self.blue_units)
        red_alive = any(u.alive for u in self.red_units)

        # 아군이 목표 지점(Objective)에 도달했는지 확인
        obj_reached = any(u.alive and math.hypot(u.x - OBJECTIVE_POS[0], u.y - OBJECTIVE_POS[1]) < 35 for u in self.blue_units)

        if obj_reached or (blue_alive and not red_alive):
            self.winner = 'BLUE'
            self.is_finished = True
        elif not blue_alive:
            self.winner = 'RED'
            self.is_finished = True
        elif self.time_ticks > 2000: # 타임아웃 (적 방어 성공)
            self.winner = 'RED'
            self.is_finished = True

def run_monte_carlo(sim, coa, num_runs=100):
    """배치 몬테카를로 시뮬레이션으로 승률 계산"""
    blue_wins = 0
    total_time = 0
    total_blue_hp_percent = 0

    for _ in range(num_runs):
        sim.reset(coa)
        while not sim.is_finished:
            sim.step()
        if sim.winner == 'BLUE':
            blue_wins += 1
        total_time += sim.time_ticks
        
        # 잔여 HP 비율 계산
        surviving_hp = sum(u.hp for u in sim.blue_units)
        max_hp = sum(u.max_hp for u in sim.blue_units)
        total_blue_hp_percent += (surviving_hp / max_hp) * 100

    win_rate = (blue_wins / num_runs) * 100
    avg_time = total_time / num_runs
    avg_hp = total_blue_hp_percent / num_runs
    return win_rate, avg_time, avg_hp

# --- 메인 실행 루프 ---
def main():
    sim = SimulationEngine()
    current_coa = 'COA1'
    batch_results = {}

    # 버튼 정의
    btn_coa1 = pygame.Rect(860, 40, 210, 40)
    btn_coa2 = pygame.Rect(860, 90, 210, 40)
    btn_coa3 = pygame.Rect(860, 140, 210, 40)
    btn_reset = pygame.Rect(860, 200, 210, 35)
    btn_batch = pygame.Rect(860, 250, 210, 45)

    running = True
    while running:
        clock.tick(60) # 60 FPS
        
        # 이벤트 처리
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if btn_coa1.collidepoint(mx, my):
                    current_coa = 'COA1'
                    sim.reset('COA1')
                elif btn_coa2.collidepoint(mx, my):
                    current_coa = 'COA2'
                    sim.reset('COA2')
                elif btn_coa3.collidepoint(mx, my):
                    current_coa = 'COA3'
                    sim.reset('COA3')
                elif btn_reset.collidepoint(mx, my):
                    sim.reset(current_coa)
                elif btn_batch.collidepoint(mx, my):
                    # 전체 COA 몬테카를로 테스트 실행
                    for c in ['COA1', 'COA2', 'COA3']:
                        w_rate, a_time, a_hp = run_monte_carlo(sim, c, num_runs=100)
                        batch_results[c] = (w_rate, a_time, a_hp)
                    sim.reset(current_coa)

        # 시뮬레이션 연산 진행
        if not sim.is_finished:
            sim.step()

        # --- 렌더링 ---
        screen.fill(GREEN_TERRAIN)

        # 1. 지형 그리기
        pygame.draw.rect(screen, ROAD_COLOR, ROAD_RECT) # 도로
        for r in RIDGES:
            pygame.draw.rect(screen, RIDGE_COLOR, r, border_radius=5) # 능선
        pygame.draw.circle(screen, RIDGE_COLOR, HILL_500_POS, 35) # 500고지
        pygame.draw.circle(screen, PURPLE_OBJ, OBJECTIVE_POS, 25) # 목표(OBJ)

        # 지형 텍스트
        screen.blit(FONT_S.render("ROAD (Speed +50%)", True, WHITE), (482, 570))
        screen.blit(FONT_S.render("Ridge Line (Cover +40%)", True, WHITE), (150, 250))
        screen.blit(FONT_S.render("500 Hill", True, WHITE), (590, 142))
        screen.blit(FONT_M.render("OBJ", True, WHITE), (OBJECTIVE_POS[0]-14, OBJECTIVE_POS[1]-10))

        # FLOT (접적선)
        pygame.draw.line(screen, BLUE_TEAM, (50, 390), (830, 390), 2)

        # 2. 이동 경로 (Waypoints) 시각화
        for u in sim.blue_units:
            if u.alive and u.waypoints:
                pts = [(u.x, u.y)] + u.waypoints
                if len(pts) >= 2:
                    pygame.draw.lines(screen, BLUE_TEAM, False, pts, 2)

        # 3. 유닛 그리기
        all_units = sim.blue_units + sim.red_units
        for u in all_units:
            if not u.alive:
                continue
            color = BLUE_TEAM if u.side == 'BLUE' else RED_TEAM
            size = 14 if u.type == 'TANK' else 9
            
            # 사거리 원 표시 (선택사항)
            pygame.draw.circle(screen, color, (int(u.x), int(u.y)), size)
            pygame.draw.circle(screen, BLACK, (int(u.x), int(u.y)), size, 2)

            # 체력바 Draw
            hp_ratio = u.hp / u.max_hp
            pygame.draw.rect(screen, BLACK, (u.x - 15, u.y - size - 8, 30, 4))
            pygame.draw.rect(screen, color, (u.x - 15, u.y - size - 8, int(30 * hp_ratio), 4))
            
            # 유닛명
            lbl = FONT_S.render(u.name, True, BLACK)
            screen.blit(lbl, (u.x - 20, u.y + size + 2))

        # 4. 오른쪽 대시보드 UI 패널
        pygame.draw.rect(screen, DARK_GRAY, (840, 0, 260, HEIGHT))

        # 대시보드 제목
        screen.blit(FONT_L.render("M&S Control Panel", True, WHITE), (855, 10))

        # 버튼 그리기
        for btn, name, c_code in [(btn_coa1, "Select COA 1 (Center)", 'COA1'),
                                  (btn_coa2, "Select COA 2 (Right)", 'COA2'),
                                  (btn_coa3, "Select COA 3 (Left)", 'COA3')]:
            b_color = YELLOW_ACCENT if current_coa == c_code else GRAY
            pygame.draw.rect(screen, b_color, btn, border_radius=4)
            screen.blit(FONT_M.render(name, True, BLACK), (btn.x + 10, btn.y + 10))

        pygame.draw.rect(screen, WHITE, btn_reset, border_radius=4)
        screen.blit(FONT_M.render("Reset Simulation", True, BLACK), (btn_reset.x + 35, btn_reset.y + 7))

        pygame.draw.rect(screen, PURPLE_OBJ, btn_batch, border_radius=4)
        screen.blit(FONT_M.render("Run 100 Sim Batch", True, WHITE), (btn_batch.x + 25, btn_batch.y + 12))

        # 시뮬레이션 상태 정보
        status_text = f"Active COA: {current_coa}"
        screen.blit(FONT_M.render(status_text, True, WHITE), (855, 310))
        screen.blit(FONT_S.render(f"Simulation Ticks: {sim.time_ticks}", True, GRAY), (855, 335))

        if sim.is_finished:
            res_color = BLUE_TEAM if sim.winner == 'BLUE' else RED_TEAM
            res_txt = f"RESULT: {sim.winner} VICTORY!"
            screen.blit(FONT_L.render(res_txt, True, res_color), (855, 360))

        # 몬테카를로 통계 출력
        pygame.draw.line(screen, GRAY, (855, 400), (1080, 400), 1)
        screen.blit(FONT_L.render("Monte Carlo Results", True, WHITE), (855, 410))

        if batch_results:
            y_off = 440
            for c_name, (w_rate, a_time, a_hp) in batch_results.items():
                screen.blit(FONT_M.render(f"[{c_name}]", True, YELLOW_ACCENT), (855, y_off))
                screen.blit(FONT_S.render(f" Win Rate: {w_rate:.1f}%", True, WHITE), (855, y_off + 20))
                screen.blit(FONT_S.render(f" Avg Time: {a_time:.0f} ticks | HP: {a_hp:.1f}%", True, GRAY), (855, y_off + 35))
                y_off += 60
        else:
            screen.blit(FONT_S.render("Click [Run 100 Sim Batch]", True, GRAY), (855, 450))
            screen.blit(FONT_S.render("to compute win rates.", True, GRAY), (855, 470))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()