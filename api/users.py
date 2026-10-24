from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import get_db_connection, MOCK_USERS
except ImportError:
    from db import get_db_connection, MOCK_USERS

# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_timestamps(obj):
    """
    Pastikan objek user (dict) memiliki created_at & updated_at.
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
def _validate_username(value):
    if value is None:
        return None, "Field 'username' wajib diisi"
    if not isinstance(value, str):
        return None, "Field 'username' harus berupa string"
    v = value.strip()
    if not (3 <= len(v) <= 30):
        return None, "Field 'username' harus 3-30 karakter"
    return v, None


def _validate_display_name(value):
    if value is None:
        return None, "Field 'display_name' wajib diisi"
    if not isinstance(value, str):
        return None, "Field 'display_name' harus berupa string"
    v = value.strip()
    if not (1 <= len(v) <= 30):
        return None, "Field 'display_name' harus 1-30 karakter"
    return v, None


def _validate_email(value):
    if value is None:
        return None, "Field 'email' wajib diisi"
    if not isinstance(value, str):
        return None, "Field 'email' harus berupa string"
    v = value.strip()
    if len(v) > 254:
        return None, "Field 'email' maksimal 254 karakter"
    if '@' not in v or '.' not in v.split('@')[-1] or v.startswith('@') or v.endswith('@'):
        return None, "Format 'email' tidak valid"
    return v, None


# ---------- Root info modul ----------
@register_route('/users-info')
def users_root():
    return jsonify({
        "status": "success",
        "message": "Users REST API siap digunakan",
        "endpoints": {
            "list_users":   "GET /api/users",
            "user_detail":  "GET /api/users/<id>",
            "create_user":  "POST /api/users",
            "update_user":  "PUT /api/users/<id>",
            "delete_user":  "DELETE /api/users/<id>"
        },
        "fields": {
            "id": "integer",
            "username": "string (UNIQUE, 3-30)",
            "display_name": "string (1-30)",
            "email": "string (UNIQUE)",
            "created_at": "TIMESTAMPTZ — diisi otomatis saat INSERT",
            "updated_at": "TIMESTAMPTZ — diperbarui otomatis saat UPDATE",
        }
    }), 200


# =========================================================
# 1. GET /api/users  — list + search + pagination
# =========================================================
@register_route('/api/users', methods=['GET'])
def get_users():
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
                SELECT id, username, display_name, email, created_at, updated_at
                FROM users
                WHERE 1=1
            """
            params = []
            if search:
                query += (
                    " AND (LOWER(username) LIKE %s"
                    " OR LOWER(display_name) LIKE %s"
                    " OR LOWER(email) LIKE %s)"
                )
                pattern = f"%{search}%"
                params.extend([pattern, pattern, pattern])
            query += " ORDER BY id ASC OFFSET %s LIMIT %s;"
            params.extend([skip, limit])
            cur.execute(query, params)
            users = cur.fetchall()
            cur.close()
            conn.close()
            # created_at & updated_at sudah termasuk dari SELECT
            return jsonify({
                "status": "success",
                "total": len(users),
                "data": users
            }), 200
        except Exception:
            conn.close()

    # Fallback
    filtered = MOCK_USERS
    if search:
        filtered = [
            u for u in filtered
            if search in u['username'].lower()
            or search in u['display_name'].lower()
            or search in u['email'].lower()
        ]
    paginated = filtered[skip: skip + limit]
    paginated = [_ensure_timestamps(dict(u)) for u in paginated]
    return jsonify({
        "status": "success",
        "total": len(paginated),
        "data": paginated
    }), 200


