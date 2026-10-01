"""
Getaway Chase - Basic Prototype
===============================
You're the getaway driver. Outrun, outsmart and wreck the police.

Controls:
  Left/Right or A/D  - steer
  Up or W            - accelerate
  Down or S          - brake
  Shift              - nitro (burns the nitro bar)
  U                  - open/close upgrade menu (spend cash, game pauses)
  1-5                - buy an upgrade while the menu is open
  Space              - start
  R                  - restart after game over
  ESC                - quit

Tips: oncoming traffic is in the left two lanes. Lure police into traffic
and roadblocks, ram them when they get close, and grab the cash bags.
Heat rises every 20 seconds and brings tougher police.

Everything is drawn with simple shapes, so no image files are needed.
"""

import math
import os
import random
import sys

import pygame

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
pygame.init()

WIDTH, HEIGHT = 480, 720
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Getaway Chase - Prototype")
clock = pygame.time.Clock()
FPS = 60

font_small = pygame.font.SysFont("consolas", 16)
font_msg = pygame.font.SysFont("consolas", 18, bold=True)
font_big = pygame.font.SysFont("consolas", 40, bold=True)

WHITE = (240, 240, 240)
BLACK = (15, 15, 20)
GRAY = (70, 70, 80)
RED = (220, 60, 60)
GREEN = (70, 200, 100)
YELLOW = (240, 210, 60)
BLUE = (80, 160, 240)
ORANGE = (230, 140, 50)
ASPHALT = (50, 52, 60)
GRASS = (36, 74, 48)
GRASS_LIGHT = (42, 84, 55)

