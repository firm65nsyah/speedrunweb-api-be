from flask import jsonify, request
from api.index import app, register_route

try:
    from api.db import (
        get_db_connection,
        MOCK_CATEGORY_MODERATORS, MOCK_USERS, MOCK_CATEGORIES
    )
except ImportError:
    from db import (
        get_db_connection,
        MOCK_CATEGORY_MODERATORS, MOCK_USERS, MOCK_CATEGORIES
    )


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


# ---------- Root info modul ----------
@register_route('/category-moderators-info')
def category_moderators_root():
    return jsonify({
        "status": "success",
        "message": "Category Moderators REST API siap digunakan",
        "endpoints": {
            "list_moderators_by_category": "GET /api/categories/<category_id>/moderators",
            "list_categories_by_moderator": "GET /api/users/<user_id>/moderated-categories",
            "assign_moderator":             "POST /api/categories/<category_id>/moderators",
            "remove_moderator":             "DELETE /api/categories/<category_id>/moderators/<user_id>"
        },
        "fields": {
            "user_id": "integer (composite PK, FK users.id, ON DELETE CASCADE)",
            "category_id": "integer (composite PK, FK categories.id, ON DELETE CASCADE)",
        },
        "notes": {
            "created_at": "Tidak ada di skema category_moderators",
            "updated_at": "Tidak ada di skema category_moderators",
            "verified_at": "Tidak relevan untuk category_moderators",
            "put": "Tidak ada PUT; untuk mengubah relasi, DELETE lalu POST",
        }
    }), 200


