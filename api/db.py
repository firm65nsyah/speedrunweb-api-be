import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

# In-memory mock data jika belum terhubung ke PostgreSQL / Supabase
MOCK_GENRES = [
    {"id": 1, "name": "Platformer"},
    {"id": 2, "name": "Action RPG"},
    {"id": 3, "name": "Metroidvania"},
    {"id": 4, "name": "Sandbox"},
    {"id": 5, "name": "FPS"}
]

MOCK_GAMES = [
    {
        "id": 1,
        "name": "Super Mario 64",
        "genre_id": 1,
        "genre_name": "Platformer",
        "description": "3D platformer klasik di Nintendo 64."
    },
    {
        "id": 2,
        "name": "Celeste",
        "genre_id": 1,
        "genre_name": "Platformer",
        "description": "Precision platformer tentang mendaki gunung Celeste."
    },
    {
        "id": 3,
        "name": "Hollow Knight",
        "genre_id": 3,
        "genre_name": "Metroidvania",
        "description": "Petualangan serangga di kerajaan Hallownest."
    },
    {
        "id": 4,
        "name": "Elden Ring",
        "genre_id": 2,
        "genre_name": "Action RPG",
        "description": "Action RPG open world karya FromSoftware."
    },
    {
        "id": 5,
        "name": "Minecraft",
        "genre_id": 4,
        "genre_name": "Sandbox",
        "description": "Game sandbox survival dan membangun dunia balok."
    }
]

MOCK_CATEGORIES = [
    {"id": 1, "game_id": 1, "name": "120 Star"},
    {"id": 2, "game_id": 1, "name": "16 Star"},
    {"id": 3, "game_id": 2, "name": "Any%"},
    {"id": 4, "game_id": 3, "name": "Any% (No Major Glitches)"},
    {"id": 5, "game_id": 4, "name": "Any% Unrestricted"},
    {"id": 6, "game_id": 5, "name": "Any% Random Seed"}
]

MOCK_ENTRIES = [
    {
        "id": 1,
        "runner": "speedy_sam",
        "game": "Super Mario 64",
        "category": "16 Star",
        "duration_seconds": 912,
        "formatted_time": "15m 12s",
        "video_url": "https://youtube.com/watch?v=sample1"
    },
    {
        "id": 2,
        "runner": "chrono_ninja",
        "game": "Celeste",
        "category": "Any%",
        "duration_seconds": 1645,
        "formatted_time": "27m 25s",
        "video_url": "https://youtube.com/watch?v=sample2"
    },
    {
        "id": 3,
        "runner": "glitch_master",
        "game": "Hollow Knight",
        "category": "Any% (No Major Glitches)",
        "duration_seconds": 2040,
        "formatted_time": "34m 00s",
        "video_url": "https://youtube.com/watch?v=sample3"
    }
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
