"""
Getaway Chase - Prototype v2
============================
You're the getaway driver. Outrun, outsmart and wreck the police.

Controls:
  Left/Right or A/D  - steer
  Up or W            - accelerate
  Down or S          - brake
  Shift              - nitro (burns the nitro bar)
  U                  - open/close the garage (spend cash, game pauses)
  1-6                - buy an upgrade while the garage is open
  Space              - start
  R                  - restart after game over
  ESC                - quit

The route changes as you drive:
  Highway   - wide, fast, gentle bends
  Downtown  - narrow streets with intersections and cross traffic
  Canyon    - winding road that you have to steer along

Tips: oncoming traffic is always on the left side of the road. Lure police
into traffic, cross traffic and roadblocks, ram them when they get close, and
grab the cash bags. Hold the gas (and use nitro) to pull away from them.

Everything is drawn with simple shapes, so no image files are needed.
"""

import bisect
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

MIN_SPEED = 2.5
MAX_LEVEL = 5
STEP = 6            # road is drawn in horizontal bands this tall
IH = 130            # height of an intersection
CH = 120            # scenery chunk size
SAVE_PATH = os.path.join(os.path.expanduser("~"), ".getaway_chase_best")

# Lane positions as a fraction of road width (negative = oncoming side)
LANE_FRACS = {4: [-0.375, -0.125, 0.125, 0.375], 2: [-0.25, 0.25]}
SAME_FRACS = {4: [0.125, 0.375], 2: [0.25]}


def clamp(value, low, high):
    return max(low, min(high, value))


def hrand(i, side, k):
    """Deterministic pseudo-random 0..1 so scenery never flickers."""
    h = (i * 73856093) ^ ((side + 3) * 19349663) ^ (k * 83492791)
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFF) / 65535.0


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
# The route: a chain of road sections with different looks and shapes
# ---------------------------------------------------------------------------
THEMES = {
    "grass": dict(side=(36, 74, 48), side2=(42, 84, 55), road=(50, 52, 60), edge=(WHITE, 4)),
    "city": dict(side=(52, 54, 62), side2=(57, 59, 68), road=(44, 46, 54), edge=((120, 122, 134), 8)),
    "sand": dict(side=(150, 112, 68), side2=(160, 122, 76), road=(70, 66, 66), edge=(WHITE, 4)),
}

KINDS = {
    "highway": dict(name="Highway", width=360, lanes=4, theme="grass",
                    amp=(0, 45), waves=(1, 2), length=(2000, 3000)),
    "downtown": dict(name="Downtown", width=230, lanes=2, theme="city",
                     amp=(0, 0), waves=(1, 1), length=(2400, 3200)),
    "canyon": dict(name="Canyon Road", width=290, lanes=2, theme="sand",
                   amp=(55, 75), waves=(2, 3), length=(2200, 3000)),
}

ZONE_MESSAGES = {
    "highway": "HIGHWAY: open road, open throttle.",
    "downtown": "DOWNTOWN: watch the intersections!",
    "canyon": "CANYON ROAD: it twists, so steer.",
}


class Section:
    def __init__(self, start, kind, prev_width, first=False):
        cfg = KINDS[kind]
        self.kind = kind
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.name = cfg["name"]
        self.start = start
        self.length = 2600 if first else random.randint(*cfg["length"])
        self.end = start + self.length
        self.width = cfg["width"]
        self.lanes = cfg["lanes"]
        self.prev_width = prev_width
        self.taper = 260
        self.amp = 0 if first else random.uniform(*cfg["amp"]) * random.choice((-1, 1))
        self.waves = random.randint(*cfg["waves"])
        self.intersections = []
        if kind == "downtown":
            d = start + 700
            while d < self.end - 500:
                self.intersections.append(d)
                d += random.randint(800, 1100)

    def center(self, D):
        if self.amp == 0:
            return WIDTH / 2
        t = clamp((D - self.start) / self.length, 0, 1)
        return WIDTH / 2 + self.amp * math.sin(2 * math.pi * self.waves * t) * math.sin(math.pi * t)

    def width_at(self, D):
        if self.prev_width is None:
            return self.width
        local = D - self.start
        if local >= self.taper:
            return self.width
        u = clamp(local / self.taper, 0, 1)
        u = u * u * (3 - 2 * u)
        return self.prev_width + (self.width - self.prev_width) * u


