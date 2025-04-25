import os

import pygame
import random
import math
import google.generativeai as genai # Requires installation
from dotenv import load_dotenv

# --- Gemini API Configuration ---
GEMINI_MODEL_NAME = "gemini-2.5-flash-preview-04-17"

# Initialize Gemini (handle potential errors if key is missing or invalid later)
try:
    load_dotenv()
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    gemini_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    GEMINI_ENABLED = True
    print("Gemini model initialized successfully.")
except Exception as e:
    print(f"Failed to initialize Gemini model: {e}")
    print("Gemini features will be disabled.")
    GEMINI_ENABLED = False
    gemini_model = None

# --- Game Constants ---
WIDTH, HEIGHT = 800, 600
FPS = 60
TITLE = "Geometry Wars (Gemini Integrated)"

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
PURPLE = (128, 0, 128)

# Player
PLAYER_SIZE = 20
PLAYER_SPEED = 5
PLAYER_SHOOT_DELAY = 200 # milliseconds
PLAYER_LIVES = 3

# Bullet
BULLET_SIZE = 5
BULLET_COLOR = YELLOW
BULLET_SPEED = 7

# Enemies
ENEMY_SIZE = 20
ENEMY_SPEED_MIN = 1
ENEMY_SPEED_MAX = 3
ENEMY_SPAWN_RATE = 1000 # milliseconds
MAX_ENEMIES = 20

# Particle Effects
PARTICLE_LIFETIME = 500 # milliseconds
PARTICLE_SPEED_MIN = 1
PARTICLE_SPEED_MAX = 4
PARTICLE_COUNT_MIN = 5
PARTICLE_COUNT_MAX = 15

# Game State
GAME_STATE_MENU = 0
GAME_STATE_PLAYING = 1
GAME_STATE_GAME_OVER = 2

# Gemini Integration Variables
GEMINI_TRIGGER_ENEMY_COUNT = 10 # Trigger a Gemini message every X enemies destroyed
gemini_message = ""
gemini_message_timer = 0
GEMINI_MESSAGE_DURATION = 5000 # milliseconds
enemies_destroyed_since_last_gemini = 0
last_gemini_call_time = 0
GEMINI_CALL_COOLDOWN = 10000 # milliseconds cooldown between calls

# --- Initialize Pygame ---
pygame.init()
pygame.mixer.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(TITLE)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)
small_font = pygame.font.Font(None, 24)

# --- Dummy Sound ---
class DummySound:
    """A dummy sound class that does nothing when play() is called."""
    def play(self):
        pass

