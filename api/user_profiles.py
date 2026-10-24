from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import get_db_connection, MOCK_USERS, MOCK_USER_PROFILES
except ImportError:
    from db import get_db_connection, MOCK_USERS, MOCK_USER_PROFILES



# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_updated_at(obj):
    """Pastikan objek profile (dict) memiliki updated_at."""
    if not isinstance(obj, dict):
        return obj
    if 'updated_at' not in obj or obj['updated_at'] is None:
        obj['updated_at'] = _now_iso()
    return obj


# ---------- Konstanta field ----------
PROFILE_FIELDS = ('bio', 'avatar_url', 'twitch_url', 'youtube_url', 'social_media_url')
URL_FIELDS = ('avatar_url', 'twitch_url', 'youtube_url', 'social_media_url')


def _validate_url(value, field_name):
    """Validasi field URL (nullable)."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"Field '{field_name}' harus berupa string atau null"
    v = value.strip()
    if v == '':
        return None, None  # kosong → NULL
    if not (v.startswith('http://') or v.startswith('https://')):
        return None, f"Field '{field_name}' harus berupa URL valid (http/https)"
    if len(v) > 2048:
        return None, f"Field '{field_name}' maksimal 2048 karakter"
    return v, None


def _validate_bio(value):
    """Validasi field bio (TEXT nullable)."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "Field 'bio' harus berupa string atau null"
    v = value.strip()
    if v == '':
        return None, None  # kosong → NULL
    if len(v) > 5000:
        return None, "Field 'bio' maksimal 5000 karakter"
    return v, None


def _normalize_payload(data, partial=False):
    """
    Validasi & normalisasi payload profile.
    - partial=True  → hanya field yang dikirim yang diproses (untuk PUT)
    - partial=False → semua field wajib diproses (untuk POST; nilai default NULL)
    Return: (normalized_dict, error_message)
    """
    normalized = {}
    fields_to_check = (
        PROFILE_FIELDS if not partial
        else [f for f in PROFILE_FIELDS if f in data]
    )

    for field in fields_to_check:
        raw = data.get(field)
        if field == 'bio':
            val, err = _validate_bio(raw)
        else:
            val, err = _validate_url(raw, field)
        if err:
            return None, err
        normalized[field] = val

    return normalized, None


# ---------- Root info modul ----------
@register_route('/user-profiles-info')
def user_profiles_root():
    return jsonify({
        "status": "success",
        "message": "User Profiles REST API siap digunakan",
        "endpoints": {
            "get_profile":    "GET /api/users/<user_id>/profile",
            "create_profile": "POST /api/users/<user_id>/profile",
            "update_profile": "PUT /api/users/<user_id>/profile",
            "delete_profile": "DELETE /api/users/<user_id>/profile"
        },
        "fields": {
            "user_id": "integer (PRIMARY KEY, FK ke users.id, ON DELETE CASCADE)",
            "bio": "TEXT (nullable, DEFAULT NULL)",
            "avatar_url": "TEXT (nullable, DEFAULT NULL)",
            "twitch_url": "TEXT (nullable, DEFAULT NULL)",
            "youtube_url": "TEXT (nullable, DEFAULT NULL)",
            "social_media_url": "TEXT (nullable, DEFAULT NULL)",
            "updated_at": "TIMESTAMPTZ — diisi otomatis saat INSERT, diperbarui saat UPDATE",
        },
        "notes": {
            "created_at": "Tidak ada di skema user_profiles",
            "verified_at": "Tidak relevan untuk user_profiles",
        }
    }), 200


# =========================================================
# 1. GET /api/users/<user_id>/profile
# =========================================================
@register_route('/api/users/<int:user_id>/profile', methods=['GET'])
def get_user_profile(user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan user ada
            cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            cur.execute("""
                SELECT user_id, bio, avatar_url, twitch_url, youtube_url,
                       social_media_url, updated_at
                FROM user_profiles
                WHERE user_id = %s;
            """, (user_id,))
            profile = cur.fetchone()
            cur.close()
            conn.close()

            if not profile:
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} belum memiliki profil"
                }), 404

            return jsonify({"status": "success", "data": profile}), 200
        except Exception:
            conn.close()

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    profile = next((p for p in MOCK_USER_PROFILES if p['user_id'] == user_id), None)
    if not profile:
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} belum memiliki profil"
        }), 404

    profile_copy = _ensure_updated_at(dict(profile))
    return jsonify({"status": "success", "data": profile_copy}), 200


