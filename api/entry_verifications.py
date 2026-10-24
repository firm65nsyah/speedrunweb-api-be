from flask import jsonify, request
from api.index import app, register_route
from datetime import datetime, timezone

try:
    from api.db import (
        get_db_connection,
        MOCK_ENTRY_VERIFICATIONS, MOCK_ENTRIES, MOCK_USERS
    )
except ImportError:
    from db import (
        get_db_connection,
        MOCK_ENTRY_VERIFICATIONS, MOCK_ENTRIES, MOCK_USERS
    )


# ---------- Helper timestamp ----------
def _now_iso():
    """Waktu sekarang dalam format ISO 8601 UTC (mirror TIMESTAMPTZ)."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_verified_at(obj):
    """Pastikan objek verifikasi (dict) memiliki verified_at."""
    if not isinstance(obj, dict):
        return obj
    if 'verified_at' not in obj or obj['verified_at'] is None:
        obj['verified_at'] = _now_iso()
    return obj


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


def _validate_note(value):
    """note TEXT nullable."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "Field 'note' harus berupa string atau null"
    v = value.strip()
    if v == '':
        return None, None  # kosong → NULL
    if len(v) > 5000:
        return None, "Field 'note' maksimal 5000 karakter"
    return v, None


# ---------- Root info modul ----------
@register_route('/entry-verifications-info')
def entry_verifications_root():
    return jsonify({
        "status": "success",
        "message": "Entry Verifications REST API siap digunakan",
        "endpoints": {
            "list_verifications":     "GET /api/entry-verifications",
            "verification_by_entry":  "GET /api/entries/<entry_id>/verification",
            "create_verification":    "POST /api/entries/<entry_id>/verification",
            "update_verification":    "PUT /api/entries/<entry_id>/verification",
            "delete_verification":    "DELETE /api/entries/<entry_id>/verification"
        },
        "fields": {
            "entry_id": "integer (PRIMARY KEY, FK entries.id, ON DELETE CASCADE)",
            "verifier_id": "integer (nullable, FK users.id, ON DELETE SET NULL)",
            "verified_at": "TIMESTAMPTZ — diisi otomatis saat INSERT, TIDAK bisa diubah",
            "note": "TEXT (nullable)",
        },
        "notes": {
            "created_at": "Tidak ada di skema entry_verifications",
            "updated_at": "Tidak ada di skema entry_verifications",
            "verified_at": "Satu-satunya timestamp; bersifat immutable setelah INSERT",
        }
    }), 200


# =========================================================
# 1. GET /api/entry-verifications  — list semua verifikasi
# =========================================================
@register_route('/api/entry-verifications', methods=['GET'])
def list_entry_verifications():
    skip = request.args.get('skip', default=0, type=int)
    limit = request.args.get('limit', default=100, type=int)
    verifier_id = request.args.get('verifier_id', type=int)
    if skip < 0: skip = 0
    if limit < 1 or limit > 500: limit = 100

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            query = """
                SELECT ev.entry_id, ev.verifier_id, u.username AS verifier,
                       ev.verified_at, ev.note,
                       e.duration, e.video_url,
                       e.category_id, c.name AS category_name
                FROM entry_verifications ev
                LEFT JOIN users u ON ev.verifier_id = u.id
                LEFT JOIN entries e ON ev.entry_id = e.id
                LEFT JOIN categories c ON e.category_id = c.id
                WHERE 1=1
            """
            params = []
            if verifier_id:
                query += " AND ev.verifier_id = %s"
                params.append(verifier_id)
            query += " ORDER BY ev.verified_at DESC OFFSET %s LIMIT %s;"
            params.extend([skip, limit])
            cur.execute(query, params)
            verifications = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "total": len(verifications),
                "data": verifications
            }), 200
        except Exception:
            conn.close()

    # Fallback
    filtered = MOCK_ENTRY_VERIFICATIONS
    if verifier_id:
        filtered = [v for v in filtered if v.get('verifier_id') == verifier_id]

    filtered = sorted(
        filtered,
        key=lambda x: x.get('verified_at') or '',
        reverse=True
    )
    paginated = filtered[skip: skip + limit]

    enriched = []
    for v in paginated:
        v_copy = _ensure_verified_at(dict(v))
        verifier = next(
            (u['username'] for u in MOCK_USERS if u['id'] == v_copy.get('verifier_id')),
            None
        )
        entry = next((e for e in MOCK_ENTRIES if e['id'] == v_copy.get('entry_id')), None)
        v_copy['verifier'] = verifier
        v_copy['duration'] = entry.get('duration') if entry else None
        v_copy['video_url'] = entry.get('video_url') if entry else None
        v_copy['category_id'] = entry.get('category_id') if entry else None
        enriched.append(v_copy)

    return jsonify({
        "status": "success",
        "total": len(enriched),
        "data": enriched
    }), 200


