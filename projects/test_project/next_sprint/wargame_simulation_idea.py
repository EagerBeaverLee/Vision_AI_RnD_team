import pygame
import math
import random
import json
import os

# --- 초기화 및 창 설정 ---
pygame.init()
pygame.font.init()

WIDTH, HEIGHT = 1100, 750
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Military M&S Simulation - Fixed Target & Combat Logic")
clock = pygame.time.Clock()

# --- 색상 정의 ---
COLOR_BG = (225, 235, 225)
COLOR_ROAD = (120, 120, 120)
COLOR_RIDGE = (180, 140, 100)
COLOR_HILL = (200, 160, 120)
COLOR_OBJ = (120, 40, 160)
COLOR_BLUE = (40, 100, 220)
COLOR_RED = (220, 50, 50)
COLOR_PANEL = (30, 35, 45)
COLOR_TEXT = (240, 240, 240)
COLOR_ACCENT = (245, 180, 0)
COLOR_GREEN = (40, 180, 80)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (150, 150, 150)

FONT_S = pygame.font.SysFont("malgungothic", 12)
FONT_M = pygame.font.SysFont("malgungothic", 15, bold=True)
FONT_L = pygame.font.SysFont("malgungothic", 20, bold=True)

ROAD_RECT = pygame.Rect(480, 0, 50, 750)
OBJECTIVE_POS = (630, 70)
HILL_500_POS = (610, 150)
RIDGES = [
    pygame.Rect(80, 240, 300, 35),
    pygame.Rect(420, 280, 160, 35),
    pygame.Rect(650, 320, 180, 35)
]

CONFIG_FILE = "scenario_config.json"

class Unit:
    def __init__(self, name, side, unit_type, x, y, hp=100, attack=12, armor=1.0, speed=1.8, rng=120, detect_prob=0.7):
        self.name = name
        self.side = side
        self.type = unit_type
        self.x = float(x)
        self.y = float(y)
        self.max_hp = hp
        self.hp = hp
        self.attack = attack
        self.armor = armor
        self.base_speed = speed
        self.rng = rng
        self.detect_prob = detect_prob
        self.waypoints = []
        self.alive = True
        self.target = None

    def update_movement(self, enemies):
        if not self.alive:
            return

        # 1. 현재 사거리 내에서 가장 가까운 살아있는 적 검색
        min_dist = float('inf')
        closest_enemy = None

        for e in enemies:
            if not e.alive:
                continue
            d = math.hypot(e.x - self.x, e.y - self.y)
            if d <= self.rng and d < min_dist:
                min_dist = d
                closest_enemy = e

        # 2. 타겟 선택 및 전환 로직
        if closest_enemy:
            # 이미 가장 가까운 적을 잡고 있는 경우 유지
            if self.target == closest_enemy:
                pass
            else:
                # 기존 타겟이 죽었거나 사거리를 벗어났거나, 더 가까운 적이 나타난 경우
                # 탐지 확률 판정 수행
                if random.random() < self.detect_prob:
                    self.target = closest_enemy
                elif self.target and (not self.target.alive or math.hypot(self.target.x - self.x, self.target.y - self.y) > self.rng):
                    self.target = None
        else:
            # 사거리 내에 적이 없으면 타겟 해제
            self.target = None

        # 3. 타겟이 없을 때만 웨이포인트를 따라 이동 (교전 중일 때는 이동 멈춤)
        if not self.target and self.waypoints:
            tx, ty = self.waypoints[0]
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            current_speed = self.base_speed * 1.5 if ROAD_RECT.collidepoint(self.x, self.y) else self.base_speed

            if dist < current_speed:
                self.x, self.y = tx, ty
                self.waypoints.pop(0)
            else:
                self.x += (dx / dist) * current_speed
                self.y += (dy / dist) * current_speed

    def take_damage(self, dmg, attacker=None):
        defense_factor = 1.0
        for ridge in RIDGES:
            if ridge.collidepoint(self.x, self.y):
                defense_factor *= 0.65
        if math.hypot(self.x - HILL_500_POS[0], self.y - HILL_500_POS[1]) < 40:
            defense_factor *= 0.5

        actual_dmg = (dmg / self.armor) * defense_factor * random.uniform(0.85, 1.15)
        self.hp -= actual_dmg

        # [피격 대응 로직] 공격을 받았을 때 자신이 무타겟 상태라면 공격한 적을 즉시 타겟으로 지정하여 대응/정지
        if attacker and attacker.alive and not self.target:
            d = math.hypot(attacker.x - self.x, attacker.y - self.y)
            if d <= self.rng * 1.2: # 사거리 근처면 피격 반응하여 정지 및 반격
                self.target = attacker

        if self.hp <= 0:
            self.hp = 0
            self.alive = False

    def combat_step(self):
        if self.alive and self.target and self.target.alive:
            self.target.take_damage(self.attack * 0.08, attacker=self)

