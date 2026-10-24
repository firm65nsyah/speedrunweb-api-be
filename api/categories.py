from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import (
        get_db_connection,
        MOCK_CATEGORIES, MOCK_GAMES, MOCK_USERS,
        MOCK_ENTRIES, MOCK_ENTRY_VERIFICATIONS
    )
except ImportError:
    from db import (
        get_db_connection,
        MOCK_CATEGORIES, MOCK_GAMES, MOCK_USERS,
        MOCK_ENTRIES, MOCK_ENTRY_VERIFICATIONS
    )


# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_timestamps(obj):
    """Pastikan objek category (dict) memiliki created_at & updated_at."""
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


# ---------- Root info modul ----------
@register_route('/categories-info')
def categories_root():
    return jsonify({
        "status": "success",
        "message": "Categories REST API siap digunakan",
        "endpoints": {
            "list_categories":     "GET /api/categories",
            "category_detail":     "GET /api/categories/<id>",
            "categories_by_game":  "GET /api/games/<game_id>/categories",
            "create_category":     "POST /api/categories",
            "update_category":     "PUT /api/categories/<id>",
            "delete_category":     "DELETE /api/categories/<id>"
        },
        "fields": {
            "id": "integer (PRIMARY KEY)",
            "game_id": "integer (NOT NULL, FK games.id, ON DELETE CASCADE)",
            "creator_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "latest_editor_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "name": "string (NOT NULL)",
            "created_at": "TIMESTAMPTZ — diisi otomatis saat INSERT",
            "updated_at": "TIMESTAMPTZ — diperbarui otomatis saat UPDATE",
        },
        "notes": {
            "verified_at": "Tidak relevan untuk categories",
        }
    }), 200


# =========================================================
# 1. GET /api/categories  — list + filter + search + pagination
# =========================================================
@register_route('/api/categories', methods=['GET'])
def get_categories():
    search = request.args.get('search', '').strip().lower()
    game_id = request.args.get('game_id', type=int)
    skip = request.args.get('skip', default=0, type=int)
    limit = request.args.get('limit', default=100, type=int)
    if skip < 0: skip = 0
    if limit < 1 or limit > 500: limit = 100

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            query = """
                SELECT c.id, c.name, c.game_id, g.name AS game_name,
                       c.creator_id, c.latest_editor_id,
                       c.created_at, c.updated_at
                FROM categories c
                LEFT JOIN games g ON c.game_id = g.id
                WHERE 1=1
            """
            params = []
            if search:
                query += " AND LOWER(c.name) LIKE %s"
                params.append(f"%{search}%")
            if game_id:
                query += " AND c.game_id = %s"
                params.append(game_id)
            query += " ORDER BY c.id ASC OFFSET %s LIMIT %s;"
            params.extend([skip, limit])
            cur.execute(query, params)
            categories = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "total": len(categories),
                "data": categories
            }), 200
        except Exception:
            conn.close()

    # Fallback
    filtered = MOCK_CATEGORIES
    if search:
        filtered = [c for c in filtered if search in c['name'].lower()]
    if game_id:
        filtered = [c for c in filtered if c.get('game_id') == game_id]
    paginated = filtered[skip: skip + limit]

    enriched = []
    for c in paginated:
        c_copy = _ensure_timestamps(dict(c))
        game = next((g for g in MOCK_GAMES if g['id'] == c_copy.get('game_id')), None)
        c_copy['game_name'] = game['name'] if game else None
        enriched.append(c_copy)

    return jsonify({
        "status": "success",
        "total": len(enriched),
        "data": enriched
    }), 200


