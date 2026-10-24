from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import get_db_connection, MOCK_GENRES, MOCK_GAMES, MOCK_USERS
except ImportError:
    from db import get_db_connection, MOCK_GENRES, MOCK_GAMES, MOCK_USERS


# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_timestamps(obj):
    """
    Pastikan objek genre (dict) memiliki created_at & updated_at.
    Dipakai untuk mock lama yang mungkin belum punya field ini.
    """
    if not isinstance(obj, dict):
        return obj
    if 'created_at' not in obj or obj['created_at'] is None:
        obj['created_at'] = _now_iso()
    if 'updated_at' not in obj or obj['updated_at'] is None:
        obj['updated_at'] = obj['created_at']
    return obj


# ---------- Validator ----------
def _validate_name(value):
    """Validasi name (VARCHAR NOT NULL di SQL)."""
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


def _validate_user_id(value, field_name):
    """Validasi referensi user_id (nullable, FK ke users.id)."""
    if value is None:
        return None, None
    if not isinstance(value, int) or isinstance(value, bool):
        return None, f"Field '{field_name}' harus berupa integer atau null"
    if value <= 0:
        return None, f"Field '{field_name}' harus berupa integer positif"
    return value, None


# ---------- Root info modul ----------
@register_route('/genres-info')
def genres_root():
    return jsonify({
        "status": "success",
        "message": "Genres REST API siap digunakan",
        "endpoints": {
            "list_genres":  "GET /api/genres",
            "genre_detail": "GET /api/genres/<id>",
            "create_genre": "POST /api/genres",
            "update_genre": "PUT /api/genres/<id>",
            "delete_genre": "DELETE /api/genres/<id>"
        },
        "fields": {
            "id": "integer (PRIMARY KEY)",
            "creator_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "latest_editor_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "name": "string (NOT NULL)",
            "created_at": "TIMESTAMPTZ — diisi otomatis saat INSERT",
            "updated_at": "TIMESTAMPTZ — diperbarui otomatis saat UPDATE",
        },
        "notes": {
            "verified_at": "Tidak relevan untuk genres",
        }
    }), 200


# =========================================================
# 1. GET /api/genres  — list + search + pagination
# =========================================================
@register_route('/api/genres', methods=['GET'])
def get_genres():
    search = request.args.get('search', '').strip().lower()
    skip = request.args.get('skip', default=0, type=int)
    limit = request.args.get('limit', default=100, type=int)
    if skip < 0: skip = 0
    if limit < 1 or limit > 500: limit = 100

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            query = """
                SELECT id, name, creator_id, latest_editor_id,
                       created_at, updated_at
                FROM genres
                WHERE 1=1
            """
            params = []
            if search:
                query += " AND LOWER(name) LIKE %s"
                params.append(f"%{search}%")
            query += " ORDER BY id ASC OFFSET %s LIMIT %s;"
            params.extend([skip, limit])
            cur.execute(query, params)
            genres = cur.fetchall()
            cur.close()
            conn.close()
            # created_at & updated_at sudah termasuk dari SELECT
            return jsonify({
                "status": "success",
                "total": len(genres),
                "data": genres
            }), 200
        except Exception:
            conn.close()

    # Fallback
    filtered = MOCK_GENRES
    if search:
        filtered = [g for g in filtered if search in g['name'].lower()]
    paginated = filtered[skip: skip + limit]
    paginated = [_ensure_timestamps(dict(g)) for g in paginated]
    return jsonify({
        "status": "success",
        "total": len(paginated),
        "data": paginated
    }), 200