class SimulationEngine:
    def __init__(self):
        self.config = self.load_config()
        self.reset('COA1')

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Config load error: {e}")
        return None

    def reload_config(self):
        new_cfg = self.load_config()
        if new_cfg:
            self.config = new_cfg
            return True
        return False

    def reset(self, coa='COA1'):
        self.coa = coa
        self.ticks = 0
        self.winner = None
        self.is_finished = False

        if not self.config:
            return

        self.red_units = []
        for u in self.config.get("RED_UNITS", []):
            armor_val = 2.0 if u.get("type") == "TANK" else 1.0
            self.red_units.append(
                Unit(u["name"], "RED", u["type"], u["x"], u["y"], 
                     hp=u["hp"], attack=u["attack"], armor=armor_val, speed=u["speed"], rng=u["rng"],
                     detect_prob=u.get("detect_prob", 0.7))
            )

        self.blue_units = []
        for u in self.config.get("BLUE_UNITS", []):
            armor_val = 2.0 if u.get("type") == "TANK" else 1.0
            self.blue_units.append(
                Unit(u["name"], "BLUE", u["type"], u["x"], u["y"], 
                     hp=u["hp"], attack=u["attack"], armor=armor_val, speed=u["speed"], rng=u["rng"],
                     detect_prob=u.get("detect_prob", 0.7))
            )

        self.apply_coa_paths()

    def apply_coa_paths(self):
        if not self.config or "WAYPOINTS" not in self.config:
            return
        
        coa_wpt = self.config["WAYPOINTS"].get(self.coa, {})
        for u in self.blue_units:
            if u.name in coa_wpt:
                u.waypoints = [list(pt) for pt in coa_wpt[u.name]]

    def step(self):
        if self.is_finished:
            return

        self.ticks += 1
        
        for u in self.blue_units:
            u.update_movement(self.red_units)
        for u in self.red_units:
            u.update_movement(self.blue_units)

        for u in self.blue_units:
            u.combat_step()
        for u in self.red_units:
            u.combat_step()

        # 승패 조건 검사
        blue_alive = any(u.alive for u in self.blue_units)
        red_alive = any(u.alive for u in self.red_units)

        # [수정] 도달 반경을 50px로 확장하고, 점령 상태 체크
        obj_captured = any(
            u.alive and math.hypot(u.x - OBJECTIVE_POS[0], u.y - OBJECTIVE_POS[1]) < 50 
            for u in self.blue_units
        )

        # 아군이 목표 지점에 도달했거나 적군이 전멸한 경우 블루팀 승리
        if obj_captured: #or (blue_alive and not red_alive):
            self.winner = 'BLUE'
            self.is_finished = True
        # 아군이 전멸하거나 제한 시간(10000 Ticks) 초과 시 레드팀 승리
        elif not blue_alive or self.ticks > 10000:
            self.winner = 'RED'
            self.is_finished = True

def run_single_coa_monte_carlo(sim, coa, num_runs=100):
    """선택된 단일 COA만을 대상으로 N회 시뮬레이션 수행 및 실시간 로그 출력"""
    blue_wins = 0
    total_ticks = 0
    total_hp_ratio = 0

    print(f"\n==========================================")
    print(f"   [{coa}] Monte Carlo Simulation Started ({num_runs} Runs)")
    print(f"==========================================")

    for i in range(1, num_runs + 1):
        sim.reset(coa)
        while not sim.is_finished:
            sim.step()
        
        # 회차별 승리 여부 및 잔여 HP 계산
        surv_hp = sum(u.hp for u in sim.blue_units if u.alive)
        max_hp = sum(u.max_hp for u in sim.blue_units)
        hp_percent = (surv_hp / max_hp * 100) if max_hp > 0 else 0

        if sim.winner == 'BLUE':
            blue_wins += 1

        total_ticks += sim.ticks
        total_hp_ratio += hp_percent

        # [실시간 로그 출력] 매 회차별 결과 및 진행률 표시
        print(f"Run #{i:03d}/{num_runs} | Winner: {sim.winner:<4} | Ticks: {sim.ticks:04d} | Surv HP: {hp_percent:5.1f}% | Current Win Rate: {(blue_wins/i)*100:5.1f}%")

    win_rate = (blue_wins / num_runs) * 100
    avg_ticks = total_ticks / num_runs
    avg_hp = total_hp_ratio / num_runs

    print(f"------------------------------------------")
    print(f" [SUMMARY] {coa} Final Win Rate: {win_rate:.1f}% | Avg Ticks: {avg_ticks:.0f} | Avg Surv HP: {avg_hp:.1f}%")
    print(f"==========================================\n")

    return win_rate, avg_ticks, avg_hp

