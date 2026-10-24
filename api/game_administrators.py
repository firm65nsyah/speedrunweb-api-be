from flask import jsonify, request
from api.index import app, register_route

try:
    from api.db import (
        get_db_connection,
        MOCK_GAME_ADMINISTRATORS, MOCK_USERS, MOCK_GAMES, MOCK_GENRES
    )
except ImportError:
    from db import (
        get_db_connection,
        MOCK_GAME_ADMINISTRATORS, MOCK_USERS, MOCK_GAMES, MOCK_GENRES
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
@register_route('/game-administrators-info')
def game_administrators_root():
    return jsonify({
        "status": "success",
        "message": "Game Administrators REST API siap digunakan",
        "endpoints": {
            "list_admins_by_game":   "GET /api/games/<game_id>/administrators",
            "list_games_by_admin":   "GET /api/users/<user_id>/administered-games",
            "assign_administrator":  "POST /api/games/<game_id>/administrators",
            "remove_administrator":  "DELETE /api/games/<game_id>/administrators/<user_id>"
        },
        "fields": {
            "user_id": "integer (composite PK, FK users.id, ON DELETE CASCADE)",
            "game_id": "integer (composite PK, FK games.id, ON DELETE CASCADE)",
        },
        "notes": {
            "created_at": "Tidak ada di skema game_administrators",
            "updated_at": "Tidak ada di skema game_administrators",
            "verified_at": "Tidak relevan untuk game_administrators",
            "put": "Tidak ada PUT; untuk mengubah relasi, DELETE lalu POST",
        }
    }), 200


# =========================================================
# 1. GET /api/games/<game_id>/administrators
#    — daftar administrator untuk satu game
# =========================================================
@register_route('/api/games/<int:game_id>/administrators', methods=['GET'])
def list_admins_by_game(game_id):
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
                SELECT ga.user_id, u.username, u.display_name
                FROM game_administrators ga
                LEFT JOIN users u ON ga.user_id = u.id
                WHERE ga.game_id = %s
                ORDER BY ga.user_id ASC;
            """, (game_id,))
            admins = cur.fetchall()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "game_id": game_id,
                "game_name": game['name'],
                "total": len(admins),
                "data": admins
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

    admins = []
    for a in MOCK_GAME_ADMINISTRATORS:
        if a['game_id'] == game_id:
            user = next((u for u in MOCK_USERS if u['id'] == a['user_id']), None)
            admins.append({
                "user_id": a['user_id'],
                "username": user['username'] if user else None,
                "display_name": user['display_name'] if user else None,
            })
    admins.sort(key=lambda x: x['user_id'])

    return jsonify({
        "status": "success",
        "game_id": game_id,
        "game_name": game['name'],
        "total": len(admins),
        "data": admins
    }), 200


# =========================================================
# 2. GET /api/users/<user_id>/administered-games
#    — daftar game yang diadministrasi seorang user
# =========================================================
@register_route('/api/users/<int:user_id>/administered-games', methods=['GET'])
def list_games_by_admin(user_id):
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
                SELECT ga.game_id, g.name AS game_name,
                       g.genre_id, ge.name AS genre_name
                FROM game_administrators ga
                LEFT JOIN games g ON ga.game_id = g.id
                LEFT JOIN genres ge ON g.genre_id = ge.id
                WHERE ga.user_id = %s
                ORDER BY ga.game_id ASC;
            """, (user_id,))
            games = cur.fetchall()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "user_id": user_id,
                "username": user['username'],
                "total": len(games),
                "data": games
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

    games = []
    for a in MOCK_GAME_ADMINISTRATORS:
        if a['user_id'] == user_id:
            game = next((g for g in MOCK_GAMES if g['id'] == a['game_id']), None)
            genre = None
            if game:
                genre = next(
                    (ge for ge in MOCK_GENRES if ge['id'] == game.get('genre_id')),
                    None
                )
            games.append({
                "game_id": a['game_id'],
                "game_name": game['name'] if game else None,
                "genre_id": game.get('genre_id') if game else None,
                "genre_name": genre['name'] if genre else None,
            })
    games.sort(key=lambda x: x['game_id'])

    return jsonify({
        "status": "success",
        "user_id": user_id,
        "username": user['username'],
        "total": len(games),
        "data": games
    }), 200