# =========================================================
# 2. GET /api/users/<id>  — detail (+ profil & settings ringkas)
# =========================================================
@register_route('/api/users/<int:user_id>', methods=['GET'])
def get_user_detail(user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, username, display_name, email, created_at, updated_at
                FROM users WHERE id = %s;
            """, (user_id,))
            user = cur.fetchone()
            if not user:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            # Ringkasan profil (opsional)
            cur.execute("""
                SELECT bio, avatar_url, twitch_url, youtube_url,
                       social_media_url, updated_at AS profile_updated_at
                FROM user_profiles WHERE user_id = %s;
            """, (user_id,))
            user['profile'] = cur.fetchone()

            # Ringkasan settings (opsional)
            cur.execute("""
                SELECT display_theme, updated_at AS settings_updated_at
                FROM user_settings WHERE user_id = %s;
            """, (user_id,))
            user['settings'] = cur.fetchone()

            cur.close()
            conn.close()
            return jsonify({"status": "success", "data": user}), 200
        except Exception:
            conn.close()

    # Fallback
    user = next((u for u in MOCK_USERS if u['id'] == user_id), None)
    if not user:
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    user_copy = _ensure_timestamps(dict(user))
    user_copy['profile'] = None
    user_copy['settings'] = {"display_theme": "system"}
    return jsonify({"status": "success", "data": user_copy}), 200


# =========================================================
# 3. POST /api/users  — create (created_at & updated_at otomatis)
# =========================================================
@register_route('/api/users', methods=['POST'])
def create_user():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    username, err = _validate_username(data.get('username'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    display_name, err = _validate_display_name(data.get('display_name'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    email, err = _validate_email(data.get('email'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Cek UNIQUE (username & email) sebelum insert untuk pesan 409 yang rapi
            cur.execute(
                "SELECT id, username, email FROM users WHERE username = %s OR email = %s;",
                (username, email)
            )
            conflict = cur.fetchone()
            if conflict:
                cur.close()
                conn.close()
                field = "username" if conflict['username'] == username else "email"
                return jsonify({
                    "status": "error",
                    "message": f"{field} sudah digunakan"
                }), 409

            # created_at & updated_at TIDAK dikirim oleh client.
            # Nilai diisi oleh DEFAULT now() di DB.
            cur.execute("""
                INSERT INTO users (username, display_name, email)
                VALUES (%s, %s, %s)
                RETURNING id, username, display_name, email,
                          created_at, updated_at;
            """, (username, display_name, email))
            new_user = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "User berhasil ditambahkan",
                "data": new_user
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan user: {str(e)}"
            }), 500

    # Fallback
    if any(u['username'] == username for u in MOCK_USERS):
        return jsonify({"status": "error", "message": "username sudah digunakan"}), 409
    if any(u['email'] == email for u in MOCK_USERS):
        return jsonify({"status": "error", "message": "email sudah digunakan"}), 409

    new_id = max([u['id'] for u in MOCK_USERS], default=0) + 1
    now = _now_iso()
    new_user = {
        "id": new_id,
        "username": username,
        "display_name": display_name,
        "email": email,
        "created_at": now,   # ← created_at diisi saat INSERT
        "updated_at": now,   # ← updated_at = created_at saat INSERT
    }
    MOCK_USERS.append(new_user)
    return jsonify({
        "status": "success",
        "message": "User berhasil ditambahkan",
        "data": new_user
    }), 201


# =========================================================
# 4. PUT /api/users/<id>  — partial update (updated_at otomatis berubah)
# =========================================================
@register_route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang boleh diubah (created_at & updated_at TIDAK boleh dari client)
    allowed = ('username', 'display_name', 'email')
    if not any(f in data for f in allowed):
        return jsonify({
            "status": "error",
            "message": f"Minimal satu field harus diisi: {', '.join(allowed)}"
        }), 400

    # Validasi per-field jika dikirim
    username_value = None
    if 'username' in data:
        username_value, err = _validate_username(data['username'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    display_name_value = None
    if 'display_name' in data:
        display_name_value, err = _validate_display_name(data['display_name'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    email_value = None
    if 'email' in data:
        email_value, err = _validate_email(data['email'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id = %s;", (user_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            # Cek UNIQUE jika username/email diubah
            new_username = username_value if username_value is not None else existing['username']
            new_email = email_value if email_value is not None else existing['email']

            if (username_value is not None or email_value is not None):
                cur.execute(
                    """SELECT id, username, email FROM users
                       WHERE (username = %s OR email = %s) AND id <> %s;""",
                    (new_username, new_email, user_id)
                )
                conflict = cur.fetchone()
                if conflict:
                    cur.close()
                    conn.close()
                    field = "username" if conflict['username'] == new_username else "email"
                    return jsonify({
                        "status": "error",
                        "message": f"{field} sudah digunakan"
                    }), 409

            new_display = (
                display_name_value if display_name_value is not None
                else existing['display_name']
            )

            # updated_at di-set eksplisit via now() → dijamin berubah pada setiap PUT
            cur.execute("""
                UPDATE users
                SET username = %s,
                    display_name = %s,
                    email = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, username, display_name, email,
                          created_at, updated_at;
            """, (new_username, new_display, new_email, user_id))
            updated = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "User berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui user: {str(e)}"
            }), 500

    # Fallback
    user = next((u for u in MOCK_USERS if u['id'] == user_id), None)
    if not user:
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    if username_value is not None:
        if any(
            u['id'] != user_id and u['username'] == username_value
            for u in MOCK_USERS
        ):
            return jsonify({"status": "error", "message": "username sudah digunakan"}), 409
        user['username'] = username_value

    if display_name_value is not None:
        user['display_name'] = display_name_value

    if email_value is not None:
        if any(
            u['id'] != user_id and u['email'] == email_value
            for u in MOCK_USERS
        ):
            return jsonify({"status": "error", "message": "email sudah digunakan"}), 409
        user['email'] = email_value

    # created_at tetap; updated_at selalu berubah saat PUT
    _ensure_timestamps(user)
    user['updated_at'] = _now_iso()

    return jsonify({
        "status": "success",
        "message": "User berhasil diperbarui",
        "data": user
    }), 200


# =========================================================
# 5. DELETE /api/users/<id>
# =========================================================
@register_route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id = %s;", (user_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            # Info dampak relasi:
            # - entries.user_id ON DELETE SET NULL
            # - user_settings, user_profiles, category_moderators,
            #   game_administrators ON DELETE CASCADE
            cur.execute("SELECT COUNT(*) AS count FROM entries WHERE user_id = %s;", (user_id,))
            res = cur.fetchone()
            entry_count = res['count'] if res else 0

            cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
            conn.commit()
            cur.close()
            conn.close()

            message = f"User ID {user_id} berhasil dihapus"
            if entry_count > 0:
                message += (
                    f" ({entry_count} entry kini tanpa pemilik / user_id = NULL); "
                    "profile, settings, moderator & admin otomatis terhapus via CASCADE"
                )
            return jsonify({"status": "success", "message": message}), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus user: {str(e)}"
            }), 500

    # Fallback
    user_idx = next((i for i, u in enumerate(MOCK_USERS) if u['id'] == user_id), None)
    if user_idx is None:
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    deleted = MOCK_USERS.pop(user_idx)
    return jsonify({
        "status": "success",
        "message": f"User '{deleted['username']}' berhasil dihapus"
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
    app.run(debug=True, port=5001)