from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import get_db_connection, MOCK_USERS, MOCK_USER_SETTINGS
except ImportError:
    from db import get_db_connection, MOCK_USERS, MOCK_USER_SETTINGS

# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_updated_at(obj):
    """
    Pastikan objek settings (dict) memiliki updated_at.
    Dipakai untuk mock lama yang mungkin belum punya field ini.
    """
    if not isinstance(obj, dict):
        return obj
    if 'updated_at' not in obj or obj['updated_at'] is None:
        obj['updated_at'] = _now_iso()
    return obj


# ---------- Konstanta validasi (mirror CHECK constraint di SQL) ----------
VALID_THEMES = ('light', 'dark', 'system')
DEFAULT_THEME = 'system'


def _validate_theme(value):
    """Validasi display_theme sesuai CHECK (display_theme IN (...))."""
    if value is None:
        return None, "Field 'display_theme' wajib diisi"
    if not isinstance(value, str):
        return None, "Field 'display_theme' harus berupa string"
    theme = value.strip().lower()
    if theme not in VALID_THEMES:
        return None, (
            f"Field 'display_theme' harus salah satu dari: "
            f"{', '.join(VALID_THEMES)}"
        )
    return theme, None


# ---------- Root info modul ----------
@register_route('/user-settings-info')
def user_settings_root():
    return jsonify({
        "status": "success",
        "message": "User Settings REST API siap digunakan",
        "endpoints": {
            "get_settings":    "GET /api/users/<user_id>/settings",
            "create_settings": "POST /api/users/<user_id>/settings",
            "update_settings": "PUT /api/users/<user_id>/settings",
            "delete_settings": "DELETE /api/users/<user_id>/settings"
        },
        "fields": {
            "user_id": "integer (PRIMARY KEY, FK ke users.id, ON DELETE CASCADE)",
            "display_theme": "string (CHECK: light | dark | system, DEFAULT 'system')",
            "updated_at": "TIMESTAMPTZ — diisi otomatis saat INSERT, diperbarui saat UPDATE",
        },
        "notes": {
            "created_at": "Tidak ada di skema user_settings",
            "verified_at": "Tidak relevan untuk user_settings",
        }
    }), 200


# =========================================================
# 1. GET /api/users/<user_id>/settings
# =========================================================
@register_route('/api/users/<int:user_id>/settings', methods=['GET'])
def get_user_settings(user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan user ada
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
                SELECT user_id, display_theme, updated_at
                FROM user_settings
                WHERE user_id = %s;
            """, (user_id,))
            settings = cur.fetchone()
            cur.close()
            conn.close()

            if not settings:
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} belum memiliki pengaturan"
                }), 404

            return jsonify({"status": "success", "data": settings}), 200
        except Exception:
            conn.close()

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    settings = next((s for s in MOCK_USER_SETTINGS if s['user_id'] == user_id), None)
    if not settings:
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} belum memiliki pengaturan"
        }), 404

    settings_copy = _ensure_updated_at(dict(settings))
    return jsonify({"status": "success", "data": settings_copy}), 200


# =========================================================
# 2. POST /api/users/<user_id>/settings
#    — updated_at otomatis diisi (DEFAULT now())
# =========================================================
@register_route('/api/users/<int:user_id>/settings', methods=['POST'])
def create_user_settings(user_id):
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

    # Validasi theme (jika tidak dikirim → default 'system' via server)
    if 'display_theme' in data:
        theme, err = _validate_theme(data['display_theme'])
        if err:
            return jsonify({"status": "error", "message": err}), 400
    else:
        theme = DEFAULT_THEME  # mirror DEFAULT 'system'

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

            # Cek sudah ada settings (PRIMARY KEY = user_id)
            cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s;", (user_id,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} sudah memiliki pengaturan, gunakan PUT untuk memperbarui"
                }), 409

            # updated_at TIDAK dikirim → diisi DEFAULT now() di DB
            cur.execute("""
                INSERT INTO user_settings (user_id, display_theme)
                VALUES (%s, %s)
                RETURNING user_id, display_theme, updated_at;
            """, (user_id, theme))
            new_settings = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Pengaturan user berhasil dibuat",
                "data": new_settings
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal membuat pengaturan user: {str(e)}"
            }), 500

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    if any(s['user_id'] == user_id for s in MOCK_USER_SETTINGS):
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} sudah memiliki pengaturan, gunakan PUT untuk memperbarui"
        }), 409

    new_settings = {
        "user_id": user_id,
        "display_theme": theme,
        "updated_at": _now_iso(),  # ← diisi otomatis saat INSERT
    }
    MOCK_USER_SETTINGS.append(new_settings)
    return jsonify({
        "status": "success",
        "message": "Pengaturan user berhasil dibuat",
        "data": new_settings
    }), 201


# =========================================================
# 3. PUT /api/users/<user_id>/settings
#    — updated_at selalu berubah (SET updated_at = now())
# =========================================================
@register_route('/api/users/<int:user_id>/settings', methods=['PUT'])
def update_user_settings(user_id):
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

    if 'display_theme' not in data:
        return jsonify({
            "status": "error",
            "message": "Field 'display_theme' wajib diisi untuk update"
        }), 400

    theme, err = _validate_theme(data['display_theme'])
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

            # Pastikan settings ada
            cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} belum memiliki pengaturan, gunakan POST untuk membuat"
                }), 404

            # updated_at di-set eksplisit via now() → dijamin berubah
            cur.execute("""
                UPDATE user_settings
                SET display_theme = %s,
                    updated_at = now()
                WHERE user_id = %s
                RETURNING user_id, display_theme, updated_at;
            """, (theme, user_id))
            updated = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Pengaturan user berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui pengaturan user: {str(e)}"
            }), 500

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    settings = next((s for s in MOCK_USER_SETTINGS if s['user_id'] == user_id), None)
    if not settings:
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} belum memiliki pengaturan, gunakan POST untuk membuat"
        }), 404

    settings['display_theme'] = theme
    settings['updated_at'] = _now_iso()  # ← selalu berubah saat PUT

    return jsonify({
        "status": "success",
        "message": "Pengaturan user berhasil diperbarui",
        "data": settings
    }), 200


# =========================================================
# 4. DELETE /api/users/<user_id>/settings
# =========================================================
@register_route('/api/users/<int:user_id>/settings', methods=['DELETE'])
def delete_user_settings(user_id):
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

            cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Pengaturan untuk user ID {user_id} tidak ditemukan"
                }), 404

            cur.execute("DELETE FROM user_settings WHERE user_id = %s;", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Pengaturan user ID {user_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus pengaturan user: {str(e)}"
            }), 500

    # Fallback
    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    idx = next((i for i, s in enumerate(MOCK_USER_SETTINGS) if s['user_id'] == user_id), None)
    if idx is None:
        return jsonify({
            "status": "error",
            "message": f"Pengaturan untuk user ID {user_id} tidak ditemukan"
        }), 404

    MOCK_USER_SETTINGS.pop(idx)
    return jsonify({
        "status": "success",
        "message": f"Pengaturan user ID {user_id} berhasil dihapus"
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
    app.run(debug=True, port=5002)