# =========================================================
# 2. GET /api/entries/<entry_id>/verification
# =========================================================
@register_route('/api/entries/<int:entry_id>/verification', methods=['GET'])
def get_entry_verification(entry_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan entry ada
            cur.execute("SELECT id FROM entries WHERE id = %s;", (entry_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            cur.execute("""
                SELECT ev.entry_id, ev.verifier_id, u.username AS verifier,
                       ev.verified_at, ev.note
                FROM entry_verifications ev
                LEFT JOIN users u ON ev.verifier_id = u.id
                WHERE ev.entry_id = %s;
            """, (entry_id,))
            verification = cur.fetchone()
            cur.close()
            conn.close()

            if not verification:
                return jsonify({
                    "status": "error",
                    "message": f"Entry ID {entry_id} belum memiliki verifikasi"
                }), 404

            return jsonify({"status": "success", "data": verification}), 200
        except Exception:
            conn.close()

    # Fallback
    if not any(e['id'] == entry_id for e in MOCK_ENTRIES):
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    verification = next(
        (v for v in MOCK_ENTRY_VERIFICATIONS if v['entry_id'] == entry_id),
        None
    )
    if not verification:
        return jsonify({
            "status": "error",
            "message": f"Entry ID {entry_id} belum memiliki verifikasi"
        }), 404

    v_copy = _ensure_verified_at(dict(verification))
    v_copy['verifier'] = next(
        (u['username'] for u in MOCK_USERS if u['id'] == v_copy.get('verifier_id')),
        None
    )
    return jsonify({"status": "success", "data": v_copy}), 200


# =========================================================
# 3. POST /api/entries/<entry_id>/verification
#    — verified_at otomatis diisi (DEFAULT now())
# =========================================================
@register_route('/api/entries/<int:entry_id>/verification', methods=['POST'])
def create_entry_verification(entry_id):
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang TIDAK boleh dikirim dari client
    if 'verified_at' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'verified_at' tidak boleh di-set manual; diisi otomatis oleh server"
        }), 400
    if 'entry_id' in data and data['entry_id'] != entry_id:
        return jsonify({
            "status": "error",
            "message": "Field 'entry_id' pada body tidak boleh berbeda dengan entry_id di URL"
        }), 400

    verifier_id, err = _validate_int(data.get('verifier_id'), 'verifier_id', nullable=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    note, err = _validate_note(data.get('note'))
    if err:
        return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan entry ada
            cur.execute("SELECT id FROM entries WHERE id = %s;", (entry_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            # Cek sudah ada verifikasi (PRIMARY KEY = entry_id)
            cur.execute("SELECT entry_id FROM entry_verifications WHERE entry_id = %s;", (entry_id,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry ID {entry_id} sudah memiliki verifikasi, gunakan PUT untuk memperbarui"
                }), 409

            # Pastikan verifier valid jika dikirim
            if verifier_id is not None:
                cur.execute("SELECT id FROM users WHERE id = %s;", (verifier_id,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"User dengan ID {verifier_id} tidak ditemukan"
                    }), 400

            # verified_at TIDAK dikirim → diisi DEFAULT now()
            cur.execute("""
                INSERT INTO entry_verifications (entry_id, verifier_id, note)
                VALUES (%s, %s, %s)
                RETURNING entry_id, verifier_id, verified_at, note;
            """, (entry_id, verifier_id, note))
            new_verification = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Verifikasi entry berhasil dibuat",
                "data": new_verification
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal membuat verifikasi entry: {str(e)}"
            }), 500

    # Fallback
    if not any(e['id'] == entry_id for e in MOCK_ENTRIES):
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    if any(v['entry_id'] == entry_id for v in MOCK_ENTRY_VERIFICATIONS):
        return jsonify({
            "status": "error",
            "message": f"Entry ID {entry_id} sudah memiliki verifikasi, gunakan PUT untuk memperbarui"
        }), 409

    if verifier_id is not None and not any(u['id'] == verifier_id for u in MOCK_USERS):
        return jsonify({
            "status": "error",
            "message": f"User dengan ID {verifier_id} tidak ditemukan"
        }), 400

    new_verification = {
        "entry_id": entry_id,
        "verifier_id": verifier_id,
        "verified_at": _now_iso(),   # ← diisi otomatis saat INSERT
        "note": note,
    }
    MOCK_ENTRY_VERIFICATIONS.append(new_verification)
    return jsonify({
        "status": "success",
        "message": "Verifikasi entry berhasil dibuat",
        "data": new_verification
    }), 201


# =========================================================
# 4. PUT /api/entries/<entry_id>/verification
#    — HANYA verifier_id & note yang boleh berubah
#    — verified_at TIDAK berubah (immutable)
# =========================================================
@register_route('/api/entries/<int:entry_id>/verification', methods=['PUT'])
def update_entry_verification(entry_id):
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "Request body harus berupa JSON object"
        }), 400

    # Field yang TIDAK boleh dikirim dari client
    if 'verified_at' in data:
        return jsonify({
            "status": "error",
            "message": "Field 'verified_at' tidak boleh diubah; bersifat immutable setelah INSERT"
        }), 400
    if 'entry_id' in data and data['entry_id'] != entry_id:
        return jsonify({
            "status": "error",
            "message": "Field 'entry_id' tidak boleh diubah melalui endpoint ini"
        }), 400

    # Minimal satu field yang diizinkan berubah
    allowed = ('verifier_id', 'note')
    if not any(f in data for f in allowed):
        return jsonify({
            "status": "error",
            "message": f"Minimal satu field harus diisi: {', '.join(allowed)}"
        }), 400

    # Validasi per-field
    verifier_value = None
    if 'verifier_id' in data:
        verifier_value, err = _validate_int(data['verifier_id'], 'verifier_id', nullable=True)
        if err:
            return jsonify({"status": "error", "message": err}), 400

    note_value = None
    if 'note' in data:
        note_value, err = _validate_note(data['note'])
        if err:
            return jsonify({"status": "error", "message": err}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan entry ada
            cur.execute("SELECT id FROM entries WHERE id = %s;", (entry_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            # Pastikan verifikasi ada
            cur.execute("SELECT * FROM entry_verifications WHERE entry_id = %s;", (entry_id,))
            existing = cur.fetchone()
            if not existing:
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry ID {entry_id} belum memiliki verifikasi, gunakan POST untuk membuat"
                }), 404

            # Validasi verifier baru jika diubah
            if 'verifier_id' in data and verifier_value is not None:
                cur.execute("SELECT id FROM users WHERE id = %s;", (verifier_value,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": f"User dengan ID {verifier_value} tidak ditemukan"
                    }), 400

            new_verifier = (
                verifier_value if 'verifier_id' in data
                else existing['verifier_id']
            )
            new_note = note_value if 'note' in data else existing['note']

            # verified_at SENGAJA TIDAK di-update → bersifat immutable
            cur.execute("""
                UPDATE entry_verifications
                SET verifier_id = %s,
                    note = %s
                WHERE entry_id = %s
                RETURNING entry_id, verifier_id, verified_at, note;
            """, (new_verifier, new_note, entry_id))
            updated = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": "Verifikasi entry berhasil diperbarui",
                "data": updated
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal memperbarui verifikasi entry: {str(e)}"
            }), 500

    # Fallback
    if not any(e['id'] == entry_id for e in MOCK_ENTRIES):
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    verification = next(
        (v for v in MOCK_ENTRY_VERIFICATIONS if v['entry_id'] == entry_id),
        None
    )
    if not verification:
        return jsonify({
            "status": "error",
            "message": f"Entry ID {entry_id} belum memiliki verifikasi, gunakan POST untuk membuat"
        }), 404

    if 'verifier_id' in data:
        if verifier_value is not None and not any(u['id'] == verifier_value for u in MOCK_USERS):
            return jsonify({
                "status": "error",
                "message": f"User dengan ID {verifier_value} tidak ditemukan"
            }), 400
        verification['verifier_id'] = verifier_value

    if 'note' in data:
        verification['note'] = note_value

    # verified_at TIDAK diubah
    _ensure_verified_at(verification)

    return jsonify({
        "status": "success",
        "message": "Verifikasi entry berhasil diperbarui",
        "data": verification
    }), 200


