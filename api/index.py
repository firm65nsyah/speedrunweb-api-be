import urllib.parse
from flask import Flask, jsonify, request

try:
    from api.db import get_db_connection, MOCK_GAMES, MOCK_GENRES, MOCK_CATEGORIES, MOCK_ENTRIES
except ImportError:
    from db import get_db_connection, MOCK_GAMES, MOCK_GENRES, MOCK_CATEGORIES, MOCK_ENTRIES

app = Flask(__name__)
app.url_map.strict_slashes = False

class VercelPathMiddleware:
    """Memperbaiki routing WSGI di serverless Vercel."""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = urllib.parse.parse_qs(environ.get('QUERY_STRING', ''))
        if '__path' in qs and qs['__path']:
            target_path = qs['__path'][0]
            if not target_path.startswith('/'):
                target_path = '/' + target_path
            environ['PATH_INFO'] = target_path
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

# Helper decorator untuk mendaftarkan rute dengan prefix / dan /api
def register_route(rule, **options):
    def decorator(f):
        app.route(rule, **options)(f)
        if rule.startswith('/api/'):
            app.route(rule[4:], **options)(f)
        elif rule == '/api':
            app.route('/', **options)(f)
        elif not rule.startswith('/api') and rule != '/':
            app.route('/api' + rule, **options)(f)
        return f
    return decorator


# --- 1. Root & Health ---
@register_route('/')
def root():
    return jsonify({
        "status": "success",
        "message": "Speedrun Leaderboard REST API siap digunakan",
        "endpoints": {
            "health": "/api/health",
            "genres": "/api/genres",
            "games": "/api/games",
            "categories": "/api/categories",
            "leaderboard": "/api/leaderboard"
        }
    }), 200

@register_route('/api/health')
def health_check():
    conn = get_db_connection()
    db_status = "connected" if conn else "fallback_mock_data"
    if conn:
        conn.close()
    return jsonify({
        "status": "healthy",
        "database": db_status
    }), 200


# --- 2. Genres (Read Only) ---
@register_route('/api/genres')
def get_genres():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM genres ORDER BY id ASC;")
            genres = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({"status": "success", "total": len(genres), "data": genres}), 200
        except Exception:
            conn.close()
    return jsonify({"status": "success", "total": len(MOCK_GENRES), "data": MOCK_GENRES}), 200


# --- 3. Games (Full CRUD) ---
@register_route('/api/games', methods=['GET'])
def get_games():
    search = request.args.get('search', '').strip().lower()
    genre_id = request.args.get('genre_id', type=int)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            query = """
                SELECT g.id, g.name, g.genre_id, ge.name AS genre_name, g.description
                FROM games g
                LEFT JOIN genres ge ON g.genre_id = ge.id
                WHERE 1=1
            """
            params = []
            if search:
                query += " AND LOWER(g.name) LIKE %s"
                params.append(f"%{search}%")
            if genre_id:
                query += " AND g.genre_id = %s"
                params.append(genre_id)
            query += " ORDER BY g.id ASC;"
            cur.execute(query, params)
            games = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({"status": "success", "total": len(games), "data": games}), 200
        except Exception:
            conn.close()

    # Fallback ke mock data
    filtered = MOCK_GAMES
    if search:
        filtered = [g for g in filtered if search in g['name'].lower()]
    if genre_id:
        filtered = [g for g in filtered if g.get('genre_id') == genre_id]
    return jsonify({"status": "success", "total": len(filtered), "data": filtered}), 200