# =========================================================
# 2. GET /api/categories/<id>  — detail (+ entries terkait)
# =========================================================
@register_route('/api/categories/<int:category_id>', methods=['GET'])
def get_category_detail(category_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.name, c.game_id, g.name AS game_name,
                       c.creator_id, c.latest_editor_id,
                       c.created_at, c.updated_at
                FROM categories c
                LEFT JOIN games g ON c.game_id = g.id
                WHERE c.id = %s;
            """, (category_id,))
            category = cur.fetchone()
            if not category:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            # Daftar entries terkait (ringkas + verified_at) — urut tercepat
            cur.execute("""
                SELECT e.id, u.username AS runner,
                       e.duration, e.video_url, e.updated_at AS entry_updated_at,
                       ev.verified_at
                FROM entries e
                LEFT JOIN users u ON e.user_id = u.id
                LEFT JOIN entry_verifications ev ON ev.entry_id = e.id
                WHERE e.category_id = %s
                ORDER BY e.duration ASC;
            """, (category_id,))
            entries = cur.fetchall()
            cur.close()
            conn.close()

            category['entries'] = entries
            category['total_entries'] = len(entries)
            return jsonify({"status": "success", "data": category}), 200
        except Exception:
            conn.close()

    # Fallback
    category = next((c for c in MOCK_CATEGORIES if c['id'] == category_id), None)
    if not category:
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 404

    cat_copy = _ensure_timestamps(dict(category))
    game = next((g for g in MOCK_GAMES if g['id'] == cat_copy.get('game_id')), None)
    cat_copy['game_name'] = game['name'] if game else None

    related_entries = []
    for e in MOCK_ENTRIES:
        if e.get('category_id') == category_id:
            runner = next(
                (u['username'] for u in MOCK_USERS if u['id'] == e.get('user_id')),
                None
            )
            verif = next(
                (v for v in MOCK_ENTRY_VERIFICATIONS if v['entry_id'] == e['id']),
                None
            )
            related_entries.append({
                "id": e['id'],
                "runner": runner,
                "duration": e.get('duration'),
                "video_url": e.get('video_url'),
                "entry_updated_at": e.get('updated_at'),   # timestamp entry
                "verified_at": verif['verified_at'] if verif else None,  # timestamp verifikasi
            })
    related_entries.sort(key=lambda x: x.get('duration') or 0)
    cat_copy['entries'] = related_entries
    cat_copy['total_entries'] = len(related_entries)
    return jsonify({"status": "success", "data": cat_copy}), 200


# =========================================================
# 3. GET /api/games/<game_id>/categories  — filter per game
# =========================================================
@register_route('/api/games/<int:game_id>/categories', methods=['GET'])
def get_categories_by_game(game_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan game ada
            cur.execute("SELECT id, name FROM games WHERE id = %s;", (game_id,))
            game = cur.fetchone()
            if not game:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Game dengan ID {game_id} tidak ditemukan"
                }), 404

            cur.execute("""
                SELECT c.id, c.name, c.game_id, c.creator_id, c.latest_editor_id,
                       c.created_at, c.updated_at
                FROM categories c
                WHERE c.game_id = %s
                ORDER BY c.id ASC;
            """, (game_id,))
            categories = cur.fetchall()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "game_id": game_id,
                "game_name": game['name'],
                "total": len(categories),
                "data": categories
            }), 200
        except Exception:
            conn.close()

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 404

    categories = [
        _ensure_timestamps(dict(c))
        for c in MOCK_CATEGORIES if c.get('game_id') == game_id
    ]
    return jsonify({
        "status": "success",
        "game_id": game_id,
        "game_name": game['name'],
        "total": len(categories),
        "data": categories
    }), 200


# =========================================================
# 4. POST /api/categories  — create (created_at & updated_at otomatis)
# =========================================================
@register_route('/api/categories', methods=['POST'])
def create_category():
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

    game_id, err = _validate_int(data.get('game_id'), 'game_id', nullable=False)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    creator_id, err = _validate_int(data.get('creator_id'), 'creator_id', nullable=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan game ada
            cur.execute("SELECT id, name FROM games WHERE id = %s;", (game_id,))
            game = cur.fetchone()
            if not game:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Game dengan ID {game_id} tidak ditemukan"
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

            # Cek duplikasi nama dalam game yang sama
            cur.execute("""
                SELECT id FROM categories
                WHERE game_id = %s AND LOWER(name) = LOWER(%s);
            """, (game_id, name))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category '{name}' sudah ada di game ID {game_id}"
                }), 409

            # created_at & updated_at TIDAK dikirim → diisi DEFAULT now()
            cur.execute("""
                INSERT INTO categories (name, game_id, creator_id, latest_editor_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, name, game_id, creator_id, latest_editor_id,
                          created_at, updated_at;
            """, (name, game_id, creator_id, creator_id))
            new_category = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()

            new_category['game_name'] = game['name']
            return jsonify({
                "status": "success",
                "message": "Category berhasil ditambahkan",
                "data": new_category
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan category: {str(e)}"
            }), 500

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 400

    if creator_id is not None and not any(u['id'] == creator_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {creator_id} tidak ditemukan"
        }), 400

    if any(
        c['game_id'] == game_id and c['name'].lower() == name.lower()
        for c in MOCK_CATEGORIES
    ):
        return jsonify({
            "status": "error",
            "message": f"Category '{name}' sudah ada di game ID {game_id}"
        }), 409

    new_id = max([c['id'] for c in MOCK_CATEGORIES], default=0) + 1
    now = _now_iso()
    new_category = {
        "id": new_id,
        "name": name,
        "game_id": game_id,
        "game_name": game['name'],
        "creator_id": creator_id,
        "latest_editor_id": creator_id,  # diisi = creator saat INSERT
        "created_at": now,               # ← diisi otomatis saat INSERT
        "updated_at": now,               # ← diisi otomatis saat INSERT (= created_at)
    }
    MOCK_CATEGORIES.append(new_category)
    return jsonify({
        "status": "success",
        "message": "Category berhasil ditambahkan",
        "data": new_category
    }), 201


# =========================================================
# 5. PUT /api/categories/<id>  — update (updated_at selalu berubah)
# =========================================================
@register_route('/api/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
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
    if 'id' in data and data['id'] != category_id:
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
    allowed = ('name', 'latest_editor_id')
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

    editor_value = None
    if 'latest_editor_id' in data:
        editor_value, err = _validate_int(data['latest_editor_id'], 'latest_editor_id', nullable=True)
        if err:
            return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM categories WHERE id = %s;", (category_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            # Cek duplikasi nama dalam game yang sama
            if name_value is not None and name_value.lower() != existing['name'].lower():
                cur.execute("""
                    SELECT id FROM categories
                    WHERE game_id = %s AND LOWER(name) = LOWER(%s) AND id <> %s;
                """, (existing['game_id'], name_value, category_id))
                if cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"Category '{name_value}' sudah ada di game ID {existing['game_id']}"
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
                UPDATE categories
                SET name = %s,
                    latest_editor_id = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, name, game_id, creator_id, latest_editor_id,
                          created_at, updated_at;
            """, (new_name, new_editor, category_id))
            updated = cur.fetchone()

            # Enrich game_name
            cur.execute("SELECT name FROM games WHERE id = %s;", (updated['game_id'],))
            g = cur.fetchone()
            updated['game_name'] = g['name'] if g else None

            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Category berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui category: {str(e)}"
            }), 500

    # Fallback
    category = next((c for c in MOCK_CATEGORIES if c['id'] == category_id), None)
    if not category:
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 404

    if name_value is not None:
        if any(
            c['id'] != category_id
            and c['game_id'] == category['game_id']
            and c['name'].lower() == name_value.lower()
            for c in MOCK_CATEGORIES
        ):
            return jsonify({
                "status": "error",
                "message": f"Category '{name_value}' sudah ada di game ID {category['game_id']}"
            }), 409
        category['name'] = name_value

    if 'latest_editor_id' in data:
        if editor_value is not None and not any(u['id'] == editor_value for u in MOCK_USERS):
            return jsonify({
                "status": "error",
                "message": f"User dengan ID {editor_value} tidak ditemukan"
            }), 400
        category['latest_editor_id'] = editor_value

    # created_at tetap; updated_at selalu berubah saat PUT
    _ensure_timestamps(category)
    category['updated_at'] = _now_iso()

    return jsonify({
        "status": "success",
        "message": "Category berhasil diperbarui",
        "data": category
    }), 200