# =========================================================
# 2. POST /api/users/<user_id>/profile
#    — updated_at otomatis diisi (DEFAULT now())
# =========================================================
@register_route('/api/users/<int:user_id>/profile', methods=['POST'])
def create_user_profile(user_id):
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
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
    if 'user_id' in data and data['user_id'] != user_id:
        return jsonify({
            "status": "error",
            "message": "Field 'user_id' pada body tidak boleh berbeda dengan user_id di URL"
        }), 400

    normalized, err = _normalize_payload(data, partial=False)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan user ada
            cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            # PRIMARY KEY = user_id, jadi satu user hanya boleh punya 1 profil
            cur.execute("SELECT user_id FROM user_profiles WHERE user_id = %s;", (user_id,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} sudah memiliki profil, gunakan PUT untuk memperbarui"
                }), 409

            # updated_at TIDAK dikirim → diisi DEFAULT now() di DB
            cur.execute("""
                INSERT INTO user_profiles
                    (user_id, bio, avatar_url, twitch_url, youtube_url, social_media_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING user_id, bio, avatar_url, twitch_url, youtube_url,
                          social_media_url, updated_at;
            """, (
                user_id,
                normalized.get('bio'),
                normalized.get('avatar_url'),
                normalized.get('twitch_url'),
                normalized.get('youtube_url'),
                normalized.get('social_media_url'),
            ))
            new_profile = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Profil user berhasil dibuat",
                "data": new_profile
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal membuat profil user: {str(e)}"
            }), 500

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    if any(p['user_id'] == user_id for p in MOCK_USER_PROFILES):
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} sudah memiliki profil, gunakan PUT untuk memperbarui"
        }), 409

    new_profile = {
        "user_id": user_id,
        "bio": normalized.get('bio'),
        "avatar_url": normalized.get('avatar_url'),
        "twitch_url": normalized.get('twitch_url'),
        "youtube_url": normalized.get('youtube_url'),
        "social_media_url": normalized.get('social_media_url'),
        "updated_at": _now_iso(),  # ← diisi otomatis saat INSERT
    }
    MOCK_USER_PROFILES.append(new_profile)
    return jsonify({
        "status": "success",
        "message": "Profil user berhasil dibuat",
        "data": new_profile
    }), 201


# =========================================================
# 3. PUT /api/users/<user_id>/profile
#    — updated_at selalu berubah (SET updated_at = now())
# =========================================================
@register_route('/api/users/<int:user_id>/profile', methods=['PUT'])
def update_user_profile(user_id):
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
    if 'user_id' in data and data['user_id'] != user_id:
        return jsonify({
            "status": "error",
            "message": "Field 'user_id' tidak boleh diubah melalui endpoint ini"
        }), 400

    # Minimal ada satu field yang di-update
    provided_fields = [f for f in PROFILE_FIELDS if f in data]
    if not provided_fields:
        return jsonify({
            "status": "error",
            "message": f"Minimal satu field harus diisi: {', '.join(PROFILE_FIELDS)}"
        }), 400

    normalized, err = _normalize_payload(data, partial=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan user ada
            cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            # Pastikan profile ada
            cur.execute("SELECT * FROM user_profiles WHERE user_id = %s;", (user_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} belum memiliki profil, gunakan POST untuk membuat"
                }), 404

            # Merge: field yang tidak dikirim → pakai nilai lama
            bio              = normalized.get('bio',              existing['bio'])
            avatar_url       = normalized.get('avatar_url',       existing['avatar_url'])
            twitch_url       = normalized.get('twitch_url',       existing['twitch_url'])
            youtube_url      = normalized.get('youtube_url',      existing['youtube_url'])
            social_media_url = normalized.get('social_media_url', existing['social_media_url'])

            # updated_at di-set eksplisit via now() → dijamin berubah
            cur.execute("""
                UPDATE user_profiles
                SET bio = %s,
                    avatar_url = %s,
                    twitch_url = %s,
                    youtube_url = %s,
                    social_media_url = %s,
                    updated_at = now()
                WHERE user_id = %s
                RETURNING user_id, bio, avatar_url, twitch_url, youtube_url,
                          social_media_url, updated_at;
            """, (bio, avatar_url, twitch_url, youtube_url, social_media_url, user_id))
            updated = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Profil user berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui profil user: {str(e)}"
            }), 500

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    profile = next((p for p in MOCK_USER_PROFILES if p['user_id'] == user_id), None)
    if not profile:
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} belum memiliki profil, gunakan POST untuk membuat"
        }), 404

    for field, value in normalized.items():
        profile[field] = value
    profile['updated_at'] = _now_iso()  # ← selalu berubah saat PUT

    return jsonify({
        "status": "success",
        "message": "Profil user berhasil diperbarui",
        "data": profile
    }), 200


# =========================================================
# 4. DELETE /api/users/<user_id>/profile
# =========================================================
@register_route('/api/users/<int:user_id>/profile', methods=['DELETE'])
def delete_user_profile(user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan user ada
            cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            cur.execute("SELECT user_id FROM user_profiles WHERE user_id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Profil untuk user ID {user_id} tidak ditemukan"
                }), 404

            cur.execute("DELETE FROM user_profiles WHERE user_id = %s;", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Profil user ID {user_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus profil user: {str(e)}"
            }), 500

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    idx = next((i for i, p in enumerate(MOCK_USER_PROFILES) if p['user_id'] == user_id), None)
    if idx is None:
        return jsonify({
            "status": "error",
            "message": f"Profil untuk user ID {user_id} tidak ditemukan"
        }), 404

    MOCK_USER_PROFILES.pop(idx)
    return jsonify({
        "status": "success",
        "message": f"Profil user ID {user_id} berhasil dihapus"
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
    app.run(debug=True, port=5003)