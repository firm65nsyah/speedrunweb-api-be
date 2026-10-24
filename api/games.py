from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import (
        get_db_connection,
        MOCK_GAMES, MOCK_GENRES, MOCK_CATEGORIES, MOCK_USERS
    )
except ImportError:
    from db import (
        get_db_connection,
        MOCK_GAMES, MOCK_GENRES, MOCK_CATEGORIES, MOCK_USERS
    )


# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_timestamps(obj):
    """Pastikan objek game (dict) memiliki created_at & updated_at."""
    if not isinstance(obj, dict):
        return obj
    if 'created_at' not in obj or obj['created_at'] is None:
        obj['created_at'] = _now_iso()
    if 'updated_at' not in obj or obj['updated_at'] is None:
        obj['updated_at'] = obj['created_at']
    return obj


# ---------- Validator ----------
def _validate_name(value):
    if value is None:
        return None, "Field 'name' wajib diisi"
    if not isinstance(value, str):
        return None, "Field 'name' harus berupa string"
    v = value.strip()
    if not v:
        return None, "Field 'name' tidak boleh kosong"
    if len(v) > 100:
        return None, "Field 'name' maksimal 100 karakter"
    return v, None


def _validate_int(value, field_name, nullable=False):
    if value is None:
        if nullable:
            return None, None
        return None, f"Field '{field_name}' wajib diisi"
    if not isinstance(value, int) or isinstance(value, bool):
        return None, f"Field '{field_name}' harus berupa integer"
    if value <= 0:
        return None, f"Field '{field_name}' harus berupa integer positif"
    return value, None


def _validate_description(value):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "Field 'description' harus berupa string atau null"
    v = value.strip()
    if v == '':
        return None, None
    if len(v) > 10000:
        return None, "Field 'description' maksimal 10000 karakter"
    return v, None


# ---------- Root info modul ----------
@register_route('/games-info')
def games_root():
    return jsonify({
        "status": "success",
        "message": "Games REST API siap digunakan",
        "endpoints": {
            "list_games":  "GET /api/games",
            "game_detail": "GET /api/games/<id>",
            "create_game": "POST /api/games",
            "update_game": "PUT /api/games/<id>",
            "delete_game": "DELETE /api/games/<id>"
        },
        "fields": {
            "id": "integer (PRIMARY KEY)",
            "genre_id": "integer (NOT NULL, FK genres.id)",
            "creator_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "latest_editor_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "name": "string (NOT NULL)",
            "description": "TEXT (nullable)",
            "created_at": "TIMESTAMPTZ — diisi otomatis saat INSERT",
            "updated_at": "TIMESTAMPTZ — diperbarui otomatis saat UPDATE",
        },
        "notes": {
            "verified_at": "Tidak relevan untuk games",
        }
    }), 200


# =========================================================
# 1. GET /api/games  — list + search + filter + pagination
# =========================================================
@register_route('/api/games', methods=['GET'])
def get_games():
    search = request.args.get('search', '').strip().lower()
    genre_id = request.args.get('genre_id', type=int)
    skip = request.args.get('skip', default=0, type=int)
    limit = request.args.get('limit', default=100, type=int)
    if skip < 0: skip = 0
    if limit < 1 or limit > 500: limit = 100

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            query = """
                SELECT g.id, g.name, g.genre_id, ge.name AS genre_name,
                       g.description, g.creator_id, g.latest_editor_id,
                       g.created_at, g.updated_at
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
            query += " ORDER BY g.id ASC OFFSET %s LIMIT %s;"
            params.extend([skip, limit])
            cur.execute(query, params)
            games = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "total": len(games),
                "data": games
            }), 200
        except Exception:
            conn.close()

    # Fallback
    filtered = MOCK_GAMES
    if search:
        filtered = [g for g in filtered if search in g['name'].lower()]
    if genre_id:
        filtered = [g for g in filtered if g.get('genre_id') == genre_id]
    paginated = filtered[skip: skip + limit]

    enriched = []
    for g in paginated:
        g_copy = _ensure_timestamps(dict(g))
        genre = next((ge for ge in MOCK_GENRES if ge['id'] == g_copy.get('genre_id')), None)
        g_copy['genre_name'] = genre['name'] if genre else None
        enriched.append(g_copy)

    return jsonify({
        "status": "success",
        "total": len(enriched),
        "data": enriched
    }), 200


# =========================================================
# 2. GET /api/games/<id>  — detail (+ daftar categories terkait)
# =========================================================
@register_route('/api/games/<int:game_id>', methods=['GET'])
def get_game_detail(game_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT g.id, g.name, g.genre_id, ge.name AS genre_name,
                       g.description, g.creator_id, g.latest_editor_id,
                       g.created_at, g.updated_at
                FROM games g
                LEFT JOIN genres ge ON g.genre_id = ge.id
                WHERE g.id = %s;
            """, (game_id,))
            game = cur.fetchone()
            if not game:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Game dengan ID {game_id} tidak ditemukan"
                }), 404

            # Daftar kategori terkait (ringkas) — sertakan created_at & updated_at
            cur.execute("""
                SELECT id, name, created_at, updated_at
                FROM categories
                WHERE game_id = %s
                ORDER BY id ASC;
            """, (game_id,))
            categories = cur.fetchall()
            cur.close()
            conn.close()

            game['categories'] = categories
            game['total_categories'] = len(categories)
            return jsonify({"status": "success", "data": game}), 200
        except Exception:
            conn.close()

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 404

    game_copy = _ensure_timestamps(dict(game))
    genre = next((ge for ge in MOCK_GENRES if ge['id'] == game_copy.get('genre_id')), None)
    game_copy['genre_name'] = genre['name'] if genre else None

    related_categories = []
    for c in MOCK_CATEGORIES:
        if c.get('game_id') == game_id:
            related_categories.append(_ensure_timestamps({
                "id": c['id'],
                "name": c['name'],
                "created_at": c.get('created_at'),
                "updated_at": c.get('updated_at'),
            }))
    game_copy['categories'] = related_categories
    game_copy['total_categories'] = len(related_categories)
    return jsonify({"status": "success", "data": game_copy}), 200


