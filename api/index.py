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


import api.users, api.user_settings, api.user_profiles, api.genres, api.games, api.categories, api.entries, api.entry_verifications, api.category_moderators, api.game_administrators

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
