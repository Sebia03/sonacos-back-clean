import sqlite3
import os
import hashlib

DB_PATH = os.path.join(os.path.dirname(__file__), "vigilos.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Table utilisateurs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'admin_site',
            site        TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Table alertes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alarm_id    TEXT    UNIQUE NOT NULL,
            device_id   TEXT    NOT NULL,
            device_name TEXT,
            channel_id  TEXT    DEFAULT '0',
            site        TEXT,
            msg_type    TEXT,
            label_type  TEXT,
            type_label  TEXT,
            local_date  TEXT,
            thumb_url   TEXT,
            raw_data    TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Index pour accélérer les recherches
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_device_id  ON alerts(device_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_local_date ON alerts(local_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_site       ON alerts(site)")

    conn.commit()

    # Super admin par défaut
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        superadmin_email    = os.getenv("ADMIN_EMAIL", "superadmin@sonacos.sn")
        superadmin_password = os.getenv("ADMIN_PASSWORD", "motdepassefort")
        hashed = hash_password(superadmin_password)
        cursor.execute(
            "INSERT INTO users (email, password, role, site) VALUES (?, ?, ?, ?)",
            (superadmin_email, hashed, "superadmin", None)
        )
        conn.commit()
        print(f"✅ Super admin créé : {superadmin_email}")

    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def get_user_by_email(email: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_all_users():
    conn = get_db()
    users = conn.execute("SELECT id, email, role, site, created_at FROM users").fetchall()
    conn.close()
    return [dict(u) for u in users]


def create_user(email: str, password: str, role: str, site: str = None):
    conn = get_db()
    hashed = hash_password(password)
    try:
        conn.execute(
            "INSERT INTO users (email, password, role, site) VALUES (?, ?, ?, ?)",
            (email, hashed, role, site)
        )
        conn.commit()
        return True, "Utilisateur créé avec succès"
    except sqlite3.IntegrityError:
        return False, "Cet email existe déjà"
    finally:
        conn.close()


def update_user(user_id: int, email: str = None, password: str = None, role: str = None, site: str = None):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return False, "Utilisateur introuvable"
    new_email    = email    or user["email"]
    new_role     = role     or user["role"]
    new_site     = site     if site is not None else user["site"]
    new_password = hash_password(password) if password else user["password"]
    try:
        conn.execute(
            "UPDATE users SET email=?, password=?, role=?, site=? WHERE id=?",
            (new_email, new_password, new_role, new_site, user_id)
        )
        conn.commit()
        return True, "Utilisateur mis à jour"
    except sqlite3.IntegrityError:
        return False, "Cet email existe déjà"
    finally:
        conn.close()


def delete_user(user_id: int):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return False, "Utilisateur introuvable"
    if dict(user)["role"] == "superadmin":
        conn.close()
        return False, "Impossible de supprimer le super admin"
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True, "Utilisateur supprimé"


# ─── Fonctions alertes ────────────────────────────────────────────────────────

def save_alerts(alerts: list, device_id: str, device_name: str, site: str, channel_id: str = "0"):
    """Sauvegarde une liste d'alertes en évitant les doublons."""
    if not alerts:
        return 0
    conn = get_db()
    saved = 0
    import json
    for alert in alerts:
        alarm_id = alert.get("alarmId") or alert.get("alarm_id")
        if not alarm_id:
            continue
        raw = alert.get("raw", alert)
        try:
            conn.execute("""
                INSERT OR IGNORE INTO alerts
                (alarm_id, device_id, device_name, channel_id, site, msg_type, label_type, type_label, local_date, thumb_url, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(alarm_id),
                device_id,
                device_name,
                channel_id,
                site,
                raw.get("msgType"),
                raw.get("labelType"),
                alert.get("typeLabel"),
                raw.get("localDate"),
                alert.get("thumbUrl") or raw.get("thumbUrl"),
                json.dumps(raw),
            ))
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                saved += 1
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde alerte {alarm_id}: {e}")
    conn.commit()
    conn.close()
    return saved


def get_alerts_from_db(device_id: str = None, site: str = None, days: int = 7, limit: int = 100):
    """Récupère les alertes depuis la DB locale."""
    import json
    conn = get_db()
    query  = """
        SELECT * FROM alerts
        WHERE local_date >= datetime('now', ?)
    """
    params = [f"-{days} days"]

    if device_id:
        query  += " AND device_id = ?"
        params.append(device_id)
    if site:
        query  += " AND site = ?"
        params.append(site)

    query += " ORDER BY local_date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for row in rows:
        r = dict(row)
        try:
            r["raw"] = json.loads(r["raw_data"]) if r["raw_data"] else {}
        except:
            r["raw"] = {}
        result.append(r)
    return result


def cleanup_old_alerts(days: int = 7):
    """Supprime les alertes de plus de N jours."""
    conn = get_db()
    conn.execute("DELETE FROM alerts WHERE local_date < datetime('now', ?)", (f"-{days} days",))
    deleted = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    if deleted > 0:
        print(f"🗑️ {deleted} alertes supprimées (plus de {days} jours)")
    return deleted


def get_alerts_count_by_site(days: int = 7):
    """Compte les alertes par site pour les rapports."""
    conn = get_db()
    rows = conn.execute("""
        SELECT site,
               COUNT(*) as total,
               SUM(CASE WHEN msg_type = 'human' OR label_type = 'humanAlarm' THEN 1 ELSE 0 END) as human,
               SUM(CASE WHEN msg_type = 'videoMotion' OR label_type = 'motionAlarm' THEN 1 ELSE 0 END) as motion
        FROM alerts
        WHERE local_date >= datetime('now', ?)
        GROUP BY site
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]