# =========================================================
# 2. GET /api/genres/<id>  — detail (+ daftar games terkait)
# =========================================================
@register_route('/api/genres/<int:genre_id>', methods=['GET'])
def get_genre_detail(genre_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, creator_id, latest_editor_id,
                       created_at, updated_at
                FROM genres WHERE id = %s;
            """, (genre_id,))
            genre = cur.fetchone()
            if not genre:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Genre dengan ID {genre_id} tidak ditemukan"
                }), 404

            # Daftar game terkait (ringkas) — sertakan created_at & updated_at
            cur.execute("""
                SELECT id, name, created_at, updated_at
                FROM games
                WHERE genre_id = %s
                ORDER BY id ASC;
            """, (genre_id,))
            games = cur.fetchall()
            cur.close()
            conn.close()

            genre['games'] = games
            genre['total_games'] = len(games)
            return jsonify({"status": "success", "data": genre}), 200
        except Exception:
            conn.close()

    # Fallback
    genre = next((g for g in MOCK_GENRES if g['id'] == genre_id), None)
    if not genre:
        return jsonify({
            "status": "error",
            "message": f"Genre dengan ID {genre_id} tidak ditemukan"
        }), 404

    genre_copy = _ensure_timestamps(dict(genre))
    related_games = []
    for g in MOCK_GAMES:
        if g.get('genre_id') == genre_id:
            related_games.append(_ensure_timestamps({
                "id": g['id'],
                "name": g['name'],
                "created_at": g.get('created_at'),
                "updated_at": g.get('updated_at'),
            }))
    genre_copy['games'] = related_games
    genre_copy['total_games'] = len(related_games)
    return jsonify({"status": "success", "data": genre_copy}), 200


# =========================================================
# 3. POST /api/genres  — create (created_at & updated_at otomatis)
# =========================================================
@register_route('/api/genres', methods=['POST'])
def create_genre():
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

    creator_id, err = _validate_user_id(data.get('creator_id'), 'creator_id')
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan creator_id valid jika dikirim
            if creator_id is not None:
                cur.execute("SELECT id FROM users WHERE id = %s;", (creator_id,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"User dengan ID {creator_id} tidak ditemukan"
                    }), 400

            # Cek duplikasi nama (case-insensitive)
            cur.execute("SELECT id FROM genres WHERE LOWER(name) = LOWER(%s);", (name,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Genre dengan nama '{name}' sudah ada"
                }), 409

            # created_at & updated_at TIDAK dikirim → diisi DEFAULT now()
            cur.execute("""
                INSERT INTO genres (name, creator_id, latest_editor_id)
                VALUES (%s, %s, %s)
                RETURNING id, name, creator_id, latest_editor_id,
                          created_at, updated_at;
            """, (name, creator_id, creator_id))
            new_genre = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Genre berhasil ditambahkan",
                "data": new_genre
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan genre: {str(e)}"
            }), 500

    # Fallback
    if creator_id is not None and not any(u['id'] == creator_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {creator_id} tidak ditemukan"
        }), 400

    if any(g['name'].lower() == name.lower() for g in MOCK_GENRES):
        return jsonify({
            "status": "error",
            "message": f"Genre dengan nama '{name}' sudah ada"
        }), 409

    new_id = max([g['id'] for g in MOCK_GENRES], default=0) + 1
    now = _now_iso()
    new_genre = {
        "id": new_id,
        "name": name,
        "creator_id": creator_id,
        "latest_editor_id": creator_id,  # diisi = creator saat INSERT
        "created_at": now,               # ← diisi otomatis saat INSERT
        "updated_at": now,               # ← diisi otomatis saat INSERT (= created_at)
    }
    MOCK_GENRES.append(new_genre)
    return jsonify({
        "status": "success",
        "message": "Genre berhasil ditambahkan",
        "data": new_genre
    }), 201


# =========================================================
# 4. PUT /api/genres/<id>  — update (updated_at selalu berubah)
# =========================================================
@register_route('/api/genres/<int:genre_id>', methods=['PUT'])
def update_genre(genre_id):
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
    if 'id' in data and data['id'] != genre_id:
        return jsonify({
            "status": "error",
            "message": "Field 'id' tidak boleh diubah melalui endpoint ini"
        }), 400
    if 'creator_id' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'creator_id' tidak boleh diubah setelah dibuat; gunakan 'latest_editor_id'"
        }), 400

    # Minimal satu field yang dapat di-update harus dikirim
    allowed = ('name', 'latest_editor_id')
    if not any(f in data for f in allowed):
        return jsonify({
            "status": "error",
            "message": f"Minimal satu field harus diisi: {', '.join(allowed)}"
        }), 400

    # Validasi per-field jika dikirim
    name_value = None
    if 'name' in data:
        name_value, err = _validate_name(data['name'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    editor_value = None
    if 'latest_editor_id' in data:
        editor_value, err = _validate_user_id(data['latest_editor_id'], 'latest_editor_id')
        if err:
            return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM genres WHERE id = %s;", (genre_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Genre dengan ID {genre_id} tidak ditemukan"
                }), 404

            # Cek duplikasi nama (jika diubah)
            if name_value is not None and name_value.lower() != existing['name'].lower():
                cur.execute(
                    "SELECT id FROM genres WHERE LOWER(name) = LOWER(%s) AND id <> %s;",
                    (name_value, genre_id)
                )
                if cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"Genre dengan nama '{name_value}' sudah ada"
                    }), 409

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
            new_editor = (
                editor_value if 'latest_editor_id' in data
                else existing['latest_editor_id']
            )

            # updated_at di-set eksplisit via now() → dijamin berubah
            cur.execute("""
                UPDATE genres
                SET name = %s,
                    latest_editor_id = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, name, creator_id, latest_editor_id,
                          created_at, updated_at;
            """, (new_name, new_editor, genre_id))
            updated = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Genre berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui genre: {str(e)}"
            }), 500

    # Fallback
    genre = next((g for g in MOCK_GENRES if g['id'] == genre_id), None)
    if not genre:
        return jsonify({
            "status": "error",
            "message": f"Genre dengan ID {genre_id} tidak ditemukan"
        }), 404

    if name_value is not None:
        if any(
            g['id'] != genre_id and g['name'].lower() == name_value.lower()
            for g in MOCK_GENRES
        ):
            return jsonify({
                "status": "error",
                "message": f"Genre dengan nama '{name_value}' sudah ada"
            }), 409
        genre['name'] = name_value

    if 'latest_editor_id' in data:
        if editor_value is not None and not any(u['id'] == editor_value for u in MOCK_USERS):
            return jsonify({
                "status": "error",
                "message": f"User dengan ID {editor_value} tidak ditemukan"
            }), 400
        genre['latest_editor_id'] = editor_value

    # created_at tetap; updated_at selalu berubah saat PUT
    _ensure_timestamps(genre)
    genre['updated_at'] = _now_iso()

    return jsonify({
        "status": "success",
        "message": "Genre berhasil diperbarui",
        "data": genre
    }), 200


# =========================================================
# 5. DELETE /api/genres/<id>
# =========================================================
@register_route('/api/genres/<int:genre_id>', methods=['DELETE'])
def delete_genre(genre_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM genres WHERE id = %s;", (genre_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Genre dengan ID {genre_id} tidak ditemukan"
                }), 404

            # games.genre_id NOT NULL tanpa ON DELETE → RESTRICT
            cur.execute("SELECT COUNT(*) AS count FROM games WHERE genre_id = %s;", (genre_id,))
            res = cur.fetchone()
            game_count = res['count'] if res else 0

            if game_count > 0:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": (
                        f"Tidak dapat menghapus genre ID {genre_id} karena masih memiliki "
                        f"{game_count} game terkait (Relational Integrity Conflict)."
                    )
                }), 409

            cur.execute("DELETE FROM genres WHERE id = %s;", (genre_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Genre ID {genre_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus genre: {str(e)}"
            }), 500

    # Fallback
    genre_idx = next((i for i, g in enumerate(MOCK_GENRES) if g['id'] == genre_id), None)
    if genre_idx is None:
        return jsonify({
            "status": "error",
            "message": f"Genre dengan ID {genre_id} tidak ditemukan"
        }), 404

    game_count = sum(1 for g in MOCK_GAMES if g.get('genre_id') == genre_id)
    if game_count > 0:
        return jsonify({
            "status": "error",
            "message": (
                f"Tidak dapat menghapus genre ID {genre_id} karena masih memiliki "
                f"{game_count} game terkait (Relational Integrity Conflict)."
            )
        }), 409

    deleted = MOCK_GENRES.pop(genre_idx)
    return jsonify({
        "status": "success",
        "message": f"Genre '{deleted['name']}' berhasil dihapus"
    }), 200


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
    app.run(debug=True, port=5004)