# --- Load Assets (Basic placeholders) ---
# You can replace these with actual images/sounds
try:
    # Create simple surfaces if files don't exist
    player_img = pygame.Surface([PLAYER_SIZE, PLAYER_SIZE])
    player_img.fill(BLUE)
    player_img.set_colorkey(BLACK)
    pygame.draw.polygon(player_img, WHITE, [(0, PLAYER_SIZE), (PLAYER_SIZE // 2, 0), (PLAYER_SIZE, PLAYER_SIZE)]) # Triangle pointing up

    enemy_img = pygame.Surface([ENEMY_SIZE, ENEMY_SIZE])
    enemy_img.fill(RED)
    # enemy_img.set_colorkey(BLACK) # Keep background for squares

    bullet_img = pygame.Surface([BULLET_SIZE, BULLET_SIZE])
    bullet_img.fill(BULLET_COLOR)

    # Create simple sounds
    shoot_sound = DummySound()
    explode_sound = DummySound()
    # Fallback if sfx not available (e.g. non-default pygame builds)
except pygame.error:
     print("Warning: Could not load default sound effects. Creating simple sounds.")
     class DummySound:
         def play(self): pass
     shoot_sound = DummySound()
     explode_sound = DummySound()


# --- Game Classes ---

class Player(pygame.sprite.Sprite):
    def __init__(self):
        pygame.sprite.Sprite.__init__(self)
        self.image = player_img.copy()
        self.rect = self.image.get_rect()
        self.rect.center = (WIDTH // 2, HEIGHT // 2)
        self.speedx = 0
        self.speedy = 0
        self.last_shot_time = pygame.time.get_ticks()
        self.lives = PLAYER_LIVES
        self.hidden = False
        self.hide_timer = pygame.time.get_ticks()
        self.hide_duration = 1000 # milliseconds of invulnerability after hit

    def update(self):
        if self.hidden:
            if pygame.time.get_ticks() - self.hide_timer > self.hide_duration:
                self.hidden = False
                self.image.set_alpha(255) # Make visible
            else:
                 # Flash effect while hidden/invulnerable
                 alpha = (math.sin((pygame.time.get_ticks() - self.hide_timer) / 50) * 100) + 155 # Oscillate alpha
                 self.image.set_alpha(int(alpha))
            return # Don't process movement/shooting while hidden

        # Movement
        self.speedx = 0
        self.speedy = 0
        keystate = pygame.key.get_pressed()
        if keystate[pygame.K_LEFT] or keystate[pygame.K_a]:
            self.speedx = -PLAYER_SPEED
        if keystate[pygame.K_RIGHT] or keystate[pygame.K_d]:
            self.speedx = PLAYER_SPEED
        if keystate[pygame.K_UP] or keystate[pygame.K_w]:
            self.speedy = -PLAYER_SPEED
        if keystate[pygame.K_DOWN] or keystate[pygame.K_s]:
            self.speedy = PLAYER_SPEED

        self.rect.x += self.speedx
        self.rect.y += self.speedy

        # Keep player within bounds
        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > WIDTH:
            self.rect.right = WIDTH
        if self.rect.top < 0:
            self.rect.top = 0
        if self.rect.bottom > HEIGHT:
            self.rect.bottom = HEIGHT

        # Shooting (point towards mouse)
        mouse_x, mouse_y = pygame.mouse.get_pos()
        dx = mouse_x - self.rect.centerx
        dy = mouse_y - self.rect.centery
        angle = math.degrees(math.atan2(-dy, dx)) - 90 # Calculate angle and adjust
        self.image = pygame.transform.rotate(player_img.copy(), angle)
        self.rect = self.image.get_rect(center=self.rect.center) # Update rect after rotation

        if pygame.mouse.get_pressed()[0]: # Left mouse button
             self.shoot()

    def shoot(self):
        now = pygame.time.get_ticks()
        if now - self.last_shot_time > PLAYER_SHOOT_DELAY:
            self.last_shot_time = now
            # Calculate bullet direction based on player's current rotation (which points to mouse)
            mouse_x, mouse_y = pygame.mouse.get_pos()
            dx = mouse_x - self.rect.centerx
            dy = mouse_y - self.rect.centery
            dist = math.sqrt(dx**2 + dy**2)
            if dist > 0:
                # Normalize direction vector
                dir_x = dx / dist
                dir_y = dy / dist
                bullet = Bullet(self.rect.centerx, self.rect.centery, dir_x, dir_y)
                all_sprites.add(bullet)
                bullets.add(bullet)
                shoot_sound.play()

    def hide(self):
        self.hidden = True
        self.hide_timer = pygame.time.get_ticks()
        self.lives -= 1
        self.rect.center = (WIDTH // 2, HEIGHT // 2) # Respawn in center


class Enemy(pygame.sprite.Sprite):
    def __init__(self):
        pygame.sprite.Sprite.__init__(self)
        self.image = enemy_img.copy()
        self.rect = self.image.get_rect()
        # Spawn off-screen
        side = random.choice(['top', 'bottom', 'left', 'right'])
        if side == 'top':
            self.rect.x = random.randrange(WIDTH)
            self.rect.y = random.randrange(-50, -20)
        elif side == 'bottom':
            self.rect.x = random.randrange(WIDTH)
            self.rect.y = random.randrange(HEIGHT + 20, HEIGHT + 50)
        elif side == 'left':
            self.rect.x = random.randrange(-50, -20)
            self.rect.y = random.randrange(HEIGHT)
        elif side == 'right':
            self.rect.x = random.randrange(WIDTH + 20, WIDTH + 50)
            self.rect.y = random.randrange(HEIGHT)

        self.speed = random.uniform(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX)

    def update(self):
        # Move towards the player
        player_pos = player.rect.center
        dx = player_pos[0] - self.rect.centerx
        dy = player_pos[1] - self.rect.centery
        dist = math.sqrt(dx**2 + dy**2)

        if dist > 0:
            # Normalize direction vector
            dir_x = dx / dist
            dir_y = dy / dist
            self.rect.x += dir_x * self.speed
            self.rect.y += dir_y * self.speed

        # Remove if it somehow goes way off screen (shouldn't happen with tracking)
        if self.rect.right < -10 or self.rect.left > WIDTH + 10 or \
           self.rect.bottom < -10 or self.rect.top > HEIGHT + 10:
           self.kill() # Remove sprite from all groups


class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, dir_x, dir_y):
        pygame.sprite.Sprite.__init__(self)
        self.image = bullet_img.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed_x = dir_x * BULLET_SPEED
        self.speed_y = dir_y * BULLET_SPEED

    def update(self):
        self.rect.x += self.speed_x
        self.rect.y += self.speed_y

        # Remove if it goes off screen
        if self.rect.right < 0 or self.rect.left > WIDTH or \
           self.rect.bottom < 0 or self.rect.top > HEIGHT:
           self.kill() # Remove sprite from all groups


class Particle(pygame.sprite.Sprite):
    def __init__(self, center, color):
        pygame.sprite.Sprite.__init__(self)
        size = random.randint(1, 5)
        self.image = pygame.Surface((size, size))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=center)
        self.speedx = random.uniform(-PARTICLE_SPEED_MAX, PARTICLE_SPEED_MAX)
        self.speedy = random.uniform(-PARTICLE_SPEED_MAX, PARTICLE_SPEED_MAX)
        self.spawn_time = pygame.time.get_ticks()
        self.lifetime = random.randint(PARTICLE_LIFETIME // 2, PARTICLE_LIFETIME)

    def update(self):
        self.rect.x += self.speedx
        self.rect.y += self.speedy
        # Simple decay
        self.speedx *= 0.95
        self.speedy *= 0.95
        self.image.set_alpha(max(0, 255 - int((pygame.time.get_ticks() - self.spawn_time) / self.lifetime * 255)))

        if pygame.time.get_ticks() - self.spawn_time > self.lifetime:
            self.kill()


# --- Helper Functions ---

def draw_text(surf, text, size, x, y, color=WHITE):
    font = pygame.font.Font(None, size)
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect()
    text_rect.midtop = (x, y)
    surf.blit(text_surface, text_rect)

def spawn_enemy():
    if len(enemies) < MAX_ENEMIES:
        e = Enemy()
        all_sprites.add(e)
        enemies.add(e)

def show_menu_screen():
    screen.fill(BLACK)
    draw_text(screen, TITLE, 64, WIDTH // 2, HEIGHT // 4)
    draw_text(screen, "Arrow keys or WASD to move, Mouse to aim and shoot", 22, WIDTH // 2, HEIGHT // 2)
    draw_text(screen, "Press any key to start", 18, WIDTH // 2, HEIGHT * 3 // 4)
    if not GEMINI_ENABLED:
         draw_text(screen, "Warning: Gemini API not configured. No AI tips.", 18, WIDTH // 2, HEIGHT - 50, YELLOW)
    pygame.display.flip()
    waiting = True
    while waiting:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYUP:
                waiting = False

def show_game_over_screen(score):
    screen.fill(BLACK)
    draw_text(screen, "GAME OVER", 64, WIDTH // 2, HEIGHT // 4, RED)
    draw_text(screen, f"Final Score: {score}", 36, WIDTH // 2, HEIGHT // 2)
    draw_text(screen, "Press any key to play again", 18, WIDTH // 2, HEIGHT * 3 // 4)
    pygame.display.flip()
    waiting = True
    while waiting:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYUP:
                waiting = False

# --- Gemini Integration Function ---
def trigger_gemini_insight(score):
    global gemini_message, gemini_message_timer, last_gemini_call_time, enemies_destroyed_since_last_gemini

    if not GEMINI_ENABLED or pygame.time.get_ticks() - last_gemini_call_time < GEMINI_CALL_COOLDOWN:
        return # Don't trigger if disabled or on cooldown

    # Prepare a prompt based on game state
    prompt = f"""
    You are an ancient, wise, but slightly quirky AI observer watching a simple 2D space shooter game.
    The player is battling geometric shapes.
    Current Score: {score}
    Enemies on screen: {len(enemies)}
    Lives left: {player.lives}
    Recent activity: Player just destroyed {enemies_destroyed_since_last_gemini} enemies since the last observation.

    Provide a very short, mysterious, or insightful comment (1-2 sentences maximum) related to the game context.
    It could be a tip, a philosophical observation about the shapes, or a cryptic remark.
    Do NOT refer to yourself as an AI or mention 'Gemini'. Use a game-appropriate persona.
    Example style: "The swarm recedes... but they learn." or "Focus is key when the patterns shift."
    """

    print("Attempting to call Gemini...")
    try:
        # Asynchronous call simulation - in a real game you'd use a separate thread/process
        # But for this example, we'll make a quick blocking call and hope it's fast.
        # A proper implementation would need threading to avoid freezing the game loop.
        response = gemini_model.generate_content(prompt)

        # Extract text, handle potential issues like no text in response
        if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
             text_parts = [part.text for part in response.candidates[0].content.parts if part.text]
             if text_parts:
                gemini_message = "Observer: " + " ".join(text_parts).strip()
                gemini_message_timer = GEMINI_MESSAGE_DURATION
                last_gemini_call_time = pygame.time.get_ticks()
                enemies_destroyed_since_last_gemini = 0 # Reset counter
                print(f"Gemini message received: {gemini_message}")
             else:
                 print("Gemini response contained no readable text parts.")
        elif response and response.prompt_feedback:
             print(f"Gemini blocked prompt/response: {response.prompt_feedback}")
             # Optionally display a default "..." message or nothing
             gemini_message = "" # No message if blocked
             gemini_message_timer = 0
        else:
             print("Gemini returned an unexpected response format.")
             gemini_message = ""
             gemini_message_timer = 0

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        # Optionally display a brief error message or nothing
        gemini_message = "Observer: ... (connection lost)"
        gemini_message_timer = 2000 # Display error briefly
        # Don't update last_gemini_call_time if the call failed entirely


# --- Game Initialization ---
all_sprites = pygame.sprite.Group()
enemies = pygame.sprite.Group()
bullets = pygame.sprite.Group()
particles = pygame.sprite.Group()
player = Player() # Player instance created here
all_sprites.add(player)

score = 0
game_state = GAME_STATE_MENU
last_enemy_spawn_time = pygame.time.get_ticks() # Initialize spawn timer


# --- Game Loop ---
running = True
while running:
    clock.tick(FPS) # Keep loop running at the right speed

    # --- Process Input (Events) ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if game_state == GAME_STATE_MENU and event.type == pygame.KEYUP:
             game_state = GAME_STATE_PLAYING
             # Reset game state
             all_sprites.empty()
             enemies.empty()
             bullets.empty()
             particles.empty()
             player = Player()
             all_sprites.add(player)
             score = 0
             last_enemy_spawn_time = pygame.time.get_ticks()
             gemini_message = ""
             gemini_message_timer = 0
             enemies_destroyed_since_last_gemini = 0
             last_gemini_call_time = 0

        if game_state == GAME_STATE_GAME_OVER and event.type == pygame.KEYUP:
             game_state = GAME_STATE_MENU # Go back to menu

    # --- Update (Game Logic) ---
    if game_state == GAME_STATE_PLAYING:
        all_sprites.update()

        # Spawn enemies
        now = pygame.time.get_ticks()
        if now - last_enemy_spawn_time > ENEMY_SPAWN_RATE:
            last_enemy_spawn_time = now
            spawn_enemy()

        # Check for bullet-enemy collisions
        hits = pygame.sprite.groupcollide(enemies, bullets, True, True)
        for enemy in hits:
            score += 10 # Points for destroying enemy
            explode_sound.play()
            # Create particles on enemy death
            num_particles = random.randint(PARTICLE_COUNT_MIN, PARTICLE_COUNT_MAX)
            for _ in range(num_particles):
                 p = Particle(enemy.rect.center, RED) # Particles match enemy color
                 all_sprites.add(p)
                 particles.add(p) # Add to particles group too if needed separately

            enemies_destroyed_since_last_gemini += 1 # Increment counter

        # Trigger Gemini if enough enemies destroyed since last call
        if enemies_destroyed_since_last_gemini >= GEMINI_TRIGGER_ENEMY_COUNT:
             trigger_gemini_insight(score)


        # Check for player-enemy collisions
        # Use pygame.sprite.spritecollide for more specific collision handling
        # If not hidden (invulnerable)
        if not player.hidden:
            hits = pygame.sprite.spritecollide(player, enemies, True, pygame.sprite.collide_circle) # Check circle collision
            for hit in hits:
                player.hide() # Player gets hit, becomes hidden (invulnerable) and respawns
                # Create particles on player hit location
                num_particles = random.randint(PARTICLE_COUNT_MIN, PARTICLE_COUNT_MAX * 2) # More particles for player hit
                for _ in range(num_particles):
                     p = Particle(player.rect.center, BLUE) # Particles match player color
                     all_sprites.add(p)
                     particles.add(p)

                if player.lives <= 0:
                    game_state = GAME_STATE_GAME_OVER


        # Update Gemini message timer
        if gemini_message_timer > 0:
             gemini_message_timer -= clock.get_rawtime() # Decrement by frame time
             if gemini_message_timer <= 0:
                 gemini_message = "" # Clear message when timer runs out


    # --- Draw ---
    screen.fill(BLACK)

    # Draw grid effect (simple lines)
    grid_color = (20, 20, 20) # Dark grey
    grid_spacing = 50
    for x in range(0, WIDTH, grid_spacing):
        pygame.draw.line(screen, grid_color, (x, 0), (x, HEIGHT))
    for y in range(0, HEIGHT, grid_spacing):
        pygame.draw.line(screen, grid_color, (0, y), (WIDTH, y))

    all_sprites.draw(screen)

    if game_state == GAME_STATE_PLAYING:
        # Draw UI
        draw_text(screen, f"Score: {score}", 25, WIDTH // 10, 10)
        draw_text(screen, f"Lives: {player.lives}", 25, WIDTH * 9 // 10, 10)

        # Draw Gemini Message if active
        if gemini_message_timer > 0 and gemini_message:
             draw_text(screen, gemini_message, 20, WIDTH // 2, HEIGHT - 40, YELLOW)


    elif game_state == GAME_STATE_MENU:
        show_menu_screen() # This has its own drawing and loop, but we call it here
        # Reset state slightly so next start is clean
        all_sprites.empty()
        enemies.empty()
        bullets.empty()
        particles.empty()

    elif game_state == GAME_STATE_GAME_OVER:
        show_game_over_screen(score) # This has its own drawing and loop
        # Reset state slightly so next start is clean
        all_sprites.empty()
        enemies.empty()
        bullets.empty()
        particles.empty()


    # --- Update Display ---
    pygame.display.flip()

pygame.quit()