def main():
    sim = SimulationEngine()
    current_coa = None
    batch_results = {}
    is_running_sim = False

    btn_coa1 = pygame.Rect(860, 50, 210, 35)
    btn_coa2 = pygame.Rect(860, 92, 210, 35)
    btn_coa3 = pygame.Rect(860, 134, 210, 35)
    
    btn_pause = pygame.Rect(860, 180, 210, 30)
    btn_reset = pygame.Rect(860, 215, 210, 30)
    btn_reload = pygame.Rect(860, 250, 210, 30)
    btn_batch = pygame.Rect(860, 285, 210, 35)

    running = True
    while running:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                
                if btn_coa1.collidepoint(mx, my):
                    current_coa = 'COA1'
                    sim.reset('COA1')
                    is_running_sim = True
                elif btn_coa2.collidepoint(mx, my):
                    current_coa = 'COA2'
                    sim.reset('COA2')
                    is_running_sim = True
                elif btn_coa3.collidepoint(mx, my):
                    current_coa = 'COA3'
                    sim.reset('COA3')
                    is_running_sim = True
                elif btn_pause.collidepoint(mx, my) and current_coa:
                    is_running_sim = not is_running_sim
                elif btn_reset.collidepoint(mx, my):
                    sim.reset(current_coa if current_coa else 'COA1')
                    is_running_sim = False
                elif btn_reload.collidepoint(mx, my):
                    if sim.reload_config():
                        sim.reset(current_coa if current_coa else 'COA1')
                        is_running_sim = False
                        print("Config Reloaded Successfully!")
                elif btn_batch.collidepoint(mx, my):
                    if current_coa:  # 현재 사용자가 선택한 COA가 있을 때만 실행
                        is_running_sim = False
                        # 선택된 current_coa 하나만 지정 횟수(100회)만큼 돌림
                        w_rate, a_time, a_hp = run_single_coa_monte_carlo(sim, current_coa, num_runs=100)
                        batch_results[current_coa] = (w_rate, a_time, a_hp)
                        
                        sim.reset(current_coa) # 연산 후 상태 리셋
                    else:
                        print("COA를 먼저 선택해주세요!")

        if is_running_sim and not sim.is_finished:
            sim.step()

        screen.fill(COLOR_BG)

        pygame.draw.rect(screen, COLOR_ROAD, ROAD_RECT)
        for r in RIDGES:
            pygame.draw.rect(screen, COLOR_RIDGE, r, border_radius=4)
        pygame.draw.circle(screen, COLOR_HILL, HILL_500_POS, 40)
        pygame.draw.circle(screen, COLOR_OBJ, OBJECTIVE_POS, 28)

        screen.blit(FONT_S.render("ROAD (Speed +50%)", True, COLOR_WHITE), (482, 680))
        screen.blit(FONT_S.render("Ridge Line (Cover +35%)", True, COLOR_WHITE), (140, 250))
        screen.blit(FONT_S.render("500 Hill", True, COLOR_WHITE), (590, 142))
        screen.blit(FONT_M.render("OBJ", True, COLOR_WHITE), (OBJECTIVE_POS[0]-14, OBJECTIVE_POS[1]-10))

        pygame.draw.line(screen, COLOR_BLUE, (30, 420), (810, 420), 2)

        for u in sim.blue_units + sim.red_units:
            if u.alive:
                if u.target and u.target.alive and is_running_sim:
                    line_color = (255, 50, 50) if u.side == 'BLUE' else (255, 120, 0)
                    pygame.draw.line(screen, line_color, (int(u.x), int(u.y)), (int(u.target.x), int(u.target.y)), 1)
                elif u.side == 'BLUE' and u.waypoints:
                    pts = [(u.x, u.y)] + u.waypoints
                    if len(pts) >= 2:
                        pygame.draw.lines(screen, COLOR_BLUE, False, pts, 2)

        for u in sim.blue_units + sim.red_units:
            if not u.alive:
                continue
            color = COLOR_BLUE if u.side == 'BLUE' else COLOR_RED
            radius = 12 if u.type == 'TANK' else 8

            pygame.draw.circle(screen, color, (int(u.x), int(u.y)), radius)
            pygame.draw.circle(screen, (0, 0, 0), (int(u.x), int(u.y)), radius, 2)

            hp_w = 30
            hp_ratio = u.hp / u.max_hp if u.max_hp > 0 else 0
            pygame.draw.rect(screen, (0, 0, 0), (u.x - hp_w/2, u.y - radius - 8, hp_w, 4))
            pygame.draw.rect(screen, color, (u.x - hp_w/2, u.y - radius - 8, hp_w * hp_ratio, 4))

            lbl = FONT_S.render(u.name, True, (0, 0, 0))
            screen.blit(lbl, (u.x - 20, u.y + radius + 2))

        pygame.draw.rect(screen, COLOR_PANEL, (840, 0, 260, HEIGHT))
        screen.blit(FONT_L.render("M&S Control Panel", True, COLOR_TEXT), (855, 15))

        for btn, name, c_code in [(btn_coa1, "COA 1 (Center)", 'COA1'),
                                  (btn_coa2, "COA 2 (Right)", 'COA2'),
                                  (btn_coa3, "COA 3 (Left)", 'COA3')]:
            b_color = COLOR_ACCENT if current_coa == c_code else COLOR_GRAY
            pygame.draw.rect(screen, b_color, btn, border_radius=4)
            screen.blit(FONT_M.render(name, True, (0, 0, 0)), (btn.x + 15, btn.y + 7))

        pause_txt = "Pause" if is_running_sim else "Resume / Ready"
        pygame.draw.rect(screen, COLOR_GREEN if not is_running_sim else COLOR_GRAY, btn_pause, border_radius=4)
        screen.blit(FONT_M.render(pause_txt, True, (0, 0, 0)), (btn_pause.x + 40, btn_pause.y + 5))

        pygame.draw.rect(screen, COLOR_WHITE, btn_reset, border_radius=4)
        screen.blit(FONT_M.render("Reset Simulation", True, (0, 0, 0)), (btn_reset.x + 35, btn_reset.y + 5))

        pygame.draw.rect(screen, COLOR_ACCENT, btn_reload, border_radius=4)
        screen.blit(FONT_M.render("Reload Config (JSON)", True, (0, 0, 0)), (btn_reload.x + 20, btn_reload.y + 5))

        pygame.draw.rect(screen, COLOR_OBJ, btn_batch, border_radius=4)
        screen.blit(FONT_M.render("Run 100 Sim Batch", True, COLOR_WHITE), (btn_batch.x + 25, btn_batch.y + 7))

        active_txt = current_coa if current_coa else "None (Select COA)"
        screen.blit(FONT_M.render(f"Active COA: {active_txt}", True, COLOR_TEXT), (855, 330))
        screen.blit(FONT_S.render(f"Ticks: {sim.ticks}", True, COLOR_GRAY), (855, 355))

        if sim.is_finished:
            res_color = COLOR_BLUE if sim.winner == 'BLUE' else COLOR_RED
            screen.blit(FONT_L.render(f"RESULT: {sim.winner} WIN", True, res_color), (855, 380))
        elif not is_running_sim:
            screen.blit(FONT_M.render("[ Click COA to Start ]", True, COLOR_ACCENT), (855, 380))

        pygame.draw.line(screen, COLOR_GRAY, (855, 415), (1080, 415), 1)
        screen.blit(FONT_L.render("Monte Carlo Results", True, COLOR_TEXT), (855, 425))

        if batch_results:
            y_off = 455
            for c_name, (w_rate, a_time, a_hp) in batch_results.items():
                screen.blit(FONT_M.render(f"[{c_name}]", True, COLOR_ACCENT), (855, y_off))
                screen.blit(FONT_S.render(f" Win Rate: {w_rate:.1f}%", True, COLOR_TEXT), (855, y_off + 18))
                screen.blit(FONT_S.render(f" Avg Time: {a_time:.0f}t | Surv HP: {a_hp:.1f}%", True, COLOR_GRAY), (855, y_off + 33))
                y_off += 55
        else:
            screen.blit(FONT_S.render("Click [Run 100 Sim Batch]", True, COLOR_GRAY), (855, 460))
            screen.blit(FONT_S.render("to test all COAs.", True, COLOR_GRAY), (855, 480))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()