# =========================================================
# 6. DELETE /api/categories/<id>  — RESTRICT ke entries
# =========================================================
@register_route('/api/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM categories WHERE id = %s;", (category_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            # entries.category_id NOT NULL tanpa ON DELETE → RESTRICT
            cur.execute("SELECT COUNT(*) AS count FROM entries WHERE category_id = %s;", (category_id,))
            res = cur.fetchone()
            entry_count = res['count'] if res else 0

            if entry_count > 0:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": (
                        f"Tidak dapat menghapus category ID {category_id} karena masih memiliki "
                        f"{entry_count} entry terkait (Relational Integrity Conflict). "
                        f"Hapus atau pindahkan entry terlebih dahulu."
                    )
                }), 409

            cur.execute("DELETE FROM categories WHERE id = %s;", (category_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Category ID {category_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus category: {str(e)}"
            }), 500

    # Fallback
    cat_idx = next((i for i, c in enumerate(MOCK_CATEGORIES) if c['id'] == category_id), None)
    if cat_idx is None:
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 404

    entry_count = sum(1 for e in MOCK_ENTRIES if e.get('category_id') == category_id)
    if entry_count > 0:
        return jsonify({
            "status": "error",
            "message": (
                f"Tidak dapat menghapus category ID {category_id} karena masih memiliki "
                f"{entry_count} entry terkait (Relational Integrity Conflict). "
                f"Hapus atau pindahkan entry terlebih dahulu."
            )
        }), 409

    deleted = MOCK_CATEGORIES.pop(cat_idx)
    return jsonify({
        "status": "success",
        "message": f"Category '{deleted['name']}' berhasil dihapus"
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
    app.run(debug=True, port=5006)