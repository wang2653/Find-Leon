import json
import math
import os
import random
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk

# Constants & Configurations
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image")
HIGH_SCORE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "highscore.json"
)

WINDOW_WIDTH = 450
WINDOW_HEIGHT = 700
INFO_BAR_HEIGHT = 50
PLAY_AREA_HEIGHT = WINDOW_HEIGHT - INFO_BAR_HEIGHT

FPS = 60
TIME_STEP_MS = round(1000 / FPS)

INITIAL_TIME_SECONDS = 300
LOW_TIME_WARNING_SECONDS = 30

GRAVITY = 0.6  # g
RESTITUTION = 0.15  # bounce factor

FRICTION_X = 0.98  # h_friction
FRICTION_Y = 0.99  # v_friction
GROUND_FRICTION = 0.7  # g_friction

DANGER_LINE_Y = 100
MAX_DANGER_FRAMES = 24  # frames

FRUIT_SPAWN_Y = 50  # new
DROP_COOLDOWN_MS = 800  # next new

ORB_RADIUS = 20
MAX_GOOD_ORBS = 2  # 2 good orbs
GOOD_ORB_SPAWN_INTERVAL = 10 * FPS
GOOD_ORB_TIME_DELTA = 5

BAD_ORB_MIN_SPAWN_INTERVAL = 15 * FPS
BAD_ORB_MAX_SPAWN_INTERVAL = 20 * FPS
BAD_ORB_MIN_LIFETIME = 3 * FPS
BAD_ORB_MAX_LIFETIME = 5 * FPS
BAD_ORB_TIME_DELTA = -5

START_EFFECT_STEPS = 20  # start effect frames
START_EFFECT_DELAY_MS = 30
START_EFFECT_SCALE_INCREASE = 0.3

COLLISION_ITERATIONS = 5  # collision iterations per frame, reduce overlaps

BLOOD_MIST_PARTICLE_COUNT = 20
BLOOD_MIST_EXTRA_PARTICLES_PER_LEVEL = 5

BLOOD_MIST_MIN_SPEED = 0.8
BLOOD_MIST_MAX_SPEED = 5.8

BLOOD_MIST_MIN_RADIUS = 1.5
BLOOD_MIST_MAX_RADIUS = 7.5

BLOOD_MIST_MIN_LIFETIME = 20
BLOOD_MIST_MAX_LIFETIME = 34

BLOOD_MIST_MIN_GRAVITY = 0.05
BLOOD_MIST_MAX_GRAVITY = 0.14

BLOOD_MIST_COLORS = [
    "#1A0000",
    "#2B0000",
    "#3A0000",
    "#4A0000",
    "#5C0000",
    "#6E0000",
    "#7A0A0A",
    "#260000",
]

RADII = [25, 35, 40, 50, 60, 70, 75, 85, 95, 200]

FRUIT_COLORS = [
    "#ff6b6b",
    "#ffa94d",
    "#ffd43b",
    "#69db7c",
    "#38d9a9",
    "#4dabf7",
    "#748ffc",
    "#b197fc",
    "#f783ac",
    "#adb5bd",
]

STATE_START = "start"
STATE_ANIMATING = "animating"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"


# Utility Functions
def get_resample_filter():
    return Image.Resampling.LANCZOS


def image_path(filename):
    return os.path.join(IMAGE_DIR, filename)


def load_rgba_image(path, size=None):
    img = Image.open(path).convert("RGBA")
    if size is not None:
        img = img.resize(size, get_resample_filter())
    return img


