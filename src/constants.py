SAMPLE_RATE = 44100
BLOCK_SIZE = 512
CHANNELS = 2

MAX_DISTANCE = 10.0
COLLISION_THRESHOLD = 1.5
COLLISION_DUCK_RATIO = 0.5

SPHERE_RADIUS = 0.3
GRID_SIZE = 20
GRID_SPACING = 1.0

UI_REFRESH_MS = 16  # ~60fps

TRACK_COLORS = [
    (0, 229, 255),    # cyan
    (255, 109, 0),    # orange
    (170, 0, 255),    # purple
    (118, 255, 3),    # green
    (255, 23, 68),    # red
    (255, 214, 0),    # yellow
]

DEFAULT_POSITIONS = [
    (-2.0, 0.0, 2.0),
    (2.0, 0.0, 2.0),
    (-2.0, 0.0, -2.0),
    (2.0, 0.0, -2.0),
    (0.0, 2.0, 0.0),
    (0.0, -2.0, 0.0),
]