# =========================================================
# 3. POST /api/games/<game_id>/administrators
#    — assign user sebagai administrator game
# =========================================================
@register_route('/api/games/<int:game_id>/administrators', methods=['POST'])
def assign_administrator(game_id):
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
            "message": "Tabel game_administrators tidak memiliki timestamp; "
                       "field 'created_at', 'updated_at', 'verified_at' tidak valid"
        }), 400

    user_id, err = _validate_int(data.get('user_id'), 'user_id', nullable=False)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    # Tolak jika game_id di body berbeda dari URL
    if 'game_id' in data and data['game_id'] != game_id:
        return jsonify({
            "status": "error",
            "message": "Field 'game_id' pada body tidak boleh berbeda dengan game_id di URL"
        }), 400

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
                SELECT 1 FROM game_administrators
                WHERE user_id = %s AND game_id = %s;
            """, (user_id, game_id))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} sudah menjadi administrator game ID {game_id}"
                }), 409

            cur.execute("""
                INSERT INTO game_administrators (user_id, game_id)
                VALUES (%s, %s);
            """, (user_id, game_id))
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "message": f"User '{user['username']}' berhasil ditambahkan sebagai administrator game '{game['name']}'",
                "data": {
                    "user_id": user_id,
                    "username": user['username'],
                    "game_id": game_id,
                    "game_name": game['name'],
                }
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menambahkan administrator: {str(e)}"
            }), 500

    # Fallback
    game = next((g for g in MOCK_GAMES if g['id'] == game_id), None)
    if not game:
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 404

    user = next((u for u in MOCK_USERS if u['id'] == user_id), None)
    if not user:
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 400

    if any(
        a['user_id'] == user_id and a['game_id'] == game_id
        for a in MOCK_GAME_ADMINISTRATORS
    ):
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} sudah menjadi administrator game ID {game_id}"
        }), 409

    MOCK_GAME_ADMINISTRATORS.append({
        "user_id": user_id,
        "game_id": game_id,
    })
    return jsonify({
        "status": "success",
        "message": f"User '{user['username']}' berhasil ditambahkan sebagai administrator game '{game['name']}'",
        "data": {
            "user_id": user_id,
            "username": user['username'],
            "game_id": game_id,
            "game_name": game['name'],
        }
    }), 201


# =========================================================
# 4. DELETE /api/games/<game_id>/administrators/<user_id>
#    — hapus relasi administrator
# =========================================================
@register_route('/api/games/<int:game_id>/administrators/<int:user_id>', methods=['DELETE'])
def remove_administrator(game_id, user_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Pastikan game ada
            cur.execute("SELECT id FROM games WHERE id = %s;", (game_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Game dengan ID {game_id} tidak ditemukan"
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
                SELECT 1 FROM game_administrators
                WHERE user_id = %s AND game_id = %s;
            """, (user_id, game_id))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"User ID {user_id} bukan administrator game ID {game_id}"
                }), 404

            cur.execute("""
                DELETE FROM game_administrators
                WHERE user_id = %s AND game_id = %s;
            """, (user_id, game_id))
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "message": f"Administrator user ID {user_id} berhasil dihapus dari game ID {game_id}"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus administrator: {str(e)}"
            }), 500

    # Fallback
    if not any(g['id'] == game_id for g in MOCK_GAMES):
        return jsonify({
            "status": "error",
            "message": f"Game dengan ID {game_id} tidak ditemukan"
        }), 404

    if not any(u['id'] == user_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {user_id} tidak ditemukan"
        }), 404

    idx = next(
        (i for i, a in enumerate(MOCK_GAME_ADMINISTRATORS)
         if a['user_id'] == user_id and a['game_id'] == game_id),
        None
    )
    if idx is None:
        return jsonify({
            "status": "error",
            "message": f"User ID {user_id} bukan administrator game ID {game_id}"
        }), 404

    MOCK_GAME_ADMINISTRATORS.pop(idx)
    return jsonify({
        "status": "success",
        "message": f"Administrator user ID {user_id} berhasil dihapus dari game ID {game_id}"
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
    app.run(debug=True, port=5010)