@register_route('/api/games/<int:game_id>', methods=['GET'])
def get_game_detail(game_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT g.id, g.name, g.genre_id, ge.name AS genre_name, g.description
                FROM games g
                LEFT JOIN genres ge ON g.genre_id = ge.id
                WHERE g.id = %s;
            """, (game_id,))
            game = cur.fetchone()
            if not game:
                cur.close()
                conn.close()
                return jsonify({"status": "error", "message": f"Game dengan ID {game_id} tidak ditemukan"}), 404

            cur.execute("SELECT id, name FROM categories WHERE game_id = %s ORDER BY id ASC;", (game_id,))
            categories = cur.fetchall()
            cur.close()
            conn.close()
            game['categories'] = categories
            return jsonify({"status": "success", "data": game}), 200
        except Exception:
            conn.close()

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({"status": "error", "message": f"Game dengan ID {game_id} tidak ditemukan"}), 404
    game_copy = dict(game)
    game_copy['categories'] = [c for c in MOCK_CATEGORIES if c['game_id'] == game_id]
    return jsonify({"status": "success", "data": game_copy}), 200


@register_route('/api/games', methods=['POST'])
def create_game():
    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Request body harus berupa JSON object"}), 400

    name = str(data.get('name', '')).strip()
    genre_id = data.get('genre_id')
    description = str(data.get('description', '')).strip()

    if not name:
        return jsonify({"status": "error", "message": "Field 'name' wajib diisi"}), 400
    if not genre_id or not isinstance(genre_id, int):
        return jsonify({"status": "error", "message": "Field 'genre_id' harus berupa integer valid"}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Cek genre ada
            cur.execute("SELECT id, name FROM genres WHERE id = %s;", (genre_id,))
            genre = cur.fetchone()
            if not genre:
                cur.close()
                conn.close()
                return jsonify({"status": "error", "message": f"Genre dengan ID {genre_id} tidak ditemukan"}), 400

            cur.execute("""
                INSERT INTO games (name, genre_id, description)
                VALUES (%s, %s, %s)
                RETURNING id, name, genre_id, description;
            """, (name, genre_id, description))
            new_game = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            new_game['genre_name'] = genre['name']
            return jsonify({
                "status": "success",
                "message": "Game berhasil ditambahkan",
                "data": new_game
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": f"Gagal menambahkan game: {str(e)}"}), 500

    # Fallback
    genre = next((g for g in MOCK_GENRES if g['id'] == genre_id), None)
    if not genre:
        return jsonify({"status": "error", "message": f"Genre dengan ID {genre_id} tidak ditemukan"}), 400

    new_id = max([g['id'] for g in MOCK_GAMES], default=0) + 1
    new_game = {
        "id": new_id,
        "name": name,
        "genre_id": genre_id,
        "genre_name": genre['name'],
        "description": description
    }
    MOCK_GAMES.append(new_game)
    return jsonify({
        "status": "success",
        "message": "Game berhasil ditambahkan",
        "data": new_game
    }), 201


@register_route('/api/games/<int:game_id>', methods=['PUT'])
def update_game(game_id):
    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Request body harus berupa JSON object"}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM games WHERE id = %s;", (game_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({"status": "error", "message": f"Game dengan ID {game_id} tidak ditemukan"}), 404

            name = data.get('name', existing['name'])
            genre_id = data.get('genre_id', existing['genre_id'])
            description = data.get('description', existing['description'])

            cur.execute("""
                UPDATE games
                SET name = %s, genre_id = %s, description = %s, updated_at = now()
                WHERE id = %s
                RETURNING id, name, genre_id, description;
            """, (name, genre_id, description, game_id))
            updated = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Game berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": str(e)}), 500

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({"status": "error", "message": f"Game dengan ID {game_id} tidak ditemukan"}), 404

    if 'name' in data and data['name']:
        game['name'] = str(data['name']).strip()
    if 'genre_id' in data and isinstance(data['genre_id'], int):
        genre = next((g for g in MOCK_GENRES if g['id'] == data['genre_id']), None)
        if genre:
            game['genre_id'] = data['genre_id']
            game['genre_name'] = genre['name']
    if 'description' in data:
        game['description'] = str(data['description']).strip()

    return jsonify({
        "status": "success",
        "message": "Game berhasil diperbarui",
        "data": game
    }), 200


@register_route('/api/games/<int:game_id>', methods=['DELETE'])
def delete_game(game_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM games WHERE id = %s;", (game_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({"status": "error", "message": f"Game dengan ID {game_id} tidak ditemukan"}), 404

            # Cek relasi kategori
            cur.execute("SELECT COUNT(*) AS count FROM categories WHERE game_id = %s;", (game_id,))
            res = cur.fetchone()
            if res and res['count'] > 0:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Tidak dapat menghapus game ID {game_id} karena masih memiliki {res['count']} kategori speedrun aktif (Relational Integrity Conflict)."
                }), 409

            cur.execute("DELETE FROM games WHERE id = %s;", (game_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Game ID {game_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": str(e)}), 500

    # Fallback
    game_idx = next((i for i, g in enumerate(MOCK_GAMES) if g['id'] == game_id), None)
    if game_idx is None:
        return jsonify({"status": "error", "message": f"Game dengan ID {game_id} tidak ditemukan"}), 404

    # Cek relasi kategori di mock
    cat_count = sum(1 for c in MOCK_CATEGORIES if c['game_id'] == game_id)
    if cat_count > 0:
        return jsonify({
            "status": "error",
            "message": f"Tidak dapat menghapus game ID {game_id} karena masih memiliki {cat_count} kategori speedrun aktif (Relational Integrity Conflict)."
        }), 409

    deleted = MOCK_GAMES.pop(game_idx)
    return jsonify({
        "status": "success",
        "message": f"Game '{deleted['name']}' berhasil dihapus"
    }), 200


# --- 4. Categories & Leaderboard ---
@register_route('/api/categories')
def get_categories():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.name, c.game_id, g.name AS game_name
                FROM categories c
                JOIN games g ON c.game_id = g.id
                ORDER BY c.id ASC;
            """)
            categories = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({"status": "success", "total": len(categories), "data": categories}), 200
        except Exception:
            conn.close()

    return jsonify({"status": "success", "total": len(MOCK_CATEGORIES), "data": MOCK_CATEGORIES}), 200


@register_route('/api/leaderboard')
def get_leaderboard():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    e.id,
                    u.username AS runner,
                    g.name AS game,
                    c.name AS category,
                    e.duration AS duration_seconds,
                    CONCAT(FLOOR(e.duration / 60), 'm ', (e.duration %% 60), 's') AS formatted_time,
                    e.video_url
                FROM entries e
                LEFT JOIN users u ON e.user_id = u.id
                LEFT JOIN categories c ON e.category_id = c.id
                LEFT JOIN games g ON c.game_id = g.id
                ORDER BY e.duration ASC;
            """)
            entries = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({"status": "success", "total": len(entries), "data": entries}), 200
        except Exception:
            conn.close()

    return jsonify({"status": "success", "total": len(MOCK_ENTRIES), "data": MOCK_ENTRIES}), 200


# Error Handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint tidak ditemukan (404)"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"status": "error", "message": "HTTP Method tidak diizinkan (405)"}), 405

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal Server Error (500)"}), 500