# =========================================================
# 3. POST /api/games  — create (created_at & updated_at otomatis)
# =========================================================
@register_route('/api/games', methods=['POST'])
def create_game():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang TIDAK boleh dikirim dari client
    if 'created_at' in data or 'updated_at' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'created_at' dan 'updated_at' tidak boleh di-set manual; diisi otomatis oleh server"
        }), 400

    name, err = _validate_name(data.get('name'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    genre_id, err = _validate_int(data.get('genre_id'), 'genre_id', nullable=False)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    creator_id, err = _validate_int(data.get('creator_id'), 'creator_id', nullable=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    description, err = _validate_description(data.get('description'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan genre ada
            cur.execute("SELECT id, name FROM genres WHERE id = %s;", (genre_id,))
            genre = cur.fetchone()
            if not genre:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Genre dengan ID {genre_id} tidak ditemukan"
                }), 400

            # Pastikan creator valid jika dikirim
            if creator_id is not None:
                cur.execute("SELECT id FROM users WHERE id = %s;", (creator_id,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"User dengan ID {creator_id} tidak ditemukan"
                    }), 400

            # created_at & updated_at TIDAK dikirim → diisi DEFAULT now()
            cur.execute("""
                INSERT INTO games (name, genre_id, description, creator_id, latest_editor_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, genre_id, description, creator_id,
                          latest_editor_id, created_at, updated_at;
            """, (name, genre_id, description, creator_id, creator_id))
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
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan game: {str(e)}"
            }), 500

    # Fallback
    genre = next((ge for ge in MOCK_GENRES if ge['id'] == genre_id), None)
    if not genre:
        return jsonify({
            "status": "error",
            "message": f"Genre dengan ID {genre_id} tidak ditemukan"
        }), 400

    if creator_id is not None and not any(u['id'] == creator_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {creator_id} tidak ditemukan"
        }), 400

    new_id = max([g['id'] for g in MOCK_GAMES], default=0) + 1
    now = _now_iso()
    new_game = {
        "id": new_id,
        "name": name,
        "genre_id": genre_id,
        "genre_name": genre['name'],
        "description": description,
        "creator_id": creator_id,
        "latest_editor_id": creator_id,  # diisi = creator saat INSERT
        "created_at": now,               # ← diisi otomatis saat INSERT
        "updated_at": now,               # ← diisi otomatis saat INSERT (= created_at)
    }
    MOCK_GAMES.append(new_game)
    return jsonify({
        "status": "success",
        "message": "Game berhasil ditambahkan",
        "data": new_game
    }), 201