# =========================================================
# 5. DELETE /api/entries/<entry_id>/verification
# =========================================================
@register_route('/api/entries/<int:entry_id>/verification', methods=['DELETE'])
def delete_entry_verification(entry_id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Pastikan entry ada
            cur.execute("SELECT id FROM entries WHERE id = %s;", (entry_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Entry dengan ID {entry_id} tidak ditemukan"
                }), 404

            cur.execute("SELECT entry_id FROM entry_verifications WHERE entry_id = %s;", (entry_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "status": "error",
                    "message": f"Verifikasi untuk entry ID {entry_id} tidak ditemukan"
                }), 404

            cur.execute("DELETE FROM entry_verifications WHERE entry_id = %s;", (entry_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({
                "status": "success",
                "message": f"Verifikasi entry ID {entry_id} berhasil dihapus"
            }), 200
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "status": "error",
                "message": f"Gagal menghapus verifikasi entry: {str(e)}"
            }), 500

    # Fallback
    if not any(e['id'] == entry_id for e in MOCK_ENTRIES):
        return jsonify({
            "status": "error",
            "message": f"Entry dengan ID {entry_id} tidak ditemukan"
        }), 404

    idx = next(
        (i for i, v in enumerate(MOCK_ENTRY_VERIFICATIONS) if v['entry_id'] == entry_id),
        None
    )
    if idx is None:
        return jsonify({
            "status": "error",
            "message": f"Verifikasi untuk entry ID {entry_id} tidak ditemukan"
        }), 404

    MOCK_ENTRY_VERIFICATIONS.pop(idx)
    return jsonify({
        "status": "success",
        "message": f"Verifikasi entry ID {entry_id} berhasil dihapus"
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
    app.run(debug=True, port=5008)