ROAD_L, ROAD_R = 60, 420
LANE_W = 90
LANE_CENTERS = [ROAD_L + LANE_W // 2 + i * LANE_W for i in range(4)]
ONCOMING_LANES = (0, 1)   # left side of the road drives toward you
SAME_LANES = (2, 3)       # right side drives the same way as you

MIN_SPEED = 2.5
MAX_LEVEL = 5
SAVE_PATH = os.path.join(os.path.expanduser("~"), ".getaway_chase_best")


def clamp(value, low, high):
    return max(low, min(high, value))


def load_best():
    try:
        with open(SAVE_PATH) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_best(score):
    try:
        with open(SAVE_PATH, "w") as f:
            f.write(str(int(score)))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Drawing helper
# ---------------------------------------------------------------------------
def draw_car(surf, rect, color, facing_up=True, flash=None, flame=False, hit=False):
    # PLACEHOLDER: replace with pygame.image blits of car sprites
    if flame:
        cx = rect.centerx
        tip = rect.bottom + random.randint(14, 26)
        pygame.draw.polygon(surf, ORANGE, [(cx - 8, rect.bottom - 2), (cx + 8, rect.bottom - 2), (cx, tip)])
        pygame.draw.polygon(surf, YELLOW, [(cx - 4, rect.bottom - 2), (cx + 4, rect.bottom - 2), (cx, tip - 8)])
    body = (255, 255, 255) if hit else color
    pygame.draw.rect(surf, body, rect, border_radius=9)
    pygame.draw.rect(surf, WHITE, rect, 2, border_radius=9)

    glass = (25, 30, 45)
    wh = max(10, rect.h // 5)
    if facing_up:
        front_y = rect.y + int(rect.h * 0.17)
        rear_y = rect.bottom - int(rect.h * 0.17) - wh // 2
    else:
        front_y = rect.bottom - int(rect.h * 0.17) - wh
        rear_y = rect.y + int(rect.h * 0.17)
    pygame.draw.rect(surf, glass, (rect.x + 5, front_y, rect.w - 10, wh), border_radius=3)
    pygame.draw.rect(surf, glass, (rect.x + 6, rear_y, rect.w - 12, wh // 2), border_radius=2)

    if flash is not None:
        bar_y = rect.centery - 3
        half = (rect.w - 10) // 2
        left_c, right_c = (RED, BLUE) if flash == 0 else (BLUE, RED)
        pygame.draw.rect(surf, left_c, (rect.x + 5, bar_y, half, 6))
        pygame.draw.rect(surf, right_c, (rect.x + 5 + half, bar_y, half, 6))


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, size):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = life
        self.color = color
        self.size = size

    def update(self, scroll_speed):
        self.x += self.vx
        self.y += self.vy + scroll_speed * 0.5
        self.life -= 1

    def draw(self, surf):
        pygame.draw.rect(surf, self.color, (int(self.x), int(self.y), self.size, self.size))


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------
class Vehicle:
    def __init__(self, cx, y, w, h, color, hp):
        self.w, self.h = w, h
        self.x = cx - w / 2
        self.y = y
        self.color = color
        self.hp = hp
        self.max_hp = hp

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def cx(self):
        return self.x + self.w / 2


class Player(Vehicle):
    def __init__(self):
        super().__init__(LANE_CENTERS[3], HEIGHT - 170, 36, 62, RED, 100)
        self.v = 5.0           # forward speed (how fast the road scrolls)
        self.vx = 0.0          # sideways speed
        self.engine_level = 0
        self.handling_level = 0
        self.nitro_level = 0
        self.armor_level = 0
        self.ram_level = 0
        self.hp = self.hp_cap
        self.nitro = self.nitro_cap
        self.invincible = 0
        self.boosting = False
        self.offroad = False

    @property
    def max_speed(self):
        return 8.5 + self.engine_level * 0.7

    @property
    def steer_power(self):
        return 0.42 + self.handling_level * 0.07

    @property
    def max_lateral(self):
        return 4.2 + self.handling_level * 0.4

    @property
    def nitro_cap(self):
        return 100 + self.nitro_level * 30

    @property
    def hp_cap(self):
        return 100 + self.armor_level * 25

    @property
    def ram_damage(self):
        return 14 + self.ram_level * 8

    def update(self, keys, game):
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        up = keys[pygame.K_UP] or keys[pygame.K_w]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        nitro_key = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        steer = (1 if right else 0) - (1 if left else 0)

        self.offroad = not (ROAD_L + 6 < self.cx < ROAD_R - 6)
        self.boosting = bool(nitro_key) and self.nitro > 0 and not self.offroad

        cap = self.max_speed
        if self.offroad:
            cap = min(cap, 4.5)
        if self.boosting:
            cap += 3.5
            self.nitro = max(0.0, self.nitro - 1.1)
            self.v += 0.22
        else:
            self.nitro = min(self.nitro_cap, self.nitro + 0.12)
            if up:
                self.v += 0.07
            elif down:
                self.v -= 0.2
            else:
                self.v += clamp(5.0 - self.v, -0.03, 0.03)
        if self.v > cap:
            self.v = max(cap, self.v - 0.15)
        self.v = clamp(self.v, MIN_SPEED, 20)

        # Steering gets stronger with speed, with a bit of slide
        authority = 0.35 + min(1.0, self.v / 6.0) * 0.65
        self.vx += steer * self.steer_power * authority
        self.vx *= 0.88
        self.vx = clamp(self.vx, -self.max_lateral, self.max_lateral)
        self.x += self.vx
        if self.x < 0:
            self.x, self.vx = 0, 0
        elif self.x > WIDTH - self.w:
            self.x, self.vx = WIDTH - self.w, 0

        if self.invincible > 0:
            self.invincible -= 1

        if self.offroad and self.v > 3:
            game.shake = max(game.shake, 2)
            if random.random() < 0.5:
                game.emit(self.cx, self.y + self.h, (110, 90, 60), n=1, speed=1.5, life=20)
        if self.boosting and random.random() < 0.6:
            game.emit(self.cx, self.y + self.h, ORANGE, n=1, speed=1.2, life=14)
        if self.hp < self.hp_cap * 0.35 and random.random() < 0.25:
            game.emit(self.cx, self.y + 10, (90, 90, 95), n=1, speed=1.0, life=30, size=5)

    def draw(self, surf, frame):
        flicker = self.invincible > 0 and (frame // 3) % 2 == 0
        draw_car(surf, self.rect, self.color, facing_up=True, flame=self.boosting, hit=flicker)


class Traffic(Vehicle):
    COLORS = [(190, 190, 70), (70, 160, 120), (150, 110, 190), (200, 130, 70), (120, 150, 200), (170, 170, 175)]

    def __init__(self):
        lane = random.randrange(4)
        self.oncoming = lane in ONCOMING_LANES
        self.speed = random.uniform(4.0, 6.0) if self.oncoming else random.uniform(3.0, 5.0)
        super().__init__(LANE_CENTERS[lane], -80, 38, 64, random.choice(self.COLORS), 1)

    def update(self, v):
        self.y += (v + self.speed) if self.oncoming else (v - self.speed)

    def gone(self):
        return self.y > HEIGHT + 120 or self.y < -400

    def draw(self, surf):
        draw_car(surf, self.rect, self.color, facing_up=not self.oncoming)


POLICE_TYPES = {
    "cruiser": dict(w=38, h=64, hp=45, top=8.4, accel=0.05, lat=2.4, dmg=9,
                    cash=30, score=100, color=(40, 60, 130)),
    "interceptor": dict(w=36, h=62, hp=35, top=9.6, accel=0.07, lat=3.3, dmg=11,
                        cash=45, score=150, color=(25, 25, 35)),
    "swat": dict(w=46, h=78, hp=130, top=7.6, accel=0.04, lat=1.7, dmg=20,
                 cash=90, score=300, color=(60, 66, 76)),
}


def pick_police_type(heat):
    options = [("cruiser", 10)]
    if heat >= 2:
        options.append(("interceptor", 4 + heat * 2))
    if heat >= 3:
        options.append(("swat", 2 + heat))
    kinds, weights = zip(*options)
    return random.choices(kinds, weights=weights, k=1)[0]


class Police(Vehicle):
    def __init__(self, kind, heat, v):
        cfg = POLICE_TYPES[kind]
        lane = random.choice(SAME_LANES)
        super().__init__(LANE_CENTERS[lane], HEIGHT + 90, cfg["w"], cfg["h"], cfg["color"], cfg["hp"])
        self.kind = kind
        self.cfg = cfg
        self.top = cfg["top"] + 0.12 * heat
        self.speed = v
        self.ram_cd = 0

    def update(self, v, player):
        gap = self.y - (player.y + 30)
        if gap > 25:
            target = self.top               # behind: floor it
        elif gap < -25:
            target = max(2.0, v - 2.0)      # got ahead: ease off
        else:
            target = v + 0.4                # tailgate and ram
        self.speed += clamp(target - self.speed, -0.15, self.cfg["accel"])
        self.y += v - self.speed

        dx = player.cx - self.cx
        lat = self.cfg["lat"]
        self.x += clamp(dx * 0.06, -lat, lat)
        self.x = clamp(self.x, ROAD_L, ROAD_R - self.w)
        if self.ram_cd > 0:
            self.ram_cd -= 1

    def escaped(self):
        return self.y > HEIGHT + 260

    def draw(self, surf, frame):
        draw_car(surf, self.rect, self.color, facing_up=True, flash=(frame // 8) % 2)
        pct = clamp(self.hp / self.max_hp, 0, 1)
        pygame.draw.rect(surf, BLACK, (self.x, self.y - 8, self.w, 4))
        pygame.draw.rect(surf, RED, (self.x, self.y - 8, self.w * pct, 4))


# ---------------------------------------------------------------------------
# Road objects
# ---------------------------------------------------------------------------
class Barrier:
    """One half of a roadblock. Two of them leave a gap to squeeze through."""
    def __init__(self, x, w):
        self.x, self.w = x, w
        self.y = -40
        self.h = 26

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), int(self.w), self.h)

    def update(self, v):
        self.y += v

    def gone(self):
        return self.y > HEIGHT + 40

    def draw(self, surf):
        r = self.rect
        pygame.draw.rect(surf, WHITE, r)
        for sx in range(0, r.w, 24):
            pygame.draw.rect(surf, RED, (r.x + sx, r.y, min(12, r.w - sx), r.h))
        pygame.draw.rect(surf, BLACK, r, 2)


class Cash:
    def __init__(self):
        self.size = 22
        self.x = random.randint(ROAD_L + 10, ROAD_R - 10 - self.size)
        self.y = -self.size
        self.value = 10

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    def update(self, v):
        self.y += v

    def gone(self):
        return self.y > HEIGHT + 20

    def draw(self, surf):
        # PLACEHOLDER: replace with a money bag sprite
        pygame.draw.rect(surf, GREEN, self.rect, border_radius=5)
        pygame.draw.rect(surf, BLACK, self.rect, 2, border_radius=5)
        txt = font_small.render("$", True, BLACK)
        surf.blit(txt, (self.x + self.size // 2 - txt.get_width() // 2,
                        self.y + self.size // 2 - txt.get_height() // 2))


# ---------------------------------------------------------------------------
# Upgrades
# ---------------------------------------------------------------------------
UPGRADES = [
    {"key": "engine", "label": "Engine", "desc": "Higher top speed", "cost_base": 40},
    {"key": "handling", "label": "Handling", "desc": "Sharper steering", "cost_base": 40},
    {"key": "nitro", "label": "Nitro Tank", "desc": "Bigger nitro bar", "cost_base": 50},
    {"key": "armor", "label": "Armor", "desc": "More health", "cost_base": 50},
    {"key": "ram", "label": "Ram Plating", "desc": "Ram harder, take less damage", "cost_base": 60},
]

UPGRADE_KEYS = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5]


def upgrade_cost(level, base):
    return base * (level + 1)


def buy_upgrade(game, key):
    """Returns (status, message) where status is 'ok', 'max' or 'poor'."""
    player = game.player
    attr = f"{key}_level"
    cfg = next(u for u in UPGRADES if u["key"] == key)
    level = getattr(player, attr)

    if level >= MAX_LEVEL:
        return "max", f"{cfg['label']} is already maxed out!"
    cost = upgrade_cost(level, cfg["cost_base"])
    if game.cash < cost:
        return "poor", f"Need ${cost - game.cash} more for {cfg['label']}."

    game.cash -= cost
    setattr(player, attr, level + 1)
    if key == "armor":
        player.hp = min(player.hp_cap, player.hp + 25)
    if key == "nitro":
        player.nitro = player.nitro_cap
    return "ok", f"{cfg['label']} upgraded to Lv {level + 1}!"


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
HEAT_MESSAGES = {
    2: "HEAT 2: interceptors joined the chase!",
    3: "HEAT 3: SWAT vans incoming!",
    4: "HEAT 4: they're throwing everything at you!",
    5: "HEAT 5: maximum heat. Good luck.",
}


class Game:
    def __init__(self):
        self.world = pygame.Surface((WIDTH, HEIGHT))
        self.best = load_best()
        self.started = False
        self.reset()

    def reset(self):
        self.player = Player()
        self.police, self.traffic, self.barriers = [], [], []
        self.cash_items, self.particles = [], []
        self.traffic_timer = 30
        self.cash_timer = 90
        self.police_timer = 240
        self.barrier_timer = 700
        self.frame = 0
        self.scroll = 0.0
        self.distance = 0.0
        self.takedowns = 0
        self.cash = 0
        self.bonus_score = 0
        self.shake = 0
        self.paused_for_upgrade = False
        self.game_over = False
        self.new_best = False
        self.message = ""
        self.message_timer = 0
        self.message_color = WHITE
        self.seen_police = False

    @property
    def heat(self):
        return 1 + min(4, self.frame // 1200)

    @property
    def score(self):
        return int(self.distance) + self.bonus_score

    def say(self, text, color=WHITE, frames=120):
        self.message = text
        self.message_color = color
        self.message_timer = frames

    def emit(self, x, y, color, n=8, speed=3.0, life=24, size=4):
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, math.cos(ang) * spd, math.sin(ang) * spd,
                                           random.randint(max(2, life // 2), life), color,
                                           random.randint(2, size)))

    def explode(self, x, y):
        self.emit(x, y, ORANGE, n=14, speed=4)
        self.emit(x, y, YELLOW, n=8, speed=3)
        self.emit(x, y, (90, 90, 95), n=8, speed=2, life=40, size=6)

    def buy(self, key):
        status, msg = buy_upgrade(self, key)
        self.say(msg, GREEN if status == "ok" else (YELLOW if status == "poor" else RED), 100)

    # -- spawning ----------------------------------------------------------
    def spawn(self):
        heat = self.heat
        v = self.player.v

        self.traffic_timer -= 1
        if self.traffic_timer <= 0:
            self.traffic_timer = random.randint(35, 70)
            t = Traffic()
            probe = t.rect.inflate(10, 170)
            if not any(probe.colliderect(o.rect) for o in self.traffic):
                self.traffic.append(t)

        self.cash_timer -= 1
        if self.cash_timer <= 0:
            self.cash_timer = random.randint(100, 170)
            self.cash_items.append(Cash())

        self.police_timer -= 1
        if self.police_timer <= 0:
            self.police_timer = max(150, 460 - heat * 60) + random.randint(0, 60)
            if len(self.police) < 1 + heat:
                kind = pick_police_type(heat)
                cop = Police(kind, heat, v)
                probe = cop.rect.inflate(20, 40)
                if not any(probe.colliderect(o.rect) for o in self.police):
                    self.police.append(cop)
                    if not self.seen_police:
                        self.seen_police = True
                        self.say("Police on your tail! Keep moving.", YELLOW, 150)

        self.barrier_timer -= 1
        if self.barrier_timer <= 0:
            self.barrier_timer = max(420, 1000 - heat * 120)
            gap_w = 130
            gap_x = random.randint(ROAD_L + 10, ROAD_R - gap_w - 10)
            self.barriers.append(Barrier(ROAD_L, gap_x - ROAD_L))
            self.barriers.append(Barrier(gap_x + gap_w, ROAD_R - (gap_x + gap_w)))
            self.say("ROADBLOCK AHEAD!", RED, 90)

    # -- update ------------------------------------------------------------
    def update(self, keys):
        if self.message_timer > 0:
            self.message_timer -= 1
        if self.shake > 0:
            self.shake -= 1

        if not self.started or self.game_over or self.paused_for_upgrade:
            return

        self.frame += 1
        if self.frame % 1200 == 0 and self.heat in HEAT_MESSAGES:
            self.say(HEAT_MESSAGES[self.heat], ORANGE, 160)

        p = self.player
        p.update(keys, self)
        v = p.v
        self.scroll = (self.scroll + v) % 200
        self.distance += v * 0.1

        self.spawn()

        for t in self.traffic:
            t.update(v)
        for c in self.police:
            c.update(v, p)
        for b in self.barriers:
            b.update(v)
        for c in self.cash_items:
            c.update(v)
        for part in self.particles:
            part.update(v)

        self._handle_collisions()

        self.traffic = [t for t in self.traffic if not t.gone()]
        self.barriers = [b for b in self.barriers if not b.gone()]
        self.cash_items = [c for c in self.cash_items if not c.gone()]
        self.particles = [q for q in self.particles if q.life > 0]
        for c in self.police:
            if c.escaped():
                self.bonus_score += 25
                self.say("Lost one! +25", GREEN, 80)
        self.police = [c for c in self.police if not c.escaped()]

        if p.hp <= 0:
            self.explode(p.cx, p.y + p.h / 2)
            self.game_over = True
            self.shake = 20
            if self.score > self.best:
                self.best = self.score
                self.new_best = True
                save_best(self.best)

    def player_hit(self, dmg, slow=1.0):
        p = self.player
        if p.invincible > 0:
            return False
        p.hp -= dmg
        p.invincible = 30
        p.v = max(MIN_SPEED, p.v * slow)
        self.shake = 10
        return True

    def _handle_collisions(self):
        p = self.player
        pr = p.rect

        # Player vs traffic
        for t in self.traffic[:]:
            if t.rect.colliderect(pr):
                dmg = 8 + p.v * 1.3 + (8 if t.oncoming else 0)
                self.player_hit(dmg, 0.5 if t.oncoming else 0.7)
                self.explode(t.cx, t.y + t.h / 2)
                self.traffic.remove(t)

        # Player vs roadblock
        for b in self.barriers[:]:
            if b.rect.colliderect(pr):
                self.player_hit(22, 0.45)
                self.emit(p.cx, p.y, WHITE, n=10, speed=4)
                self.barriers.remove(b)

        # Player vs cash
        for c in self.cash_items[:]:
            if c.rect.colliderect(pr):
                self.cash += c.value
                self.cash_items.remove(c)

        # Police interactions
        for cop in self.police[:]:
            cr = cop.rect
            if cr.colliderect(pr):
                if cop.ram_cd <= 0:
                    cop.ram_cd = 40
                    self.player_hit(max(3, cop.cfg["dmg"] - p.ram_level), 0.92)
                    cop.hp -= p.ram_damage * (0.7 + p.v / 12)
                    direction = 1 if cop.cx > p.cx else -1
                    cop.x = clamp(cop.x + direction * 16, ROAD_L, ROAD_R - cop.w)
                    p.vx -= direction * 3
                    self.emit((cop.cx + p.cx) / 2, (cop.y + p.y) / 2 + 20, YELLOW, n=8, speed=4)
            for t in self.traffic[:]:
                if t.rect.colliderect(cr):
                    cop.hp -= 25
                    cop.speed *= 0.7
                    self.explode(t.cx, t.y + t.h / 2)
                    self.traffic.remove(t)
            for b in self.barriers[:]:
                if b.rect.colliderect(cr):
                    cop.hp -= 45
                    cop.speed *= 0.4
                    self.emit(cop.cx, cop.y, WHITE, n=10, speed=4)
                    self.barriers.remove(b)

        # Keep police from stacking on top of each other
        for i, a in enumerate(self.police):
            for b in self.police[i + 1:]:
                if a.rect.colliderect(b.rect):
                    push = 1.2 if a.cx < b.cx else -1.2
                    a.x = clamp(a.x - push, ROAD_L, ROAD_R - a.w)
                    b.x = clamp(b.x + push, ROAD_L, ROAD_R - b.w)

        # Wrecked police
        for cop in self.police[:]:
            if cop.hp <= 0:
                self.explode(cop.cx, cop.y + cop.h / 2)
                self.takedowns += 1
                self.cash += cop.cfg["cash"]
                self.bonus_score += cop.cfg["score"]
                self.say(f"TAKEDOWN! +${cop.cfg['cash']}", GREEN, 90)
                self.police.remove(cop)

    # -- drawing -----------------------------------------------------------
    def draw_road(self, w):
        w.fill(GRASS)
        for i in range(-1, 5):
            y = int(i * 200 + self.scroll)
            pygame.draw.rect(w, GRASS_LIGHT, (0, y, WIDTH, 100))
        pygame.draw.rect(w, ASPHALT, (ROAD_L, 0, ROAD_R - ROAD_L, HEIGHT))
        pygame.draw.rect(w, WHITE, (ROAD_L + 3, 0, 4, HEIGHT))
        pygame.draw.rect(w, WHITE, (ROAD_R - 7, 0, 4, HEIGHT))
        offset = int(self.scroll % 40)
        for k in (1, 3):
            x = ROAD_L + k * LANE_W
            for y in range(-40, HEIGHT + 40, 40):
                pygame.draw.rect(w, (200, 200, 205), (x - 2, y + offset, 4, 22))
        mid = ROAD_L + 2 * LANE_W
        pygame.draw.rect(w, YELLOW, (mid - 5, 0, 3, HEIGHT))
        pygame.draw.rect(w, YELLOW, (mid + 2, 0, 3, HEIGHT))

    def draw(self, surf):
        w = self.world
        self.draw_road(w)
        for c in self.cash_items:
            c.draw(w)
        for b in self.barriers:
            b.draw(w)
        for t in self.traffic:
            t.draw(w)
        for c in self.police:
            c.draw(w, self.frame)
        if not self.game_over:
            self.player.draw(w, self.frame)
        for part in self.particles:
            part.draw(w)

        ox = oy = 0
        if self.shake > 0:
            s = min(self.shake, 8)
            ox, oy = random.randint(-s, s) // 2, random.randint(-s, s) // 2
        surf.fill(BLACK)
        surf.blit(w, (ox, oy))

        self.draw_hud(surf)
        if not self.started:
            self.draw_title(surf)
        if self.paused_for_upgrade:
            self.draw_upgrade_menu(surf)
        if self.game_over:
            self.draw_game_over(surf)

    def draw_hud(self, surf):
        p = self.player
        pygame.draw.rect(surf, BLACK, (10, 10, 150, 16))
        pygame.draw.rect(surf, GREEN, (10, 10, 150 * clamp(p.hp / p.hp_cap, 0, 1), 16))
        pygame.draw.rect(surf, WHITE, (10, 10, 150, 16), 2)
        pygame.draw.rect(surf, BLACK, (10, 30, 150, 10))
        pygame.draw.rect(surf, BLUE, (10, 30, 150 * clamp(p.nitro / p.nitro_cap, 0, 1), 10))
        pygame.draw.rect(surf, WHITE, (10, 30, 150, 10), 2)

        surf.blit(font_small.render(f"Score: {self.score}", True, WHITE), (10, 46))
        surf.blit(font_small.render(f"Cash: ${self.cash}", True, GREEN), (10, 66))

        hint = font_small.render("U: Upgrades", True, WHITE)
        surf.blit(hint, (WIDTH - hint.get_width() - 10, 12))
        heat_lbl = font_small.render("HEAT", True, WHITE)
        surf.blit(heat_lbl, (WIDTH - 130 - heat_lbl.get_width() + 38, 34))
        for i in range(5):
            col = RED if i < self.heat else GRAY
            pygame.draw.rect(surf, col, (WIDTH - 100 + i * 18, 36, 14, 12))
        kmh = font_small.render(f"{int(p.v * 16)} km/h", True, YELLOW if p.boosting else WHITE)
        surf.blit(kmh, (WIDTH - kmh.get_width() - 10, 56))
        best = font_small.render(f"Best: {self.best}", True, WHITE)
        surf.blit(best, (WIDTH - best.get_width() - 10, 76))

        if not self.paused_for_upgrade and self.message_timer > 0:
            m = font_msg.render(self.message, True, self.message_color)
            shadow = font_msg.render(self.message, True, BLACK)
            pos = (WIDTH // 2 - m.get_width() // 2, 110)
            surf.blit(shadow, (pos[0] + 2, pos[1] + 2))
            surf.blit(m, pos)

    def draw_title(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surf.blit(overlay, (0, 0))
        title = font_big.render("GETAWAY CHASE", True, YELLOW)
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 170))
        lines = [
            "Steer: arrows or A/D",
            "Gas / brake: up and down (W/S)",
            "Nitro: Shift",
            "Upgrades: U, then 1-5",
            "",
            "Oncoming traffic is in the left lanes.",
            "Ram police, dodge roadblocks.",
            "",
            "Press SPACE to start",
        ]
        for i, line in enumerate(lines):
            txt = font_small.render(line, True, WHITE)
            surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 250 + i * 26))

    def draw_upgrade_menu(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surf.blit(overlay, (0, 0))

        title = font_big.render("GARAGE", True, WHITE)
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 26))
        cash = font_small.render(f"Cash: ${self.cash}", True, GREEN)
        surf.blit(cash, (WIDTH // 2 - cash.get_width() // 2, 76))

        row_h, start_y = 72, 112
        for i, u in enumerate(UPGRADES):
            level = getattr(self.player, f"{u['key']}_level")
            y = start_y + i * row_h
            box = pygame.Rect(40, y, WIDTH - 80, 62)
            maxed = level >= MAX_LEVEL
            pygame.draw.rect(surf, (50, 60, 45) if maxed else (40, 44, 56), box, border_radius=8)
            pygame.draw.rect(surf, WHITE, box, 2, border_radius=8)
            cost = "MAX" if maxed else f"${upgrade_cost(level, u['cost_base'])}"
            label = font_small.render(f"{i + 1}. {u['label']}  (Lv {level}/{MAX_LEVEL})  -  {cost}", True, WHITE)
            desc = font_small.render(u["desc"], True, (150, 155, 170))
            surf.blit(label, (box.x + 10, box.y + 10))
            surf.blit(desc, (box.x + 10, box.y + 34))

        end_y = start_y + len(UPGRADES) * row_h
        if self.message_timer > 0:
            m = font_small.render(self.message, True, self.message_color)
            surf.blit(m, (WIDTH // 2 - m.get_width() // 2, end_y + 6))
        hint = font_small.render("Press 1-5 to buy, U to close", True, (150, 155, 170))
        surf.blit(hint, (WIDTH // 2 - hint.get_width() // 2, end_y + 32))

    def draw_game_over(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surf.blit(overlay, (0, 0))
        title = font_big.render("WRECKED", True, RED)
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 90))
        lines = [
            (f"Final Score: {self.score}", WHITE),
            (f"Takedowns: {self.takedowns}", WHITE),
            ("New best score!" if self.new_best else f"Best: {self.best}", YELLOW if self.new_best else WHITE),
            ("Press R to restart", (150, 155, 170)),
        ]
        for i, (line, col) in enumerate(lines):
            txt = font_small.render(line, True, col)
            surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 20 + i * 30))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    game = Game()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE and not game.started:
                    game.started = True
                elif event.key == pygame.K_u and game.started and not game.game_over:
                    game.paused_for_upgrade = not game.paused_for_upgrade
                elif event.key == pygame.K_r and game.game_over:
                    game.reset()
                elif game.paused_for_upgrade and event.key in UPGRADE_KEYS:
                    idx = UPGRADE_KEYS.index(event.key)
                    if idx < len(UPGRADES):
                        game.buy(UPGRADES[idx]["key"])

        keys = pygame.key.get_pressed()
        game.update(keys)
        game.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