class Track:
    """Endless chain of sections. D is distance along the route in pixels."""
    def __init__(self):
        self.sections = []
        self.starts = []
        self._add(Section(-600, "highway", None, first=True))

    def _add(self, section):
        self.sections.append(section)
        self.starts.append(section.start)

    def ensure(self, D):
        while self.sections[-1].end < D:
            last = self.sections[-1]
            kinds = [k for k in KINDS if k != last.kind]
            self._add(Section(last.end, random.choice(kinds), last.width))

    def index_at(self, D):
        self.ensure(D + 1)
        return max(0, bisect.bisect_right(self.starts, D) - 1)

    def section_at(self, D):
        return self.sections[self.index_at(D)]


# ---------------------------------------------------------------------------
# Drawing helpers
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


def draw_car_h(surf, rect, color, facing_right=True):
    """A car seen driving sideways (used for cross traffic)."""
    pygame.draw.rect(surf, color, rect, border_radius=9)
    pygame.draw.rect(surf, WHITE, rect, 2, border_radius=9)
    glass = (25, 30, 45)
    ww = max(10, rect.w // 5)
    if facing_right:
        front_x = rect.right - int(rect.w * 0.17) - ww
        rear_x = rect.x + int(rect.w * 0.17)
    else:
        front_x = rect.x + int(rect.w * 0.17)
        rear_x = rect.right - int(rect.w * 0.17) - ww // 2
    pygame.draw.rect(surf, glass, (front_x, rect.y + 5, ww, rect.h - 10), border_radius=3)
    pygame.draw.rect(surf, glass, (rear_x, rect.y + 6, ww // 2, rect.h - 12), border_radius=2)


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
        super().__init__(WIDTH / 2 + 90, HEIGHT - 170, 36, 62, RED, 100)
        self.v = 6.5           # forward speed (how fast the road scrolls)
        self.vx = 0.0          # sideways speed
        self.engine_level = 0
        self.handling_level = 0
        self.nitro_level = 0
        self.armor_level = 0
        self.ram_level = 0
        self.regen_level = 0
        self.hp = self.hp_cap
        self.nitro = self.nitro_cap
        self.invincible = 0
        self.since_hit = 999
        self.boosting = False
        self.offroad = False

    @property
    def max_speed(self):
        return 9.0 + self.engine_level * 0.7

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

    @property
    def regen_rate(self):
        """Health restored per frame once you've avoided damage for a bit."""
        return self.regen_level * 0.01

    @property
    def regenerating(self):
        return self.regen_level > 0 and self.since_hit > 120 and self.hp < self.hp_cap

    def update(self, keys, game):
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        up = keys[pygame.K_UP] or keys[pygame.K_w]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        nitro_key = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        steer = (1 if right else 0) - (1 if left else 0)

        lo, hi = game.bounds(self.y + self.h / 2)
        self.offroad = not (lo + 6 < self.cx < hi - 6)
        self.boosting = bool(nitro_key) and self.nitro > 0 and not self.offroad

        cap = self.max_speed
        if self.offroad:
            cap = min(cap, 4.5)
        if self.boosting:
            cap += 3.5
            self.nitro = max(0.0, self.nitro - 0.9)
            self.v += 0.25
        else:
            self.nitro = min(self.nitro_cap, self.nitro + 0.15)
            if up:
                self.v += 0.09
            elif down:
                self.v -= 0.2
            else:
                self.v += clamp(6.5 - self.v, -0.01, 0.03)
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
        self.since_hit += 1
        if self.regenerating:
            self.hp = min(self.hp_cap, self.hp + self.regen_rate)

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

    def __init__(self, game):
        c, wd, s, _ = game.road(-40)
        self.frac = random.choice(LANE_FRACS[s.lanes])
        self.oncoming = self.frac < 0
        self.speed = random.uniform(4.0, 6.0) if self.oncoming else random.uniform(3.0, 5.0)
        super().__init__(c + self.frac * wd, -80, 38, 64, random.choice(self.COLORS), 1)

    def update(self, v, game):
        self.y += (v + self.speed) if self.oncoming else (v - self.speed)
        c, wd, _, _ = game.road(self.y + self.h / 2)
        self.x = c + self.frac * wd - self.w / 2

    def gone(self):
        return self.y > HEIGHT + 120 or self.y < -400

    def draw(self, surf):
        draw_car(surf, self.rect, self.color, facing_up=not self.oncoming)


class CrossCar(Vehicle):
    """Drives across an intersection. Fixed to the road, so it scrolls with it."""
    def __init__(self, D, direction):
        self.D = D
        self.dir = direction
        self.speed = random.uniform(4.5, 7.0)
        start_x = -40 if direction > 0 else WIDTH + 40
        super().__init__(start_x, 0, 64, 38, random.choice(Traffic.COLORS), 1)

    def update(self, game):
        self.x += self.dir * self.speed
        self.y = game.dist + HEIGHT - self.D - self.h / 2

    def gone(self):
        return self.x < -140 or self.x > WIDTH + 140 or self.y > HEIGHT + 100

    def draw(self, surf):
        draw_car_h(surf, self.rect, self.color, facing_right=self.dir > 0)


POLICE_TYPES = {
    "cruiser": dict(w=38, h=64, hp=45, top=7.6, accel=0.05, lat=2.4, dmg=9,
                    cash=30, score=100, color=(40, 60, 130)),
    "interceptor": dict(w=36, h=62, hp=35, top=8.6, accel=0.07, lat=3.3, dmg=11,
                        cash=45, score=150, color=(25, 25, 35)),
    "swat": dict(w=46, h=78, hp=130, top=6.8, accel=0.04, lat=1.7, dmg=20,
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
    def __init__(self, kind, heat, v, game):
        cfg = POLICE_TYPES[kind]
        y = HEIGHT + 90
        c, wd, s, _ = game.road(y + cfg["h"] / 2)
        frac = random.choice(SAME_FRACS[s.lanes])
        super().__init__(c + frac * wd, y, cfg["w"], cfg["h"], cfg["color"], cfg["hp"])
        self.kind = kind
        self.cfg = cfg
        self.top = cfg["top"] + 0.08 * heat
        self.speed = min(v, self.top)
        self.ram_cd = 0

    def update(self, v, player, game):
        gap = self.y - (player.y + 30)
        if gap > 25:
            target = self.top                       # behind: floor it
        elif gap < -25:
            target = max(2.0, v - 2.0)              # got ahead: ease off
        else:
            target = min(v + 0.4, self.top)         # tailgate, but never beyond top speed
        self.speed += clamp(target - self.speed, -0.15, self.cfg["accel"])
        self.speed = min(self.speed, self.top)
        self.y += v - self.speed

        dx = player.cx - self.cx
        lat = self.cfg["lat"]
        self.x += clamp(dx * 0.06, -lat, lat)
        lo, hi = game.bounds(self.y + self.h / 2)
        self.x = clamp(self.x, lo, hi - self.w)
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
class Roadblock:
    """Two barriers with a gap between them. Follows the curve of the road."""
    H = 26

    def __init__(self, gap_frac, gap_w):
        self.y = -40
        self.gap_frac = gap_frac
        self.gap_w = gap_w
        self.alive = [True, True]
        self.segs = []

    def update(self, v, game):
        self.y += v
        c, wd, _, _ = game.road(self.y + self.H / 2)
        left, right = c - wd / 2, c + wd / 2
        gx = c + self.gap_frac * wd - self.gap_w / 2
        self.segs = [
            pygame.Rect(int(left), int(self.y), max(0, int(gx - left)), self.H),
            pygame.Rect(int(gx + self.gap_w), int(self.y), max(0, int(right - (gx + self.gap_w))), self.H),
        ]

    def live(self):
        return [(i, r) for i, r in enumerate(self.segs) if self.alive[i] and r.w > 0]

    def gone(self):
        return self.y > HEIGHT + 40 or not any(self.alive)

    def draw(self, surf):
        for _, r in self.live():
            pygame.draw.rect(surf, WHITE, r)
            for sx in range(0, r.w, 24):
                pygame.draw.rect(surf, RED, (r.x + sx, r.y, min(12, r.w - sx), r.h))
            pygame.draw.rect(surf, BLACK, r, 2)


class Cash:
    def __init__(self, game):
        self.size = 22
        self.frac = random.uniform(-0.4, 0.4)
        self.y = -self.size
        self.value = 10
        self.x = 0
        self._place(game)

    def _place(self, game):
        c, wd, _, _ = game.road(self.y + self.size / 2)
        self.x = c + self.frac * wd - self.size / 2

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    def update(self, v, game):
        self.y += v
        self._place(game)

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
    {"key": "regen", "label": "Regen", "desc": "Repair health when you stay clean", "cost_base": 50},
]

UPGRADE_KEYS = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6]


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
        self.track = Track()
        self.player = Player()
        self.police, self.traffic, self.barriers = [], [], []
        self.cash_items, self.particles, self.cross = [], [], []
        self.traffic_timer = 30
        self.cash_timer = 90
        self.police_timer = 240
        self.barrier_timer = 700
        self.cross_timer = 40
        self.frame = 0
        self.dist = 0.0         # how far the route has scrolled (pixels)
        self.distance = 0.0     # score distance
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
        self.cur_section = self.track.section_at(self.dist + HEIGHT - self.player.y)

    # -- route queries ------------------------------------------------------
    def road(self, y):
        """(center, width, section, in_intersection) of the road at screen row y."""
        D = self.dist + HEIGHT - y
        s = self.track.section_at(D)
        inter = any(a <= D <= a + IH for a in s.intersections)
        return s.center(D), s.width_at(D), s, inter

    def bounds(self, y):
        """Left and right edge cars can drive between (whole screen at intersections)."""
        c, wd, _, inter = self.road(y)
        if inter:
            return 0, WIDTH
        return c - wd / 2, c + wd / 2

    def visible_intersections(self):
        out = []
        i0 = self.track.index_at(self.dist - IH)
        i1 = self.track.index_at(self.dist + HEIGHT + IH)
        for s in self.track.sections[i0:i1 + 1]:
            for a in s.intersections:
                if a + IH > self.dist and a < self.dist + HEIGHT - 40:
                    out.append(a)
        return out

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
            t = Traffic(self)
            probe = t.rect.inflate(10, 170)
            if not any(probe.colliderect(o.rect) for o in self.traffic):
                self.traffic.append(t)

        self.cash_timer -= 1
        if self.cash_timer <= 0:
            self.cash_timer = random.randint(100, 170)
            self.cash_items.append(Cash(self))

        self.police_timer -= 1
        if self.police_timer <= 0:
            self.police_timer = max(150, 460 - heat * 60) + random.randint(0, 60)
            if len(self.police) < 1 + heat:
                kind = pick_police_type(heat)
                cop = Police(kind, heat, v, self)
                probe = cop.rect.inflate(20, 40)
                if not any(probe.colliderect(o.rect) for o in self.police):
                    self.police.append(cop)
                    if not self.seen_police:
                        self.seen_police = True
                        self.say("Police on your tail! Keep moving.", YELLOW, 150)

        self.barrier_timer -= 1
        if self.barrier_timer <= 0:
            c, wd, _, inter = self.road(-20)
            if inter:
                self.barrier_timer = 60       # wait until we're past the intersection
            else:
                self.barrier_timer = max(420, 1000 - heat * 120)
                rb = Roadblock(random.uniform(-0.22, 0.22), max(110, wd * 0.4))
                rb.update(0, self)
                self.barriers.append(rb)
                self.say("ROADBLOCK AHEAD!", RED, 90)

        self.cross_timer -= 1
        if self.cross_timer <= 0 and len(self.cross) < 3:
            self.cross_timer = random.randint(35, 80)
            bands = self.visible_intersections()
            if bands:
                a = random.choice(bands)
                upper = random.random() < 0.5
                car = CrossCar(a + (IH * 0.70 if upper else IH * 0.30), 1 if upper else -1)
                if not any(abs(o.D - car.D) < 20 and abs(o.x - car.x) < 160 for o in self.cross):
                    self.cross.append(car)

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
        self.dist += v
        self.distance += v * 0.1

        section = self.track.section_at(self.dist + HEIGHT - (p.y + p.h / 2))
        if section is not self.cur_section:
            self.cur_section = section
            self.say(ZONE_MESSAGES[section.kind], WHITE, 140)

        self.spawn()

        for t in self.traffic:
            t.update(v, self)
        for c in self.cross:
            c.update(self)
        for c in self.police:
            c.update(v, p, self)
        for b in self.barriers:
            b.update(v, self)
        for c in self.cash_items:
            c.update(v, self)
        for part in self.particles:
            part.update(v)

        self._handle_collisions()

        self.traffic = [t for t in self.traffic if not t.gone()]
        self.cross = [c for c in self.cross if not c.gone()]
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
        p.since_hit = 0
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
                self.player_hit(dmg, 0.6 if t.oncoming else 0.8)
                self.explode(t.cx, t.y + t.h / 2)
                self.traffic.remove(t)

        # Player vs cross traffic
        for c in self.cross[:]:
            if c.rect.colliderect(pr):
                self.player_hit(12 + p.v * 1.5, 0.55)
                self.explode(c.cx, c.y + c.h / 2)
                self.cross.remove(c)

        # Player vs roadblock
        for rb in self.barriers:
            for idx, r in rb.live():
                if r.colliderect(pr):
                    self.player_hit(22, 0.55)
                    self.emit(p.cx, p.y, WHITE, n=10, speed=4)
                    rb.alive[idx] = False

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
                    lo, hi = self.bounds(cop.y + cop.h / 2)
                    cop.x = clamp(cop.x + direction * 16, lo, hi - cop.w)
                    p.vx -= direction * 3
                    self.emit((cop.cx + p.cx) / 2, (cop.y + p.y) / 2 + 20, YELLOW, n=8, speed=4)
            for t in self.traffic[:]:
                if t.rect.colliderect(cr):
                    cop.hp -= 25
                    cop.speed *= 0.7
                    self.explode(t.cx, t.y + t.h / 2)
                    self.traffic.remove(t)
            for c in self.cross[:]:
                if c.rect.colliderect(cr):
                    cop.hp -= 30
                    cop.speed *= 0.6
                    self.explode(c.cx, c.y + c.h / 2)
                    self.cross.remove(c)
            for rb in self.barriers:
                for idx, r in rb.live():
                    if r.colliderect(cr):
                        cop.hp -= 45
                        cop.speed *= 0.4
                        self.emit(cop.cx, cop.y, WHITE, n=10, speed=4)
                        rb.alive[idx] = False

        # Keep police from stacking on top of each other
        for i, a in enumerate(self.police):
            for b in self.police[i + 1:]:
                if a.rect.colliderect(b.rect):
                    push = 1.2 if a.cx < b.cx else -1.2
                    lo, hi = self.bounds(a.y + a.h / 2)
                    a.x = clamp(a.x - push, lo, hi - a.w)
                    lo, hi = self.bounds(b.y + b.h / 2)
                    b.x = clamp(b.x + push, lo, hi - b.w)

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
    def draw_scenery(self, w, c0, c1):
        dist = self.dist
        track = self.track
        for i in range(c0, c1 + 1):
            Dc = i * CH + CH / 2
            s = track.section_at(Dc)
            ymid = dist + HEIGHT - Dc
            c, wd = s.center(Dc), s.width_at(Dc)
            for side in (-1, 1):
                edge = c + side * wd / 2
                if s.theme == "city":
                    bw = 60 + hrand(i, side, 1) * 80
                    r2 = hrand(i, side, 2)
                    bh = CH - 14
                    x = edge - 16 - bw if side < 0 else edge + 16
                    rect = pygame.Rect(int(x), int(ymid - bh / 2), int(bw), bh)
                    base = (60 + int(r2 * 40), 64 + int(r2 * 36), 82 + int(r2 * 40))
                    pygame.draw.rect(w, base, rect)
                    pygame.draw.rect(w, (30, 32, 40), rect, 2)
                    for cy in range(rect.y + 10, rect.bottom - 10, 20):
                        for cx in range(rect.x + 8, rect.right - 12, 18):
                            lit = (int(r2 * 1000) + cx * 7 + cy * 13) % 5 == 0
                            pygame.draw.rect(w, (240, 220, 120) if lit else (36, 40, 54), (cx, cy, 9, 11))
                elif s.theme == "grass":
                    for k in (1, 2):
                        tx = edge + side * (30 + hrand(i, side, k) * 100)
                        ty = ymid + (hrand(i, side, k + 5) - 0.5) * CH
                        rad = 11 + hrand(i, side, k + 9) * 9
                        pygame.draw.circle(w, (22, 52, 32), (int(tx), int(ty)), int(rad))
                        pygame.draw.circle(w, (34, 78, 46), (int(tx - 3), int(ty - 3)), int(rad * 0.6))
                else:
                    for k in (1, 2):
                        rw = 30 + hrand(i, side, k + 9) * 40
                        rh = 20 + hrand(i, side, k + 3) * 25
                        tx = edge + side * (rw / 2 + 10 + hrand(i, side, k) * 80)
                        ty = ymid + (hrand(i, side, k + 5) - 0.5) * CH
                        pygame.draw.ellipse(w, (112, 84, 54), (int(tx - rw / 2), int(ty - rh / 2), int(rw), int(rh)))
                        pygame.draw.ellipse(w, (134, 104, 68), (int(tx - rw / 2), int(ty - rh / 2), int(rw * 0.7), int(rh * 0.6)))

    def draw_road(self, w):
        dist = self.dist
        track = self.track
        ys = list(range(-STEP, HEIGHT + 2 * STEP, STEP))
        centers, widths = [], []
        for y in ys:
            D = dist + HEIGHT - y
            s = track.section_at(D)
            centers.append(s.center(D))
            widths.append(s.width_at(D))

        # Sides, asphalt and edge lines, one band at a time
        for i in range(len(ys) - 1):
            y0, y1 = ys[i], ys[i + 1]
            Dm = dist + HEIGHT - (y0 + y1) / 2
            s = track.section_at(Dm)
            th = THEMES[s.theme]
            side_col = th["side"] if int(Dm // 120) % 2 == 0 else th["side2"]
            pygame.draw.rect(w, side_col, (0, y0, WIDTH, y1 - y0 + 1))
            l0, r0 = centers[i] - widths[i] / 2, centers[i] + widths[i] / 2
            l1, r1 = centers[i + 1] - widths[i + 1] / 2, centers[i + 1] + widths[i + 1] / 2
            pygame.draw.polygon(w, th["road"], [(l0, y0), (r0, y0), (r1, y1 + 1), (l1, y1 + 1)])
            edge_col, edge_w = th["edge"]
            pygame.draw.line(w, edge_col, (l0 + 5, y0), (l1 + 5, y1 + 1), edge_w)
            pygame.draw.line(w, edge_col, (r0 - 5, y0), (r1 - 5, y1 + 1), edge_w)

        # Scenery beside the road
        self.draw_scenery(w, int((dist - 100) // CH), int((dist + HEIGHT + 100) // CH) + 1)

        # Solid double yellow line down the middle (highway and downtown)
        for i in range(len(ys) - 1):
            Dm = dist + HEIGHT - (ys[i] + ys[i + 1]) / 2
            if track.section_at(Dm).kind in ("highway", "downtown"):
                for off in (-3.5, 3.5):
                    pygame.draw.line(w, YELLOW, (centers[i] + off, ys[i]),
                                     (centers[i + 1] + off, ys[i + 1] + 1), 3)

        # Dashed lane lines
        k0 = int(dist // 44) - 1
        for k in range(k0, k0 + HEIGHT // 44 + 3):
            Da, Db = k * 44, k * 44 + 22
            ya, yb = dist + HEIGHT - Da, dist + HEIGHT - Db
            if yb > HEIGHT + 5 or ya < -5:
                continue
            s = track.section_at((Da + Db) / 2)
            if s.kind == "highway":
                fracs, col = (-0.25, 0.25), (200, 200, 205)
            elif s.kind == "canyon":
                fracs, col = (0.0,), YELLOW
            else:
                continue
            ca, wa = s.center(Da), s.width_at(Da)
            cb, wb = s.center(Db), s.width_at(Db)
            for f in fracs:
                pygame.draw.line(w, col, (ca + f * wa, ya), (cb + f * wb, yb), 4)

        # Intersections are painted over everything on the road
        i0 = track.index_at(dist - IH)
        i1 = track.index_at(dist + HEIGHT + IH)
        for s in track.sections[i0:i1 + 1]:
            for a in s.intersections:
                ytop = dist + HEIGHT - (a + IH)
                ybot = dist + HEIGHT - a
                if ybot < 0 or ytop > HEIGHT:
                    continue
                pygame.draw.rect(w, THEMES["city"]["road"], (0, int(ytop), WIDTH, IH))
                c, wd = s.center(a), s.width_at(a)
                x = c - wd / 2 + 8
                while x < c + wd / 2 - 14:
                    pygame.draw.rect(w, (225, 225, 230), (int(x), int(ytop + 6), 9, 16))
                    pygame.draw.rect(w, (225, 225, 230), (int(x), int(ybot - 22), 9, 16))
                    x += 16
                mid = int((ytop + ybot) / 2)
                for sx in range(0, WIDTH, 44):
                    pygame.draw.rect(w, (200, 200, 205), (sx, mid - 2, 22, 4))

    def draw(self, surf):
        w = self.world
        self.draw_road(w)
        for c in self.cash_items:
            c.draw(w)
        for b in self.barriers:
            b.draw(w)
        for t in self.traffic:
            t.draw(w)
        for c in self.cross:
            c.draw(w)
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
        if p.regenerating:
            surf.blit(font_small.render("+", True, GREEN), (166, 9))
        pygame.draw.rect(surf, BLACK, (10, 30, 150, 10))
        pygame.draw.rect(surf, BLUE, (10, 30, 150 * clamp(p.nitro / p.nitro_cap, 0, 1), 10))
        pygame.draw.rect(surf, WHITE, (10, 30, 150, 10), 2)

        def put(txt, col, x, y, right=False):
            img = font_small.render(txt, True, col)
            shade = font_small.render(txt, True, BLACK)
            if right:
                x = x - img.get_width()
            surf.blit(shade, (x + 1, y + 1))
            surf.blit(shade, (x - 1, y + 1))
            surf.blit(img, (x, y))

        put(f"Score: {self.score}", WHITE, 10, 46)
        put(f"Cash: ${self.cash}", GREEN, 10, 66)
        put(self.cur_section.name, (200, 205, 220), 10, 86)

        put("U: Upgrades", WHITE, WIDTH - 10, 12, right=True)
        put("HEAT", WHITE, WIDTH - 110, 34, right=True)
        for i in range(5):
            col = RED if i < self.heat else GRAY
            pygame.draw.rect(surf, col, (WIDTH - 100 + i * 18, 36, 14, 12))
        put(f"{int(p.v * 16)} km/h", YELLOW if p.boosting else WHITE, WIDTH - 10, 56, right=True)
        put(f"Best: {self.best}", WHITE, WIDTH - 10, 76, right=True)

        if not self.paused_for_upgrade and self.message_timer > 0:
            m = font_msg.render(self.message, True, self.message_color)
            shadow = font_msg.render(self.message, True, BLACK)
            pos = (WIDTH // 2 - m.get_width() // 2, 112)
            surf.blit(shadow, (pos[0] + 2, pos[1] + 2))
            surf.blit(m, pos)

    def draw_title(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surf.blit(overlay, (0, 0))
        title = font_big.render("GETAWAY CHASE", True, YELLOW)
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 160))
        lines = [
            "Steer: arrows or A/D",
            "Gas / brake: up and down (W/S)",
            "Nitro: Shift",
            "Upgrades: U, then 1-6",
            "",
            "Oncoming traffic is on the left.",
            "The route changes: highway,",
            "downtown streets, canyon roads.",
            "Hold the gas to pull away from police.",
            "",
            "Press SPACE to start",
        ]
        for i, line in enumerate(lines):
            txt = font_small.render(line, True, WHITE)
            surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 236 + i * 26))

    def draw_upgrade_menu(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surf.blit(overlay, (0, 0))

        title = font_big.render("GARAGE", True, WHITE)
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 20))
        cash = font_small.render(f"Cash: ${self.cash}", True, GREEN)
        surf.blit(cash, (WIDTH // 2 - cash.get_width() // 2, 68))

        row_h, start_y = 70, 100
        for i, u in enumerate(UPGRADES):
            level = getattr(self.player, f"{u['key']}_level")
            y = start_y + i * row_h
            box = pygame.Rect(40, y, WIDTH - 80, 60)
            maxed = level >= MAX_LEVEL
            pygame.draw.rect(surf, (50, 60, 45) if maxed else (40, 44, 56), box, border_radius=8)
            pygame.draw.rect(surf, WHITE, box, 2, border_radius=8)
            cost = "MAX" if maxed else f"${upgrade_cost(level, u['cost_base'])}"
            label = font_small.render(f"{i + 1}. {u['label']}  (Lv {level}/{MAX_LEVEL})  -  {cost}", True, WHITE)
            desc = font_small.render(u["desc"], True, (150, 155, 170))
            surf.blit(label, (box.x + 10, box.y + 9))
            surf.blit(desc, (box.x + 10, box.y + 33))

        end_y = start_y + len(UPGRADES) * row_h
        if self.message_timer > 0:
            m = font_small.render(self.message, True, self.message_color)
            surf.blit(m, (WIDTH // 2 - m.get_width() // 2, end_y + 4))
        hint = font_small.render("Press 1-6 to buy, U to close", True, (150, 155, 170))
        surf.blit(hint, (WIDTH // 2 - hint.get_width() // 2, end_y + 30))

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
