import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

# In-memory mock data jika belum terhubung ke PostgreSQL / Supabase

# ... kode existing ...

MOCK_USERS = [
    {
        "id": 1,
        "username": "runner_one",
        "display_name": "Runner One",
        "email": "runner1@example.com",
        "created_at": "2024-01-01T08:00:00+00:00",
        "updated_at": "2024-06-15T12:30:00+00:00",
    },
    {
        "id": 2,
        "username": "runner_two",
        "display_name": "Runner Two",
        "email": "runner2@example.com",
        "created_at": "2024-02-10T09:15:00+00:00",
        "updated_at": "2024-06-20T14:45:00+00:00",
    },
    {
        "id": 3,
        "username": "speed_master",
        "display_name": "Speed Master",
        "email": "speed@example.com",
        "created_at": "2024-03-05T07:20:00+00:00",
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
]

MOCK_USER_SETTINGS = [
    {
        "user_id": 1,
        "display_theme": "dark",
        "updated_at": "2024-06-15T12:30:00+00:00",
    },
    {
        "user_id": 2,
        "display_theme": "light",
        "updated_at": "2024-06-20T14:45:00+00:00",
    },
    {
        "user_id": 3,
        "display_theme": "system",
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
]

MOCK_USER_PROFILES = [
    {
        "user_id": 1,
        "bio": "Speedrunner sejak 2018, fokus kategori Any%.",
        "avatar_url": "https://example.com/avatars/runner1.png",
        "twitch_url": "https://twitch.tv/runner_one",
        "youtube_url": "https://youtube.com/@runnerone",
        "social_media_url": "https://twitter.com/runner_one",
        "updated_at": "2024-06-15T12:30:00+00:00",
    },
    {
        "user_id": 2,
        "bio": "Suka kategori 100% dan glitchless.",
        "avatar_url": None,
        "twitch_url": None,
        "youtube_url": "https://youtube.com/@runnertwo",
        "social_media_url": None,
        "updated_at": "2024-06-20T14:45:00+00:00",
    },
    {
        "user_id": 3,
        "bio": None,
        "avatar_url": None,
        "twitch_url": "https://twitch.tv/speed_master",
        "youtube_url": None,
        "social_media_url": None,
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
]

MOCK_GENRES = [
    {
        "id": 1,
        "name": "Platformer",
        "creator_id": 1,
        "latest_editor_id": 1,
        "created_at": "2024-01-01T08:00:00+00:00",
        "updated_at": "2024-06-15T12:30:00+00:00",
    },
    {
        "id": 2,
        "name": "RPG",
        "creator_id": 2,
        "latest_editor_id": 2,
        "created_at": "2024-02-10T09:15:00+00:00",
        "updated_at": "2024-06-20T14:45:00+00:00",
    },
    {
        "id": 3,
        "name": "FPS",
        "creator_id": 1,
        "latest_editor_id": 3,
        "created_at": "2024-03-05T07:20:00+00:00",
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
    {
        "id": 4,
        "name": "Racing",
        "creator_id": 3,
        "latest_editor_id": 1,
        "created_at": "2024-04-12T11:00:00+00:00",
        "updated_at": "2024-07-10T08:30:00+00:00",
    },
]

MOCK_GAMES = [
    {
        "id": 1,
        "name": "Super Mario 64",
        "genre_id": 1,
        "creator_id": 1,
        "latest_editor_id": 1,
        "description": "Classic 3D platformer",
        "created_at": "2024-01-05T10:00:00+00:00",
        "updated_at": "2024-06-20T11:30:00+00:00",
    },
    {
        "id": 2,
        "name": "Final Fantasy VII",
        "genre_id": 2,
        "creator_id": 2,
        "latest_editor_id": 2,
        "description": "Legendary JRPG",
        "created_at": "2024-02-12T09:00:00+00:00",
        "updated_at": "2024-06-25T15:45:00+00:00",
    },
    {
        "id": 3,
        "name": "Counter-Strike 1.6",
        "genre_id": 3,
        "creator_id": 1,
        "latest_editor_id": 3,
        "description": "Classic competitive FPS",
        "created_at": "2024-03-08T08:20:00+00:00",
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
]

MOCK_CATEGORIES = [
    {
        "id": 1,
        "name": "Any%",
        "game_id": 1,
        "creator_id": 1,
        "latest_editor_id": 1,
        "created_at": "2024-01-10T09:00:00+00:00",
        "updated_at": "2024-06-20T11:30:00+00:00",
    },
    {
        "id": 2,
        "name": "100%",
        "game_id": 1,
        "creator_id": 1,
        "latest_editor_id": 2,
        "created_at": "2024-02-15T10:15:00+00:00",
        "updated_at": "2024-06-25T15:45:00+00:00",
    },
    {
        "id": 3,
        "name": "Any% Glitchless",
        "game_id": 3,
        "creator_id": 2,
        "latest_editor_id": 2,
        "created_at": "2024-03-20T08:40:00+00:00",
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
]

MOCK_ENTRIES = [
    {
        "id": 1,
        "user_id": 1,
        "category_id": 1,
        "duration": 3725,
        "description": "Run bersih tanpa reset",
        "video_url": "https://youtu.be/abc123",
        "updated_at": "2024-06-15T12:30:00+00:00",
    },
    {
        "id": 2,
        "user_id": 2,
        "category_id": 1,
        "duration": 3912,
        "description": "Sedikit choke di akhir",
        "video_url": "https://youtu.be/def456",
        "updated_at": "2024-06-20T14:45:00+00:00",
    },
    {
        "id": 3,
        "user_id": 1,
        "category_id": 2,
        "duration": 12890,
        "description": "100% full run",
        "video_url": "https://youtu.be/ghi789",
        "updated_at": "2024-07-01T10:00:00+00:00",
    },
]

MOCK_ENTRY_VERIFICATIONS = [
    {
        "entry_id": 1,
        "verifier_id": 3,
        "verified_at": "2024-06-16T10:00:00+00:00",
        "note": "Terverifikasi via VOD lengkap.",
    },
    {
        "entry_id": 3,
        "verifier_id": 2,
        "verified_at": "2024-07-02T09:30:00+00:00",
        "note": "Durasi sesuai dengan timer in-game.",
    },
]

MOCK_CATEGORY_MODERATORS = [
    {"user_id": 1, "category_id": 1},
    {"user_id": 2, "category_id": 1},
    {"user_id": 3, "category_id": 2},
    {"user_id": 1, "category_id": 3},
]

MOCK_GAME_ADMINISTRATORS = [
    {"user_id": 1, "game_id": 1},
    {"user_id": 3, "game_id": 1},
    {"user_id": 2, "game_id": 2},
    {"user_id": 1, "game_id": 3},
]

def get_db_connection():
    """Mengembalikan koneksi PostgreSQL jika DATABASE_URL tersedia."""
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"[DB Warning] Gagal koneksi ke PostgreSQL: {e}. Menggunakan fallback mock data.")
        return None
