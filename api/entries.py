from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import (
        get_db_connection,
        MOCK_ENTRIES, MOCK_CATEGORIES, MOCK_GAMES, MOCK_USERS
    )
except ImportError:
    from db import (
        get_db_connection,
        MOCK_ENTRIES, MOCK_CATEGORIES, MOCK_GAMES, MOCK_USERS
    )


# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_updated_at(obj):
    """Pastikan objek entry (dict) memiliki updated_at."""
    if not isinstance(obj, dict):
        return obj
    if 'updated_at' not in obj or obj['updated_at'] is None:
        obj['updated_at'] = _now_iso()
    return obj


def _format_duration(seconds):
    """Ubah detik ke format 'Xh Ym Zs'."""
    if seconds is None:
        return None
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


# ---------- Validator ----------
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


def _validate_duration(value):
    """duration BIGINT NOT NULL CHECK (duration > 0) → dalam detik."""
    if value is None:
        return None, "Field 'duration' wajib diisi"
    if not isinstance(value, int) or isinstance(value, bool):
        return None, "Field 'duration' harus berupa integer (detik)"
    if value <= 0:
        return None, "Field 'duration' harus lebih besar dari 0"
    # Batas atas wajar (mis. 100 tahun) untuk mencegah input ngawur
    if value > 100 * 365 * 24 * 3600:
        return None, "Field 'duration' terlalu besar"
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


def _validate_video_url(value):
    """video_url TEXT UNIQUE, nullable."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "Field 'video_url' harus berupa string atau null"
    v = value.strip()
    if v == '':
        return None, None
    if not (v.startswith('http://') or v.startswith('https://')):
        return None, "Field 'video_url' harus berupa URL valid (http/https)"
    if len(v) > 2048:
        return None, "Field 'video_url' maksimal 2048 karakter"
    return v, None


# ---------- Root info modul ----------
@register_route('/entries-info')
def entries_root():
    return jsonify({
        "status": "success",
        "message": "Entries REST API siap digunakan",
        "endpoints": {
            "list_entries":        "GET /api/entries",
            "entry_detail":        "GET /api/entries/<id>",
            "entries_by_category": "GET /api/categories/<category_id>/entries",
            "entries_by_user":     "GET /api/users/<user_id>/entries",
            "create_entry":        "POST /api/entries",
            "update_entry":        "PUT /api/entries/<id>",
            "delete_entry":        "DELETE /api/entries/<id>"
        },
        "fields": {
            "id": "integer (PRIMARY KEY)",
            "user_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "category_id": "integer (NOT NULL, FK categories.id)",
            "duration": "BIGINT (NOT NULL, CHECK duration > 0) — detik",
            "description": "TEXT (nullable)",
            "video_url": "TEXT (UNIQUE, nullable)",
            "updated_at": "TIMESTAMPTZ — diisi otomatis saat INSERT, diperbarui saat UPDATE",
        },
        "notes": {
            "created_at": "Tidak ada di skema entries",
            "verified_at": "Tidak termasuk modul ini — ditangani entry_verifications",
        }
    }), 200


# =========================================================
# 1. GET /api/entries  — list + filter + pagination
# =========================================================
@register_route('/api/entries', methods=['GET'])
def get_entries():
    category_id = request.args.get('category_id', type=int)
    user_id = request.args.get('user_id', type=int)
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
                SELECT e.id, e.user_id, u.username AS runner,
                       e.category_id, c.name AS category_name,
                       g.id AS game_id, g.name AS game_name,
                       e.duration, e.description, e.video_url, e.updated_at
                FROM entries e
                LEFT JOIN users u ON e.user_id = u.id
                LEFT JOIN categories c ON e.category_id = c.id
                LEFT JOIN games g ON c.game_id = g.id
                WHERE 1=1
            """
            params = []
            if category_id:
                query += " AND e.category_id = %s"
                params.append(category_id)
            if user_id:
                query += " AND e.user_id = %s"
                params.append(user_id)
            if game_id:
                query += " AND c.game_id = %s"
                params.append(game_id)
            query += " ORDER BY e.duration ASC OFFSET %s LIMIT %s;"
            params.extend([skip, limit])
            cur.execute(query, params)
            entries = cur.fetchall()
            cur.close()
            conn.close()

            for e in entries:
                e['formatted_duration'] = _format_duration(e['duration'])
            return jsonify({
                "status": "success",
                "total": len(entries),
                "data": entries
            }), 200
        except Exception:
            conn.close()

    # Fallback
    filtered = MOCK_ENTRIES
    if category_id:
        filtered = [e for e in filtered if e.get('category_id') == category_id]
    if user_id:
        filtered = [e for e in filtered if e.get('user_id') == user_id]
    if game_id:
        category_ids = {c['id'] for c in MOCK_CATEGORIES if c.get('game_id') == game_id}
        filtered = [e for e in filtered if e.get('category_id') in category_ids]

    filtered = sorted(filtered, key=lambda x: x.get('duration') or 0)
    paginated = filtered[skip: skip + limit]

    enriched = []
    for e in paginated:
        e_copy = _ensure_updated_at(dict(e))
        runner = next((u['username'] for u in MOCK_USERS if u['id'] == e_copy.get('user_id')), None)
        category = next((c for c in MOCK_CATEGORIES if c['id'] == e_copy.get('category_id')), None)
        game = next((g for g in MOCK_GAMES if g['id'] == (category or {}).get('game_id')), None)
        e_copy['runner'] = runner
        e_copy['category_name'] = category['name'] if category else None
        e_copy['game_id'] = game['id'] if game else None
        e_copy['game_name'] = game['name'] if game else None
        e_copy['formatted_duration'] = _format_duration(e_copy.get('duration'))
        enriched.append(e_copy)

    return jsonify({
        "status": "success",
        "total": len(enriched),
        "data": enriched
    }), 200