# =========================================================
# 1. GET /api/categories/<category_id>/moderators
#    — daftar moderator untuk satu kategori
# =========================================================
@register_route('/api/categories/<int:category_id>/moderators', methods=['GET'])
def list_moderators_by_category(category_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan kategori ada
            cur.execute("SELECT id, name FROM categories WHERE id = %s;", (category_id,))
            category = cur.fetchone()
            if not category:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            cur.execute("""
                SELECT cm.user_id, u.username, u.display_name
                FROM category_moderators cm
                LEFT JOIN users u ON cm.user_id = u.id
                WHERE cm.category_id = %s
                ORDER BY cm.user_id ASC;
            """, (category_id,))
            moderators = cur.fetchall()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "category_id": category_id,
                "category_name": category['name'],
                "total": len(moderators),
                "data": moderators
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

    moderators = []
    for m in MOCK_CATEGORY_MODERATORS:
        if m['category_id'] == category_id:
            user = next((u for u in MOCK_USERS if u['id'] == m['user_id']), None)
            moderators.append({
                "user_id": m['user_id'],
                "username": user['username'] if user else None,
                "display_name": user['display_name'] if user else None,
            })
    moderators.sort(key=lambda x: x['user_id'])

    return jsonify({
        "status": "success",
        "category_id": category_id,
        "category_name": category['name'],
        "total": len(moderators),
        "data": moderators
    }), 200


# =========================================================
# 2. GET /api/users/<user_id>/moderated-categories
#    — daftar kategori yang dimoderasi seorang user
# =========================================================
@register_route('/api/users/<int:user_id>/moderated-categories', methods=['GET'])
def list_categories_by_moderator(user_id):
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
                SELECT cm.category_id, c.name AS category_name,
                       c.game_id, g.name AS game_name
                FROM category_moderators cm
                LEFT JOIN categories c ON cm.category_id = c.id
                LEFT JOIN games g ON c.game_id = g.id
                WHERE cm.user_id = %s
                ORDER BY cm.category_id ASC;
            """, (user_id,))
            categories = cur.fetchall()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "user_id": user_id,
                "username": user['username'],
                "total": len(categories),
                "data": categories
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

    categories = []
    for m in MOCK_CATEGORY_MODERATORS:
        if m['user_id'] == user_id:
            category = next((c for c in MOCK_CATEGORIES if c['id'] == m['category_id']), None)
            game = None
            if category:
                # MOCK_GAMES tidak wajib diimpor; ambil game_id jika ada
                game_id = category.get('game_id')
            else:
                game_id = None
            categories.append({
                "category_id": m['category_id'],
                "category_name": category['name'] if category else None,
                "game_id": game_id,
                "game_name": None,  # tidak di-enrich di fallback agar ringan
            })
    categories.sort(key=lambda x: x['category_id'])

    return jsonify({
        "status": "success",
        "user_id": user_id,
        "username": user['username'],
        "total": len(categories),
        "data": categories
    }), 200


# =========================================================
# 3. POST /api/categories/<category_id>/moderators
#    — assign user sebagai moderator kategori
# =========================================================
@register_route('/api/categories/<int:category_id>/moderators', methods=['POST'])
def assign_moderator(category_id):
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Tolak timestamp & field asing (tabel pivot tidak punya timestamp)
    if 'created_at' in data or 'updated_at' in data or 'verified_at' in data:
        return jsonify({
            "status": "error",
            "message": "Tabel category_moderators tidak memiliki timestamp; "
                       "field 'created_at', 'updated_at', 'verified_at' tidak valid"
        }), 400

    user_id, err = _validate_int(data.get('user_id'), 'user_id', nullable=False)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    # Tolak jika category_id di body berbeda dari URL
    if 'category_id' in data and data['category_id'] != category_id:
        return jsonify({
            "status": "error",
            "message": "Field 'category_id' pada body tidak boleh berbeda dengan category_id di URL"
        }), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan kategori ada
            cur.execute("SELECT id, name FROM categories WHERE id = %s;", (category_id,))
            category = cur.fetchone()
            if not category:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            # Pastikan user ada
            cur.execute("SELECT id, username FROM users WHERE id = %s;", (user_id,))
            user = cur.fetchone()
            if not user:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 400

            # Cek duplikasi (composite PK)
            cur.execute("""
                SELECT 1 FROM category_moderators
                WHERE user_id = %s AND category_id = %s;
            """, (user_id, category_id))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} sudah menjadi moderator category ID {category_id}"
                }), 409

            cur.execute("""
                INSERT INTO category_moderators (user_id, category_id)
                VALUES (%s, %s);
            """, (user_id, category_id))
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "message": f"User '{user['username']}' berhasil ditambahkan sebagai moderator category '{category['name']}'",
                "data": {
                    "user_id": user_id,
                    "username": user['username'],
                    "category_id": category_id,
                    "category_name": category['name'],
                }
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan moderator: {str(e)}"
            }), 500

    # Fallback
    category = next((c for c in MOCK_CATEGORIES if c['id'] == category_id), None)
    if not category:
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 404

    user = next((u for u in MOCK_USERS if u['id'] == user_id), None)
    if not user:
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 400

    if any(
        m['user_id'] == user_id and m['category_id'] == category_id
        for m in MOCK_CATEGORY_MODERATORS
    ):
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} sudah menjadi moderator category ID {category_id}"
        }), 409

    MOCK_CATEGORY_MODERATORS.append({
        "user_id": user_id,
        "category_id": category_id,
    })
    return jsonify({
        "status": "success",
        "message": f"User '{user['username']}' berhasil ditambahkan sebagai moderator category '{category['name']}'",
        "data": {
            "user_id": user_id,
            "username": user['username'],
            "category_id": category_id,
            "category_name": category['name'],
        }
    }), 201


# =========================================================
# 4. DELETE /api/categories/<category_id>/moderators/<user_id>
#    — hapus relasi moderator
# =========================================================
@register_route('/api/categories/<int:category_id>/moderators/<int:user_id>', methods=['DELETE'])
def remove_moderator(category_id, user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan kategori ada
            cur.execute("SELECT id FROM categories WHERE id = %s;", (category_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Category dengan ID {category_id} tidak ditemukan"
                }), 404

            # Pastikan user ada
            cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User dengan ID {user_id} tidak ditemukan"
                }), 404

            # Pastikan relasi ada
            cur.execute("""
                SELECT 1 FROM category_moderators
                WHERE user_id = %s AND category_id = %s;
            """, (user_id, category_id))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} bukan moderator category ID {category_id}"
                }), 404

            cur.execute("""
                DELETE FROM category_moderators
                WHERE user_id = %s AND category_id = %s;
            """, (user_id, category_id))
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "message": f"Moderator user ID {user_id} berhasil dihapus dari category ID {category_id}"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus moderator: {str(e)}"
            }), 500

    # Fallback
    if not any(c['id'] == category_id for c in MOCK_CATEGORIES):
        return jsonify({
            "status": "error",
            "message": f"Category dengan ID {category_id} tidak ditemukan"
        }), 404

    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    idx = next(
        (i for i, m in enumerate(MOCK_CATEGORY_MODERATORS)
         if m['user_id'] == user_id and m['category_id'] == category_id),
        None
    )
    if idx is None:
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} bukan moderator category ID {category_id}"
        }), 404

    MOCK_CATEGORY_MODERATORS.pop(idx)
    return jsonify({
        "status": "success",
        "message": f"Moderator user ID {user_id} berhasil dihapus dari category ID {category_id}"
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
    app.run(debug=True, port=5009)