# image crop
def crop_center(img, width, height):
    left = max(0, (img.width - width) // 2)
    top = max(0, (img.height - height) // 2)
    return img.crop((left, top, left + width, top + height))


def make_circle_image(img, size, outline=None, outline_width=2):
    # square
    img = img.resize((size, size), get_resample_filter())

    # add black mask
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    # solid white circle
    draw.ellipse((0, 0, size, size), fill=255)
    # paste img to mask
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)

    if outline:
        output_draw = ImageDraw.Draw(output)
        output_draw.ellipse(
            (1, 1, size - 1, size - 1),
            outline=outline,
            width=outline_width,
        )
    return output


# Data Models
class Orb:
    def __init__(self, x, y, time_delta, lifetime=None):
        self.x = x
        self.y = y
        self.radius = ORB_RADIUS
        # >0 add, <0 minus
        self.time_delta = time_delta
        self.lifetime = lifetime
        self.marked_for_deletion = False

    def is_bad(self):
        return self.time_delta < 0


class Fruit:
    def __init__(self, x, y, level, active=True):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0

        self.level = level
        self.radius = RADII[level]
        self.mass = float(self.radius**2)
        self.color = FRUIT_COLORS[level % len(FRUIT_COLORS)]

        # active false means not released
        self.active = active
        self.marked_for_deletion = False
        # frame to calc danger line
        self.age = 0

    def update_physics(self):
        if not self.active:
            return

        self.age += 1

        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy

        self.vx *= FRICTION_X
        self.vy *= FRICTION_Y


# Game Application
class GameApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Find Leon")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(
            root,
            width=WINDOW_WIDTH,
            height=PLAY_AREA_HEIGHT,
            bg="#FCE4EC",
        )
        self.canvas.pack()

        self.info_frame = tk.Frame(root, bg="#333", height=INFO_BAR_HEIGHT)
        self.info_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.score_label = tk.Label(
            self.info_frame,
            text="Score: 0",
            fg="white",
            bg="#333",
            font=("Arial", 14, "bold"),
        )
        self.score_label.pack(side=tk.LEFT, padx=10, pady=10)

        self.merge_count_label = tk.Label(
            self.info_frame,
            text="Merges: 0",
            fg="white",
            bg="#333",
            font=("Arial", 14),
        )
        self.merge_count_label.pack(side=tk.LEFT, padx=10, pady=10)

        self.high_score = self.load_high_score()

        self.high_score_label = tk.Label(
            self.info_frame,
            text=f"High Score: {self.high_score}",
            fg="white",
            bg="#333",
            font=("Arial", 14),
        )
        self.high_score_label.pack(side=tk.RIGHT, padx=10, pady=10)

        self.image_cache = {}
        self.bg_photo = None
        self.cover_photo = None
        self.original_cover_img = None
        self.orb_image = None
        self.bad_orb_image = None

        self.restart_button = None
        self.start_button = None

        self.state = STATE_START

        self.reset_game_state()

        self.load_assets()

        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_mouse_click)

        self.show_startup_screen()

    # State
    def reset_game_state(self):
        self.score = 0
        self.merge_count = 0
        self.time_left = INITIAL_TIME_SECONDS
        self.frames = 0

        self.fruits = []
        self.good_orbs = []
        self.bad_orbs = []

        self.good_orb_frames = 0
        self.bad_orb_frames = 0
        self.bad_orb_spawn_time = random.randint(
            BAD_ORB_MIN_SPAWN_INTERVAL,
            BAD_ORB_MAX_SPAWN_INTERVAL,
        )

        self.current_fruit = None
        self.can_drop = True
        self.danger_frames = 0
        # bloodmist
        self.effects = []

    # Persistence
    def load_high_score(self):
        if not os.path.exists(HIGH_SCORE_FILE):
            return 0
        # read score
        try:
            with open(HIGH_SCORE_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
            return int(data.get("highscore", 0))
        except (json.JSONDecodeError, OSError, ValueError) as error:
            print(f"Failed to load high score: {error}")
            return 0

    def save_high_score(self):
        try:
            with open(HIGH_SCORE_FILE, "w", encoding="utf-8") as file:
                json.dump({"highscore": self.high_score}, file)
        except OSError as error:
            print(f"Failed to save high score: {error}")

    # Asset Loading
    def load_assets(self):
        self.load_fruit_images()
        self.load_background()
        self.load_cover_image()
        self.load_orb_images()

    def load_fruit_images(self):
        self.image_cache.clear()

        for level, radius in enumerate(RADII):
            filename = f"{level + 1}.png"
            path = image_path(filename)

            if os.path.exists(path):
                try:
                    pil_img = load_rgba_image(path, (radius * 2, radius * 2))
                    circular_img = make_circle_image(pil_img, radius * 2)
                    self.image_cache[level] = ImageTk.PhotoImage(circular_img)
                except Exception as error:
                    print(f"Failed to load fruit image {path}: {error}")
            else:
                print(f"Fruit image not found: {path}")

    def load_background(self):
        path = image_path("background.png")

        if not os.path.exists(path):
            self.bg_photo = None
            return

        try:
            img = load_rgba_image(path, (WINDOW_WIDTH, PLAY_AREA_HEIGHT))
            self.bg_photo = ImageTk.PhotoImage(img)
        except Exception as error:
            print(f"Failed to load background image: {error}")
            self.bg_photo = None

    def load_cover_image(self):
        path = image_path("cover.png")

        if not os.path.exists(path):
            self.cover_photo = None
            self.original_cover_img = None
            return

        try:
            img = load_rgba_image(path, (WINDOW_WIDTH, PLAY_AREA_HEIGHT))
            self.original_cover_img = img
            # to tk
            self.cover_photo = ImageTk.PhotoImage(img)
        except Exception as error:
            print(f"Failed to load cover image: {error}")
            self.cover_photo = None
            self.original_cover_img = None

    def load_orb_images(self):
        path = image_path("green_herb.png")

        if not os.path.exists(path):
            self.orb_image = None
            self.bad_orb_image = None
            return

        try:
            base_img = load_rgba_image(path)
            size = 30

            good_img = make_circle_image(
                base_img, size, outline="white", outline_width=2
            )
            bad_img = make_circle_image(base_img, size, outline="red", outline_width=2)

            self.orb_image = ImageTk.PhotoImage(good_img)
            self.bad_orb_image = ImageTk.PhotoImage(bad_img)
        except Exception as error:
            print(f"Failed to load orb image: {error}")
            self.orb_image = None
            self.bad_orb_image = None

    # Startup Screen
    def show_startup_screen(self):
        self.state = STATE_START
        self.canvas.delete("all")

        if self.cover_photo:
            self.canvas.create_image(
                0, 0, image=self.cover_photo, anchor="nw", tags="cover"
            )
        else:
            self.canvas.create_text(
                WINDOW_WIDTH / 2,
                PLAY_AREA_HEIGHT / 2 - 50,
                text="START GAME",
                font=("Arial", 36, "bold"),
                fill="#333",
            )

        self.start_button = tk.Button(
            self.root,
            text="START",
            font=("Arial", 16, "bold"),
            bg="#ff5722",
            fg="white",
            cursor="hand2",
            command=self.start_game_effect,
            padx=15,
            pady=8,
            relief=tk.RAISED,
            bd=4,
        )

        self.canvas.create_window(
            WINDOW_WIDTH / 2,
            PLAY_AREA_HEIGHT - 70,
            window=self.start_button,
            tags="start_btn",
        )

    def start_game_effect(self):
        if self.start_button:
            self.start_button.destroy()
            self.start_button = None

        self.state = STATE_ANIMATING
        self.effect_step = 0
        self.play_startup_effect()

    def play_startup_effect(self):
        if self.effect_step > START_EFFECT_STEPS:
            self.canvas.delete("all")
            self.start_game()
            return
        # progress 0 -> 1
        # scale 1 -> 1.5 zoon in
        # alpha 255 -> 0 fade out
        progress = self.effect_step / START_EFFECT_STEPS
        scale = 1.0 + progress * START_EFFECT_SCALE_INCREASE
        alpha = int(255 * (1 - progress))

        if self.original_cover_img:
            orig_w, orig_h = self.original_cover_img.size
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)

            scaled_img = self.original_cover_img.resize(
                (new_w, new_h),
                get_resample_filter(),
            )
            cropped_img = crop_center(scaled_img, orig_w, orig_h)

            if cropped_img.mode == "RGBA":
                mask = cropped_img.split()[3]
            else:
                mask = Image.new("L", cropped_img.size, 255)

            faded_mask = mask.point(lambda p: p * alpha // 255)
            cropped_img.putalpha(faded_mask)

            self.cover_photo = ImageTk.PhotoImage(cropped_img)

            self.canvas.delete("all")

            if self.bg_photo:
                self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")

            self.canvas.create_image(
                0, 0, image=self.cover_photo, anchor="nw", tags="cover"
            )

        self.effect_step += 1
        # delay for 16ms , means 60 fps
        self.root.after(START_EFFECT_DELAY_MS, self.play_startup_effect)

    def start_game(self):
        self.state = STATE_PLAYING
        self.reset_game_state()
        self.score_label.config(text=f"Score: {self.score}")
        self.merge_count_label.config(text=f"Merges: {self.merge_count}")
        self.spawn_new_fruit()
        self.update_game()

    # Input
    def on_mouse_move(self, event):
        if self.state != STATE_PLAYING:
            return

        if not self.current_fruit:
            return

        if self.current_fruit.active:
            return

        x = max(
            self.current_fruit.radius,
            min(event.x, WINDOW_WIDTH - self.current_fruit.radius),
        )
        self.current_fruit.x = x

        self.render()

    def on_mouse_click(self, event):
        if self.state != STATE_PLAYING:
            return

        if not self.current_fruit:
            return

        if self.current_fruit.active:
            return

        if not self.can_drop:
            return

        self.current_fruit.active = True
        self.current_fruit.vx = random.uniform(-1.0, 1.0)

        self.fruits.append(self.current_fruit)

        self.current_fruit = None
        self.can_drop = False

        self.root.after(DROP_COOLDOWN_MS, self.spawn_new_fruit)

    # Game Logic
    def format_time(self, seconds):
        minutes = seconds // 60  # MM
        seconds = seconds % 60  # SS
        return f"{minutes:02d}:{seconds:02d}"

    def spawn_new_fruit(self):
        if self.state != STATE_PLAYING:
            return

        level = random.randint(0, 2)  # spawn level 0 1 2
        self.current_fruit = Fruit(  # middle top
            WINDOW_WIDTH // 2, FRUIT_SPAWN_Y, level, active=False
        )
        self.can_drop = True
        self.render()

    def update_game(self):  # main
        if self.state != STATE_PLAYING:
            return

        self.update_timer()

        if self.state != STATE_PLAYING:
            return

        self.spawn_good_orb_if_needed()
        self.spawn_bad_orb_if_needed()

        self.update_good_orbs()
        self.update_bad_orbs()
        self.update_fruits()
        self.update_effects()  # bloodmist

        self.resolve_collisions()

        self.fruits = [fruit for fruit in self.fruits if not fruit.marked_for_deletion]

        self.check_game_over()

        if self.state == STATE_PLAYING:
            self.render()
            self.root.after(TIME_STEP_MS, self.update_game)

    def update_timer(self):
        self.frames += 1

        if self.frames < FPS:
            return

        self.frames = 0
        self.time_left -= 1

        if self.time_left <= 0:
            self.time_left = 0
            self.end_game()

    def spawn_good_orb_if_needed(self):
        if len(self.good_orbs) >= MAX_GOOD_ORBS:
            return

        self.good_orb_frames += 1

        if self.good_orb_frames < GOOD_ORB_SPAWN_INTERVAL:
            return

        x, y = self.get_valid_orb_position()
        self.good_orbs.append(Orb(x, y, GOOD_ORB_TIME_DELTA))
        self.good_orb_frames = 0

    def spawn_bad_orb_if_needed(self):
        self.bad_orb_frames += 1

        if self.bad_orb_frames < self.bad_orb_spawn_time:
            return

        x, y = self.get_valid_orb_position()
        lifetime = random.randint(BAD_ORB_MIN_LIFETIME, BAD_ORB_MAX_LIFETIME)

        self.bad_orbs.append(Orb(x, y, BAD_ORB_TIME_DELTA, lifetime=lifetime))

        self.bad_orb_frames = 0
        self.bad_orb_spawn_time = random.randint(
            BAD_ORB_MIN_SPAWN_INTERVAL,
            BAD_ORB_MAX_SPAWN_INTERVAL,
        )

    def update_good_orbs(self):
        self.update_orb_collisions(self.good_orbs)
        self.good_orbs = [orb for orb in self.good_orbs if not orb.marked_for_deletion]

    def update_bad_orbs(self):
        for orb in self.bad_orbs:
            if orb.lifetime is None:
                continue

            orb.lifetime -= 1

            if orb.lifetime <= 0:
                orb.marked_for_deletion = True

        self.update_orb_collisions(self.bad_orbs)
        self.bad_orbs = [orb for orb in self.bad_orbs if not orb.marked_for_deletion]

    def update_orb_collisions(self, orbs):
        for orb in orbs:
            if orb.marked_for_deletion:
                continue

            for fruit in self.fruits:
                if fruit.marked_for_deletion:
                    continue

                dx = fruit.x - orb.x
                dy = fruit.y - orb.y

                if dx * dx + dy * dy < (fruit.radius + orb.radius) ** 2:
                    orb.marked_for_deletion = True
                    self.time_left = max(0, self.time_left + orb.time_delta)

                    if self.time_left <= 0:
                        self.end_game()

                    break

    def update_fruits(self):
        for fruit in self.fruits:
            fruit.update_physics()

    def resolve_collisions(self):
        for _ in range(COLLISION_ITERATIONS):
            for i, fruit_1 in enumerate(self.fruits):
                if fruit_1.marked_for_deletion:
                    continue

                for j in range(i + 1, len(self.fruits)):
                    fruit_2 = self.fruits[j]

                    if fruit_2.marked_for_deletion:
                        continue

                    dx = fruit_2.x - fruit_1.x
                    dy = fruit_2.y - fruit_1.y
                    min_dist = fruit_1.radius + fruit_2.radius

                    if abs(dx) > min_dist or abs(dy) > min_dist:
                        continue

                    dist_sq = dx * dx + dy * dy
                    min_dist_sq = min_dist * min_dist

                    if dist_sq >= min_dist_sq:
                        continue

                    distance = math.sqrt(dist_sq) if dist_sq > 0 else 0

                    if distance == 0:
                        # Avoid division by zero when two fruits overlap exactly.
                        dx = random.choice([-0.1, 0.1])
                        dy = random.choice([-0.1, 0.1])
                        distance = math.sqrt(dx * dx + dy * dy)

                    if (
                        fruit_1.level == fruit_2.level
                        and fruit_1.level < len(RADII) - 1
                    ):
                        fruit_1.marked_for_deletion = True
                        fruit_2.marked_for_deletion = True
                        self.merge_fruits(fruit_1, fruit_2)
                        break

                    self.separate_overlapping_fruits(
                        fruit_1,
                        fruit_2,
                        dx,
                        dy,
                        distance,
                        min_dist,
                    )
                    self.apply_collision_impulse(
                        fruit_1,
                        fruit_2,
                        dx,
                        dy,
                        distance,
                    )

                self.resolve_wall_collision(fruit_1)

    def separate_overlapping_fruits(self, fruit_1, fruit_2, dx, dy, distance, min_dist):
        overlap = min_dist - distance
        nx = dx / distance
        ny = dy / distance

        correction_x = nx * overlap * 0.5  # each fruit take half correction
        correction_y = ny * overlap * 0.5

        fruit_1.x -= correction_x
        fruit_1.y -= correction_y
        fruit_2.x += correction_x
        fruit_2.y += correction_y

    def apply_collision_impulse(self, fruit_1, fruit_2, dx, dy, distance):
        nx = dx / distance
        ny = dy / distance

        relative_vx = fruit_1.vx - fruit_2.vx
        relative_vy = fruit_1.vy - fruit_2.vy
        # velocity along normal
        velocity_along_normal = relative_vx * nx + relative_vy * ny
        # only apply impulse if moving toward each other
        if velocity_along_normal <= 0:
            return
        # Calculate the sum of the reciprocals of the masses of two fruits
        inv_mass_sum = (1 / fruit_1.mass) + (1 / fruit_2.mass)
        # impulse = -(1 + restitution)
        impulse = -(1 + RESTITUTION) * velocity_along_normal / inv_mass_sum

        fruit_1.vx += (impulse * nx) / fruit_1.mass
        fruit_1.vy += (impulse * ny) / fruit_1.mass
        fruit_2.vx -= (impulse * nx) / fruit_2.mass
        fruit_2.vy -= (impulse * ny) / fruit_2.mass

    def resolve_wall_collision(self, fruit):
        if fruit.marked_for_deletion:
            return

        if fruit.x - fruit.radius < 0:
            fruit.x = fruit.radius
            fruit.vx *= -RESTITUTION
        elif fruit.x + fruit.radius > WINDOW_WIDTH:
            fruit.x = WINDOW_WIDTH - fruit.radius
            fruit.vx *= -RESTITUTION

        if fruit.y + fruit.radius > PLAY_AREA_HEIGHT:
            fruit.y = PLAY_AREA_HEIGHT - fruit.radius
            fruit.vy *= -RESTITUTION
            fruit.vx *= GROUND_FRICTION

    def merge_fruits(self, fruit_1, fruit_2):
        new_level = fruit_1.level + 1
        new_x = (fruit_1.x + fruit_2.x) / 2
        new_y = (fruit_1.y + fruit_2.y) / 2
        # bloodmist
        self.create_blood_mist(new_x, new_y, new_level)

        points = 2 ** (new_level + 1)  # calc point base on new
        self.score += points

        self.merge_count += 1

        self.score_label.config(text=f"Score: {self.score}")
        self.merge_count_label.config(text=f"Merges: {self.merge_count}")

        if self.score > self.high_score:
            self.high_score = self.score
            self.high_score_label.config(text=f"High Score: {self.high_score}")
            self.save_high_score()

        merged_fruit = Fruit(new_x, new_y, new_level, active=True)
        merged_fruit.vx = (fruit_1.vx + fruit_2.vx) / 2
        merged_fruit.vy = min((fruit_1.vy + fruit_2.vy) / 2, 0) - 1.5

        self.fruits.append(merged_fruit)

    def create_blood_mist(self, x, y, level):
        particle_count = (
            BLOOD_MIST_PARTICLE_COUNT
            + level * BLOOD_MIST_EXTRA_PARTICLES_PER_LEVEL
            + random.randint(-4, 8)
        )

        for _ in range(max(8, particle_count)):
            angle = random.uniform(0, math.tau)

            if random.random() < 0.65:
                speed = random.uniform(BLOOD_MIST_MIN_SPEED, BLOOD_MIST_MAX_SPEED)
            else:
                speed = random.uniform(0.2, 2.0)

            radius = random.uniform(BLOOD_MIST_MIN_RADIUS, BLOOD_MIST_MAX_RADIUS)

            lifetime = random.randint(
                BLOOD_MIST_MIN_LIFETIME,
                BLOOD_MIST_MAX_LIFETIME,
            )

            gravity = random.uniform(
                BLOOD_MIST_MIN_GRAVITY,
                BLOOD_MIST_MAX_GRAVITY,
            )

            drag = 0.9

            x_offset = random.uniform(-6, 6)
            y_offset = random.uniform(-6, 6)

            self.effects.append(
                {
                    "type": "blood_mist",
                    "x": x + x_offset,
                    "y": y + y_offset,
                    "vx": math.cos(angle) * speed * random.uniform(0.7, 1.25),
                    "vy": math.sin(angle) * speed * random.uniform(0.7, 1.25)
                    - random.uniform(0.1, 1.4),
                    "radius": radius,
                    "life": lifetime,
                    "max_life": lifetime,
                    "gravity": gravity,
                    "drag": drag,
                    "color": random.choice(BLOOD_MIST_COLORS),
                }
            )

    def update_effects(self):
        for effect in self.effects:
            if effect["type"] != "blood_mist":
                continue

            effect["x"] += effect["vx"]
            effect["y"] += effect["vy"]

            effect["vy"] += effect["gravity"]

            effect["vx"] *= effect["drag"]
            effect["vy"] *= effect["drag"]

            shrink = random.uniform(0.94, 0.985)
            effect["radius"] = max(0.8, effect["radius"] * shrink)

            effect["life"] -= 1

        self.effects = [effect for effect in self.effects if effect["life"] > 0]

    def draw_effects(self):
        for effect in self.effects:
            if effect["type"] != "blood_mist":
                continue

            x = effect["x"]
            y = effect["y"]
            radius = effect["radius"]
            life_ratio = effect["life"] / effect["max_life"]

            if life_ratio > 0.65:
                color = effect["color"]
                outline = "#120000"
            elif life_ratio > 0.35:
                color = "#2A0000"
                outline = "#0D0000"
            else:
                color = "#140000"
                outline = "#050000"

            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=color,
                outline=outline,
                width=1,
            )

    def check_game_over(self):
        any_in_danger = any(
            fruit.y - fruit.radius < DANGER_LINE_Y and fruit.age > 20
            for fruit in self.fruits
        )

        if any_in_danger:
            self.danger_frames += 1

            if self.danger_frames >= MAX_DANGER_FRAMES:
                self.end_game()

            return

        self.danger_frames = max(0, self.danger_frames - 2)

    def end_game(self):
        if self.state == STATE_GAME_OVER:
            return

        self.state = STATE_GAME_OVER
        self.show_game_over_screen()

    # Orb Positioning
    def get_valid_orb_position(self):
        for _ in range(20):  # try 20 times
            x = random.randint(ORB_RADIUS, WINDOW_WIDTH - ORB_RADIUS)
            y = random.randint(DANGER_LINE_Y + 10, DANGER_LINE_Y + 50)

            if self.is_valid_orb_position(x, y):
                return x, y

        return (
            random.randint(ORB_RADIUS, WINDOW_WIDTH - ORB_RADIUS),
            random.randint(DANGER_LINE_Y + 10, DANGER_LINE_Y + 50),
        )

    def is_valid_orb_position(self, x, y):
        for orb in self.good_orbs + self.bad_orbs:
            dx = x - orb.x
            dy = y - orb.y
            min_dist = ORB_RADIUS + orb.radius

            if dx * dx + dy * dy < min_dist * min_dist:
                return False

        return True

    # Rendering
    def render(self):
        self.canvas.delete("all")

        self.draw_background()
        self.draw_danger_line()
        self.draw_fruits()
        self.draw_effects()  # bloodmist
        self.draw_orbs()
        self.draw_timer()

    def draw_background(self):
        if self.bg_photo:
            self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")
        else:
            self.canvas.create_rectangle(
                0,
                0,
                WINDOW_WIDTH,
                PLAY_AREA_HEIGHT,
                fill="#FCE4EC",
                outline="",
            )

    def draw_danger_line(self):
        line_color = "red"

        if self.danger_frames > 0 and (self.danger_frames // 5) % 2 == 0:
            line_color = "orange"

        self.canvas.create_line(  # danger line
            0,
            DANGER_LINE_Y,
            WINDOW_WIDTH,
            DANGER_LINE_Y,
            dash=(4, 4),
            fill=line_color,
            width=2,
        )

    def draw_fruits(self):
        fruits_to_draw = self.fruits.copy()

        if self.current_fruit:
            fruits_to_draw.append(self.current_fruit)

        for fruit in fruits_to_draw:
            if fruit.level in self.image_cache:
                self.canvas.create_image(
                    fruit.x,
                    fruit.y,
                    image=self.image_cache[fruit.level],
                )
                continue
            self.draw_fallback_fruit(fruit)

    def draw_fallback_fruit(self, fruit):
        x0 = fruit.x - fruit.radius
        y0 = fruit.y - fruit.radius
        x1 = fruit.x + fruit.radius
        y1 = fruit.y + fruit.radius

        self.canvas.create_oval(
            x0,
            y0,
            x1,
            y1,
            fill=fruit.color,
            outline="black",
            width=2,
        )

        name_text = str(fruit.level + 1)
        font_size = max(  # dynamically change font size
            8,
            min(
                fruit.radius // 2,
                int(fruit.radius * 1.8 / max(1, len(name_text))),
            ),
        )

        self.canvas.create_text(  # backup
            fruit.x,
            fruit.y,
            text=name_text,
            font=("Arial", font_size, "bold"),
            fill="black",
        )

    def draw_orbs(self):
        for orb in self.good_orbs:
            self.draw_single_orb(orb)

        for orb in self.bad_orbs:
            self.draw_single_orb(orb)

    def draw_single_orb(self, orb):
        image = self.bad_orb_image if orb.is_bad() else self.orb_image

        if image:
            self.canvas.create_image(orb.x, orb.y, image=image)
            return

        x0 = orb.x - orb.radius
        y0 = orb.y - orb.radius
        x1 = orb.x + orb.radius
        y1 = orb.y + orb.radius

        if orb.is_bad():  # backup orb
            fill = "purple"
            outline = "red"
            text = "-5s"
            text_fill = "white"
        else:  # backup orb
            fill = "gold"
            outline = "orange"
            text = "+5s"
            text_fill = "black"

        self.canvas.create_oval(  # backup orb
            x0,
            y0,
            x1,
            y1,
            fill=fill,
            outline=outline,
            width=2,
        )

        self.canvas.create_text(  # backup orb
            orb.x,
            orb.y,
            text=text,
            font=("Arial", 10, "bold"),
            fill=text_fill,
        )

    def draw_timer(self):
        timer_color = "red" if self.time_left <= LOW_TIME_WARNING_SECONDS else "white"

        self.canvas.create_text(
            WINDOW_WIDTH - 20,
            20,
            text=f"Time: {self.format_time(self.time_left)}",
            fill=timer_color,
            font=("Arial", 16, "bold"),
            anchor="ne",
        )

    def show_game_over_screen(self):
        panel_width = 300
        panel_height = 250

        x1 = (WINDOW_WIDTH - panel_width) / 2
        y1 = (PLAY_AREA_HEIGHT - panel_height) / 2
        x2 = x1 + panel_width
        y2 = y1 + panel_height

        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill="#ffffff",
            outline="#333333",
            width=4,
        )

        over_text = "TIME'S UP!" if self.time_left <= 0 else "GAME OVER"

        self.canvas.create_text(
            WINDOW_WIDTH / 2,
            y1 + 50,
            text=over_text,
            fill="#DC143C",
            font=("Arial", 32, "bold"),
        )

        self.canvas.create_text(
            WINDOW_WIDTH / 2,
            y1 + 110,
            text=f"Final Score: {self.score}",
            fill="#333",
            font=("Arial", 18, "bold"),
        )

        self.canvas.create_text(
            WINDOW_WIDTH / 2,
            y1 + 150,
            text=f"High Score: {self.high_score}",
            fill="#666",
            font=("Arial", 14),
        )

        self.restart_button = tk.Button(
            self.root,
            text="Play Again",
            font=("Arial", 14, "bold"),
            bg="#4CAF50",
            fg="white",
            cursor="hand2",
            command=self.restart_game,
        )

        self.canvas.create_window(
            WINDOW_WIDTH / 2,
            y1 + 200,
            window=self.restart_button,
        )

    def restart_game(self):
        if self.restart_button:
            self.restart_button.destroy()
            self.restart_button = None

        self.state = STATE_PLAYING

        self.reset_game_state()
        self.score_label.config(text=f"Score: {self.score}")
        self.merge_count_label.config(text=f"Merges: {self.merge_count}")

        self.spawn_new_fruit()
        self.update_game()


# Entry Point
if __name__ == "__main__":
    root = tk.Tk()
    app = GameApp(root)
    root.mainloop()