# =========================================================
# 2. GET /api/entries/<id>  — detail (tanpa info verifikasi)
# =========================================================
@register_route('/api/entries/<int:entry_id>', methods=['GET'])
def get_entry_detail(entry_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT e.id, e.user_id, u.username AS runner,
                       e.category_id, c.name AS category_name,
                       g.id AS game_id, g.name AS game_name,
                       e.duration, e.description, e.video_url, e.updated_at
                FROM entries e
                LEFT JOIN users u ON e.user_id = u.id
                LEFT JOIN categories c ON e.category_id = c.id
                LEFT JOIN games g ON c.game_id = g.id
                WHERE e.id = %s;
            """, (entry_id,))
            entry = cur.fetchone()
            cur.close()
            conn.close()

            if not entry:
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            entry['formatted_duration'] = _format_duration(entry['duration'])
            return jsonify({"status": "success", "data": entry}), 200
        except Exception:
            conn.close()

    # Fallback
    entry = next((e for e in MOCK_ENTRIES if e['id'] == entry_id), None)
    if not entry:
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    e_copy = _ensure_updated_at(dict(entry))
    runner = next((u['username'] for u in MOCK_USERS if u['id'] == e_copy.get('user_id')), None)
    category = next((c for c in MOCK_CATEGORIES if c['id'] == e_copy.get('category_id')), None)
    game = next((g for g in MOCK_GAMES if g['id'] == (category or {}).get('game_id')), None)

    e_copy['runner'] = runner
    e_copy['category_name'] = category['name'] if category else None
    e_copy['game_id'] = game['id'] if game else None
    e_copy['game_name'] = game['name'] if game else None
    e_copy['formatted_duration'] = _format_duration(e_copy.get('duration'))
    return jsonify({"status": "success", "data": e_copy}), 200


# =========================================================
# 3. GET /api/categories/<category_id>/entries  — filter per kategori
# =========================================================
@register_route('/api/categories/<int:category_id>/entries', methods=['GET'])
def get_entries_by_category(category_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan kategori ada
            cur.execute("SELECT id, name, game_id FROM categories WHERE id = %s;", (category_id,))
            category = cur.fetchone()
            if not category:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            cur.execute("""
                SELECT e.id, e.user_id, u.username AS runner,
                       e.duration, e.description, e.video_url, e.updated_at
                FROM entries e
                LEFT JOIN users u ON e.user_id = u.id
                WHERE e.category_id = %s
                ORDER BY e.duration ASC;
            """, (category_id,))
            entries = cur.fetchall()
            cur.close()
            conn.close()

            for e in entries:
                e['formatted_duration'] = _format_duration(e['duration'])
            return jsonify({
                "status": "success",
                "category_id": category_id,
                "category_name": category['name'],
                "total": len(entries),
                "data": entries
            }), 200
        except Exception:
            conn.close()

    # Fallback
    category = next((c for c in MOCK_CATEGORIES if c['id'] == category_id), None)
    if not category:
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 404

    entries = [e for e in MOCK_ENTRIES if e.get('category_id') == category_id]
    entries = sorted(entries, key=lambda x: x.get('duration') or 0)

    enriched = []
    for e in entries:
        e_copy = _ensure_updated_at(dict(e))
        e_copy['runner'] = next(
            (u['username'] for u in MOCK_USERS if u['id'] == e_copy.get('user_id')), None
        )
        e_copy['formatted_duration'] = _format_duration(e_copy.get('duration'))
        enriched.append(e_copy)

    return jsonify({
        "status": "success",
        "category_id": category_id,
        "category_name": category['name'],
        "total": len(enriched),
        "data": enriched
    }), 200


# =========================================================
# 4. GET /api/users/<user_id>/entries  — filter per user
# =========================================================
@register_route('/api/users/<int:user_id>/entries', methods=['GET'])
def get_entries_by_user(user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, username FROM users WHERE id = %s;", (user_id,))
            user = cur.fetchone()
            if not user:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            cur.execute("""
                SELECT e.id, e.category_id, c.name AS category_name,
                       g.id AS game_id, g.name AS game_name,
                       e.duration, e.description, e.video_url, e.updated_at
                FROM entries e
                LEFT JOIN categories c ON e.category_id = c.id
                LEFT JOIN games g ON c.game_id = g.id
                WHERE e.user_id = %s
                ORDER BY e.duration ASC;
            """, (user_id,))
            entries = cur.fetchall()
            cur.close()
            conn.close()

            for e in entries:
                e['formatted_duration'] = _format_duration(e['duration'])
            return jsonify({
                "status": "success",
                "user_id": user_id,
                "username": user['username'],
                "total": len(entries),
                "data": entries
            }), 200
        except Exception:
            conn.close()

    # Fallback
    user = next((u for u in MOCK_USERS if u['id'] == user_id), None)
    if not user:
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    entries = [e for e in MOCK_ENTRIES if e.get('user_id') == user_id]
    entries = sorted(entries, key=lambda x: x.get('duration') or 0)

    enriched = []
    for e in entries:
        e_copy = _ensure_updated_at(dict(e))
        category = next((c for c in MOCK_CATEGORIES if c['id'] == e_copy.get('category_id')), None)
        game = next((g for g in MOCK_GAMES if g['id'] == (category or {}).get('game_id')), None)
        e_copy['category_name'] = category['name'] if category else None
        e_copy['game_id'] = game['id'] if game else None
        e_copy['game_name'] = game['name'] if game else None
        e_copy['formatted_duration'] = _format_duration(e_copy.get('duration'))
        enriched.append(e_copy)

    return jsonify({
        "status": "success",
        "user_id": user_id,
        "username": user['username'],
        "total": len(enriched),
        "data": enriched
    }), 200


# =========================================================
# 5. POST /api/entries  — create (updated_at otomatis)
# =========================================================
@register_route('/api/entries', methods=['POST'])
def create_entry():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang TIDAK boleh dikirim dari client
    if 'updated_at' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'updated_at' tidak boleh di-set manual; diisi otomatis oleh server"
        }), 400

    user_id, err = _validate_int(data.get('user_id'), 'user_id', nullable=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    category_id, err = _validate_int(data.get('category_id'), 'category_id', nullable=False)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    duration, err = _validate_duration(data.get('duration'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    description, err = _validate_description(data.get('description'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    video_url, err = _validate_video_url(data.get('video_url'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan kategori ada
            cur.execute("SELECT id, name, game_id FROM categories WHERE id = %s;", (category_id,))
            category = cur.fetchone()
            if not category:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 400

            # Pastikan user ada (jika dikirim)
            if user_id is not None:
                cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"User dengan ID {user_id} tidak ditemukan"
                    }), 400

            # Cek UNIQUE video_url
            if video_url is not None:
                cur.execute("SELECT id FROM entries WHERE video_url = %s;", (video_url,))
                if cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": "video_url sudah digunakan oleh entry lain"
                    }), 409

            # updated_at TIDAK dikirim → diisi DEFAULT now()
            cur.execute("""
                INSERT INTO entries (user_id, category_id, duration, description, video_url)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, user_id, category_id, duration, description,
                          video_url, updated_at;
            """, (user_id, category_id, duration, description, video_url))
            new_entry = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()

            new_entry['category_name'] = category['name']
            new_entry['formatted_duration'] = _format_duration(new_entry['duration'])
            return jsonify({
                "status": "success",
                "message": "Entry berhasil ditambahkan",
                "data": new_entry
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan entry: {str(e)}"
            }), 500

    # Fallback
    category = next((c for c in MOCK_CATEGORIES if c['id'] == category_id), None)
    if not category:
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 400

    if user_id is not None and not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 400

    if video_url is not None and any(e.get('video_url') == video_url for e in MOCK_ENTRIES):
        return jsonify({
            "status": "error",
            "message": "video_url sudah digunakan oleh entry lain"
        }), 409

    new_id = max([e['id'] for e in MOCK_ENTRIES], default=0) + 1
    new_entry = {
        "id": new_id,
        "user_id": user_id,
        "category_id": category_id,
        "category_name": category['name'],
        "duration": duration,
        "description": description,
        "video_url": video_url,
        "updated_at": _now_iso(),   # ← diisi otomatis saat INSERT
        "formatted_duration": _format_duration(duration),
    }
    MOCK_ENTRIES.append(new_entry)
    return jsonify({
        "status": "success",
        "message": "Entry berhasil ditambahkan",
        "data": new_entry
    }), 201


# =========================================================
# 6. PUT /api/entries/<id>  — update (updated_at selalu berubah)
# =========================================================
@register_route('/api/entries/<int:entry_id>', methods=['PUT'])
def update_entry(entry_id):
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang TIDAK boleh dikirim dari client
    if 'updated_at' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'updated_at' tidak boleh di-set manual; diisi otomatis oleh server"
        }), 400
    if 'id' in data and data['id'] != entry_id:
        return jsonify({
            "status": "error",
            "message": "Field 'id' tidak boleh diubah melalui endpoint ini"
        }), 400

    # Field yang diizinkan berubah
    allowed = ('duration', 'description', 'video_url')
    if not any(f in data for f in allowed):
        return jsonify({
            "status": "error",
            "message": f"Minimal satu field harus diisi: {', '.join(allowed)}"
        }), 400

    # Validasi per-field
    duration_value = None
    if 'duration' in data:
        duration_value, err = _validate_duration(data['duration'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    desc_value = None
    if 'description' in data:
        desc_value, err = _validate_description(data['description'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    video_value = None
    if 'video_url' in data:
        video_value, err = _validate_video_url(data['video_url'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entries WHERE id = %s;", (entry_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            # Cek duplikasi video_url jika diubah
            if video_value is not None:
                cur.execute(
                    "SELECT id FROM entries WHERE video_url = %s AND id <> %s;",
                    (video_value, entry_id)
                )
                if cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": "video_url sudah digunakan oleh entry lain"
                    }), 409

            new_duration = duration_value if duration_value is not None else existing['duration']
            new_desc = desc_value if 'description' in data else existing['description']
            new_video = video_value if 'video_url' in data else existing['video_url']

            # updated_at di-set eksplisit via now() → dijamin berubah
            cur.execute("""
                UPDATE entries
                SET duration = %s,
                    description = %s,
                    video_url = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, user_id, category_id, duration, description,
                          video_url, updated_at;
            """, (new_duration, new_desc, new_video, entry_id))
            updated = cur.fetchone()

            # Enrich category_name
            cur.execute("SELECT name FROM categories WHERE id = %s;", (updated['category_id'],))
            c = cur.fetchone()
            updated['category_name'] = c['name'] if c else None
            updated['formatted_duration'] = _format_duration(updated['duration'])

            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Entry berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui entry: {str(e)}"
            }), 500

    # Fallback
    entry = next((e for e in MOCK_ENTRIES if e['id'] == entry_id), None)
    if not entry:
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    if video_value is not None:
        if any(
            e['id'] != entry_id and e.get('video_url') == video_value
            for e in MOCK_ENTRIES
        ):
            return jsonify({
                "status": "error",
                "message": "video_url sudah digunakan oleh entry lain"
            }), 409
        entry['video_url'] = video_value

    if duration_value is not None:
        entry['duration'] = duration_value

    if 'description' in data:
        entry['description'] = desc_value

    _ensure_updated_at(entry)
    entry['updated_at'] = _now_iso()   # ← selalu berubah saat PUT
    entry['formatted_duration'] = _format_duration(entry.get('duration'))

    return jsonify({
        "status": "success",
        "message": "Entry berhasil diperbarui",
        "data": entry
    }), 200


# =========================================================
# 7. DELETE /api/entries/<id>
# =========================================================
@register_route('/api/entries/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entries WHERE id = %s;", (entry_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            # Catatan skema:
            # - entry_verifications.entry_id ON DELETE CASCADE → otomatis terhapus.
            # - Modul ini TIDAK mengelola entry_verifications; CASCADE ditangani DB.
            cur.execute("DELETE FROM entries WHERE id = %s;", (entry_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Entry ID {entry_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus entry: {str(e)}"
            }), 500

    # Fallback
    entry_idx = next((i for i, e in enumerate(MOCK_ENTRIES) if e['id'] == entry_id), None)
    if entry_idx is None:
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    MOCK_ENTRIES.pop(entry_idx)
    return jsonify({
        "status": "success",
        "message": f"Entry ID {entry_id} berhasil dihapus"
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
    app.run(debug=True, port=5007)