# =========================================================
# 4. PUT /api/games/<id>  — update (updated_at selalu berubah)
# =========================================================
@register_route('/api/games/<int:game_id>', methods=['PUT'])
def update_game(game_id):
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang TIDAK boleh dikirim dari client
    if 'created_at' in data or 'updated_at' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'created_at' dan 'updated_at' tidak boleh di-set manual; diisi otomatis oleh server"
        }), 400
    if 'id' in data and data['id'] != game_id:
        return jsonify({
            "status": "error",
            "message": "Field 'id' tidak boleh diubah melalui endpoint ini"
        }), 400
    if 'creator_id' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'creator_id' tidak boleh diubah setelah dibuat; gunakan 'latest_editor_id'"
        }), 400

    # Minimal satu field yang dapat di-update
    allowed = ('name', 'genre_id', 'description', 'latest_editor_id')
    if not any(f in data for f in allowed):
        return jsonify({
            "status": "error",
            "message": f"Minimal satu field harus diisi: {', '.join(allowed)}"
        }), 400

    # Validasi per-field kalau dikirim
    name_value = None
    if 'name' in data:
        name_value, err = _validate_name(data['name'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    genre_value = None
    if 'genre_id' in data:
        genre_value, err = _validate_int(data['genre_id'], 'genre_id', nullable=False)
        if err:
            return jsonify({"status": "error", "message": err}), 400

    desc_value = None
    if 'description' in data:
        desc_value, err = _validate_description(data['description'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    editor_value = None
    if 'latest_editor_id' in data:
        editor_value, err = _validate_int(data['latest_editor_id'], 'latest_editor_id', nullable=True)
        if err:
            return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM games WHERE id = %s;", (game_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Game dengan ID {game_id} tidak ditemukan"
                }), 404

            # Validasi genre baru jika diubah
            if genre_value is not None:
                cur.execute("SELECT id FROM genres WHERE id = %s;", (genre_value,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"Genre dengan ID {genre_value} tidak ditemukan"
                    }), 400

            # Validasi editor baru jika diubah
            if editor_value is not None:
                cur.execute("SELECT id FROM users WHERE id = %s;", (editor_value,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"User dengan ID {editor_value} tidak ditemukan"
                    }), 400

            new_name = name_value if name_value is not None else existing['name']
            new_genre = genre_value if genre_value is not None else existing['genre_id']
            new_desc = desc_value if 'description' in data else existing['description']
            new_editor = editor_value if 'latest_editor_id' in data else existing['latest_editor_id']

            # updated_at di-set eksplisit via now() → dijamin berubah
            cur.execute("""
                UPDATE games
                SET name = %s,
                    genre_id = %s,
                    description = %s,
                    latest_editor_id = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, name, genre_id, description, creator_id,
                          latest_editor_id, created_at, updated_at;
            """, (new_name, new_genre, new_desc, new_editor, game_id))
            updated = cur.fetchone()

            # Enrich genre_name
            cur.execute("SELECT name FROM genres WHERE id = %s;", (updated['genre_id'],))
            g = cur.fetchone()
            updated['genre_name'] = g['name'] if g else None

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
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui game: {str(e)}"
            }), 500

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 404

    if name_value is not None:
        game['name'] = name_value

    if genre_value is not None:
        genre = next((ge for ge in MOCK_GENRES if ge['id'] == genre_value), None)
        if not genre:
            return jsonify({
                "status": "error",
                "message": f"Genre dengan ID {genre_value} tidak ditemukan"
            }), 400
        game['genre_id'] = genre_value
        game['genre_name'] = genre['name']

    if 'description' in data:
        game['description'] = desc_value

    if 'latest_editor_id' in data:
        if editor_value is not None and not any(u['id'] == editor_value for u in MOCK_USERS):
            return jsonify({
                "status": "error",
                "message": f"User dengan ID {editor_value} tidak ditemukan"
            }), 400
        game['latest_editor_id'] = editor_value

    # created_at tetap; updated_at selalu berubah saat PUT
    _ensure_timestamps(game)
    game['updated_at'] = _now_iso()

    return jsonify({
        "status": "success",
        "message": "Game berhasil diperbarui",
        "data": game
    }), 200


# =========================================================
# 5. DELETE /api/games/<id>  — CASCADE ke categories
# =========================================================
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
                return jsonify({
                    "status": "error",
                    "message": f"Game dengan ID {game_id} tidak ditemukan"
                }), 404

            # Skema: categories.game_id ON DELETE CASCADE
            cur.execute("SELECT COUNT(*) AS count FROM categories WHERE game_id = %s;", (game_id,))
            res = cur.fetchone()
            cat_count = res['count'] if res else 0

            cur.execute("DELETE FROM games WHERE id = %s;", (game_id,))
            conn.commit()
            cur.close()
            conn.close()

            message = f"Game ID {game_id} berhasil dihapus"
            if cat_count > 0:
                message += f" (beserta {cat_count} kategori terkait via CASCADE)"
            return jsonify({"status": "success", "message": message}), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus game: {str(e)}"
            }), 500

    # Fallback
    game_idx = next((i for i, g in enumerate(MOCK_GAMES) if g['id'] == game_id), None)
    if game_idx is None:
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 404

    # Simulasi CASCADE: hapus kategori terkait dari mock
    cat_count = sum(1 for c in MOCK_CATEGORIES if c['game_id'] == game_id)
    MOCK_CATEGORIES[:] = [c for c in MOCK_CATEGORIES if c['game_id'] != game_id]

    deleted = MOCK_GAMES.pop(game_idx)
    message = f"Game '{deleted['name']}' berhasil dihapus"
    if cat_count > 0:
        message += f" (beserta {cat_count} kategori terkait via CASCADE)"
    return jsonify({"status": "success", "message": message}), 200


# --- Error Handlers ---
@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint tidak ditemukan (404)"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"status": "error", "message": "HTTP Method tidak diizinkan (405)"}), 405

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal Server Error (500)"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5005)