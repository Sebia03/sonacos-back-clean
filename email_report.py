import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from database import get_all_users

SITE_LABELS = {
    "dakar":    "Dakar",
    "louga":    "Louga",
    "kaolack":  "Kaolack",
    "diourbel": "Diourbel",
}


# ─── Envoi email ──────────────────────────────────────────────────────────────
def send_email(to_email, subject, html_body):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port   = int(os.getenv("SMTP_PORT", 25))
    smtp_user   = os.getenv("SMTP_USER")
    smtp_pass   = os.getenv("SMTP_PASSWORD")
    smtp_from   = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_server or not smtp_user:
        print("❌ Config SMTP manquante")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"VigilOS SONACOS <{smtp_from}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.sendmail(smtp_from, to_email, msg.as_string())

        print(f"✅ Email envoyé à {to_email}")
        return True

    except Exception as e:
        print(f"❌ Erreur envoi email à {to_email}: {e}")
        return False


def normalize_alarm(alarm: dict):
    msg_type   = alarm.get("msgType")   or alarm.get("raw", {}).get("msgType")
    label_type = alarm.get("labelType") or alarm.get("raw", {}).get("labelType")
    type_label = alarm.get("typeLabel")

    if msg_type == "human" or label_type == "humanAlarm" or type_label == "human_detection":
        kind = "human"
    elif msg_type == "videoMotion" or label_type == "motionAlarm" or type_label == "motion_detection":
        kind = "motion"
    else:
        kind = "other"

    return {"typeLabel": kind, "thumbUrl": alarm.get("thumbUrl"), "raw": alarm}


def detect_site(name: str = "") -> str:
    n = name.upper()
    if n.startswith("LOUGA"):                                 return "louga"
    if n.startswith("KAOLACK") or n.startswith("KOALOACK"):    return "kaolack"
    if n.startswith("DIOURBEL"):                              return "diourbel"
    return "dakar"


# ─── Récupération données caméras + alertes ──────────────────────────────────
def get_weekly_data():
    """Récupère le statut des caméras ET les alertes de la semaine, groupés par site."""
    from blueprint.camera import get_access_token, post_to_imou, get_imou_alerts

    now        = datetime.now()
    start      = now - timedelta(days=7)
    begin_time = start.strftime("%Y-%m-%d %H:%M:%S")
    end_time   = now.strftime("%Y-%m-%d %H:%M:%S")

    token, _ = get_access_token()
    if not token:
        print("❌ Impossible de récupérer le token IMOU pour le rapport")
        return {}

    try:
        result = post_to_imou("/openapi/listDeviceDetailsByPage", {
            "token": token, "page": 1, "pageSize": 50, "source": "bindAndShare"
        })
        device_list = result["result"]["data"].get("deviceList", [])
    except Exception as e:
        print(f"❌ Erreur récupération caméras: {e}")
        return {}

    sites_data = {}
    for device in device_list:
        device_id   = device.get("deviceId")
        device_name = device.get("deviceName", "")
        status      = device.get("deviceStatus", "offline")  # online / offline / sleep
        site        = detect_site(device_name)

        if site not in sites_data:
            sites_data[site] = {
                "cameras": [], "total_alerts": 0, "human": 0, "motion": 0, "other": 0,
                "online_count": 0, "offline_count": 0,
            }

        is_online = status == "online"
        if is_online:
            sites_data[site]["online_count"] += 1
        else:
            sites_data[site]["offline_count"] += 1

        cam_entry = {
            "name": device_name, "status": status,
            "total": 0, "human": 0, "motion": 0, "other": 0,
        }

        try:
            alert_result = get_imou_alerts(
                token=token, device_id=device_id, channel_id="0",
                begin_time=begin_time, end_time=end_time, count=30,
            )
            alarms = [normalize_alarm(a) for a in alert_result.get("alarms", [])]
            human  = sum(1 for a in alarms if a["typeLabel"] == "human")
            motion = sum(1 for a in alarms if a["typeLabel"] == "motion")
            other  = len(alarms) - human - motion

            cam_entry.update({"total": len(alarms), "human": human, "motion": motion, "other": other})
            sites_data[site]["total_alerts"] += len(alarms)
            sites_data[site]["human"]        += human
            sites_data[site]["motion"]       += motion
            sites_data[site]["other"]        += other

        except Exception as e:
            print(f"⚠️ Erreur alertes caméra {device_name}: {e}")

        sites_data[site]["cameras"].append(cam_entry)

    return sites_data


# ─── Génération HTML par site ─────────────────────────────────────────────────
def generate_report_html(site_name, site_data, period_start, period_end):
    cameras_rows = ""
    for cam in sorted(site_data["cameras"], key=lambda x: (x["status"] != "online", -x["total"])):
        status_color = "#34d399" if cam["status"] == "online" else ("#fbbf24" if cam["status"] == "sleep" else "#f87171")
        status_label = "En ligne" if cam["status"] == "online" else ("Veille" if cam["status"] == "sleep" else "Hors ligne")
        cameras_rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;color:#e2e8f0">{cam['name']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{status_color};margin-right:6px"></span>
                <span style="color:{status_color};font-size:12px">{status_label}</span>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#22d3ee">{cam['human']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#fbbf24">{cam['motion']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;font-weight:bold;color:#f8fafc">{cam['total']}</td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Arial,sans-serif">
  <div style="max-width:600px;margin:0 auto;padding:24px">
    <div style="background:#1e293b;border-radius:12px;padding:24px;margin-bottom:20px;border:1px solid #334155">
      <h1 style="margin:0;color:#22d3ee;font-size:22px">VigilOS</h1>
      <p style="margin:4px 0 0;color:#64748b;font-size:13px">Rapport hebdomadaire de surveillance</p>
    </div>
    <div style="background:#1e293b;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #334155">
      <h2 style="margin:0 0 4px;color:#f8fafc;font-size:16px">Site : {SITE_LABELS.get(site_name, site_name)}</h2>
      <p style="margin:0;color:#64748b;font-size:13px">Période : {period_start} → {period_end}</p>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <div style="background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #14532d">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Caméras en ligne</p>
        <p style="margin:4px 0 0;color:#34d399;font-size:28px;font-weight:bold">{site_data['online_count']}</p>
      </div>
      <div style="background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #7f1d1d">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Caméras hors ligne</p>
        <p style="margin:4px 0 0;color:#f87171;font-size:28px;font-weight:bold">{site_data['offline_count']}</p>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
      <div style="background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #334155">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Total alertes</p>
        <p style="margin:4px 0 0;color:#f8fafc;font-size:28px;font-weight:bold">{site_data['total_alerts']}</p>
      </div>
      <div style="background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #0e7490">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Humain</p>
        <p style="margin:4px 0 0;color:#22d3ee;font-size:28px;font-weight:bold">{site_data['human']}</p>
      </div>
      <div style="background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #92400e">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Mouvement</p>
        <p style="margin:4px 0 0;color:#fbbf24;font-size:28px;font-weight:bold">{site_data['motion']}</p>
      </div>
    </div>
    <div style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;margin-bottom:16px">
      <div style="padding:16px;border-bottom:1px solid #334155">
        <h3 style="margin:0;color:#f8fafc;font-size:14px">Détail par caméra</h3>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#0f172a">
            <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Caméra</th>
            <th style="padding:10px 12px;text-align:center;color:#64748b;font-size:11px;text-transform:uppercase">Statut</th>
            <th style="padding:10px 12px;text-align:center;color:#22d3ee;font-size:11px;text-transform:uppercase">Humain</th>
            <th style="padding:10px 12px;text-align:center;color:#fbbf24;font-size:11px;text-transform:uppercase">Mouvement</th>
            <th style="padding:10px 12px;text-align:center;color:#f8fafc;font-size:11px;text-transform:uppercase">Total</th>
          </tr>
        </thead>
        <tbody>{cameras_rows}</tbody>
      </table>
    </div>
    <div style="text-align:center;padding:16px">
      <p style="margin:0;color:#475569;font-size:12px">VigilOS · SONACOS · Rapport généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
    </div>
  </div>
</body>
</html>"""


# ─── Génération HTML consolidé (superadmin) ──────────────────────────────────
def generate_consolidated_html(sites_data, period_start, period_end):
    total_all   = sum(s["total_alerts"]  for s in sites_data.values())
    human_all   = sum(s["human"]         for s in sites_data.values())
    motion_all  = sum(s["motion"]        for s in sites_data.values())
    online_all  = sum(s["online_count"]  for s in sites_data.values())
    offline_all = sum(s["offline_count"] for s in sites_data.values())

    sites_summary = ""
    for site_key, data in sites_data.items():
        sites_summary += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;color:#e2e8f0">{SITE_LABELS.get(site_key, site_key)}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#34d399">{data['online_count']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#f87171">{data['offline_count']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#22d3ee">{data['human']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#fbbf24">{data['motion']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;font-weight:bold;color:#f8fafc">{data['total_alerts']}</td>
        </tr>"""

    cameras_detail = ""
    for site_key, data in sites_data.items():
        cameras_detail += f"""
        <tr><td colspan="3" style="padding:10px 12px;background:#0f172a;color:#94a3b8;font-size:12px;font-weight:bold">{SITE_LABELS.get(site_key, site_key)}</td></tr>"""
        for cam in sorted(data["cameras"], key=lambda x: x["status"] != "online"):
            status_color = "#34d399" if cam["status"] == "online" else ("#fbbf24" if cam["status"] == "sleep" else "#f87171")
            status_label = "En ligne" if cam["status"] == "online" else ("Veille" if cam["status"] == "sleep" else "Hors ligne")
            cameras_detail += f"""
            <tr>
                <td style="padding:6px 12px;border-bottom:1px solid #1e293b;color:#cbd5e1;font-size:13px">{cam['name']}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #1e293b;text-align:center">
                    <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{status_color};margin-right:5px"></span>
                    <span style="color:{status_color};font-size:11px">{status_label}</span>
                </td>
                <td style="padding:6px 12px;border-bottom:1px solid #1e293b;text-align:center;color:#f8fafc;font-size:13px">{cam['total']}</td>
            </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Arial,sans-serif">
  <div style="max-width:600px;margin:0 auto;padding:24px">
    <div style="background:#1e293b;border-radius:12px;padding:24px;margin-bottom:20px;border:1px solid #334155">
      <h1 style="margin:0;color:#22d3ee;font-size:22px">VigilOS</h1>
      <p style="margin:4px 0 0;color:#64748b;font-size:13px">Rapport consolidé — Tous les sites</p>
    </div>
    <div style="background:#1e293b;border-radius:12px;padding:16px;margin-bottom:16px;border:1px solid #334155">
      <p style="margin:0;color:#64748b;font-size:13px">Période : {period_start} → {period_end}</p>
    </div>

    <div style="display:flex;gap:12px;margin-bottom:16px">
      <div style="flex:1;background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #14532d">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">En ligne</p>
        <p style="margin:4px 0 0;color:#34d399;font-size:24px;font-weight:bold">{online_all}</p>
      </div>
      <div style="flex:1;background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #7f1d1d">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Hors ligne</p>
        <p style="margin:4px 0 0;color:#f87171;font-size:24px;font-weight:bold">{offline_all}</p>
      </div>
    </div>

    <div style="display:flex;gap:12px;margin-bottom:16px">
      <div style="flex:1;background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #334155">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Total alertes</p>
        <p style="margin:4px 0 0;color:#f8fafc;font-size:24px;font-weight:bold">{total_all}</p>
      </div>
      <div style="flex:1;background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #0e7490">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Humain</p>
        <p style="margin:4px 0 0;color:#22d3ee;font-size:24px;font-weight:bold">{human_all}</p>
      </div>
      <div style="flex:1;background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #92400e">
        <p style="margin:0;color:#64748b;font-size:11px;text-transform:uppercase">Mouvement</p>
        <p style="margin:4px 0 0;color:#fbbf24;font-size:24px;font-weight:bold">{motion_all}</p>
      </div>
    </div>

    <div style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;margin-bottom:16px">
      <div style="padding:16px;border-bottom:1px solid #334155">
        <h3 style="margin:0;color:#f8fafc;font-size:14px">Résumé par site</h3>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#0f172a">
            <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Site</th>
            <th style="padding:10px 12px;text-align:center;color:#34d399;font-size:11px;text-transform:uppercase">En ligne</th>
            <th style="padding:10px 12px;text-align:center;color:#f87171;font-size:11px;text-transform:uppercase">Hors ligne</th>
            <th style="padding:10px 12px;text-align:center;color:#22d3ee;font-size:11px;text-transform:uppercase">Humain</th>
            <th style="padding:10px 12px;text-align:center;color:#fbbf24;font-size:11px;text-transform:uppercase">Mvt</th>
            <th style="padding:10px 12px;text-align:center;color:#f8fafc;font-size:11px;text-transform:uppercase">Total</th>
          </tr>
        </thead>
        <tbody>{sites_summary}</tbody>
      </table>
    </div>

    <div style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;margin-bottom:16px">
      <div style="padding:16px;border-bottom:1px solid #334155">
        <h3 style="margin:0;color:#f8fafc;font-size:14px">Détail des caméras par site</h3>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#0f172a">
            <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:10px;text-transform:uppercase">Caméra</th>
            <th style="padding:8px 12px;text-align:center;color:#64748b;font-size:10px;text-transform:uppercase">Statut</th>
            <th style="padding:8px 12px;text-align:center;color:#64748b;font-size:10px;text-transform:uppercase">Alertes</th>
          </tr>
        </thead>
        <tbody>{cameras_detail}</tbody>
      </table>
    </div>

    <div style="text-align:center;padding:16px">
      <p style="margin:0;color:#475569;font-size:12px">VigilOS · SONACOS · {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
    </div>
  </div>
</body>
</html>"""


# ─── Envoi des rapports ───────────────────────────────────────────────────────
def send_weekly_reports():
    print("📧 Génération des rapports hebdomadaires...")

    now           = datetime.now()
    start         = now - timedelta(days=7)
    period_start  = start.strftime("%d/%m/%Y")
    period_end    = now.strftime("%d/%m/%Y")

    sites_data = get_weekly_data()
    if not sites_data:
        print("⚠️ Aucune donnée disponible pour le rapport")
        return

    users = get_all_users()

    for user in users:
        if not user.get("email"):
            continue

        if user["role"] == "admin_site" and user.get("site"):
            site = user["site"].lower()
            if site in sites_data:
                html = generate_report_html(site, sites_data[site], period_start, period_end)
                subj = f"VigilOS — Rapport hebdomadaire {SITE_LABELS.get(site, site)} ({period_start} - {period_end})"
                send_email(user["email"], subj, html)

        elif user["role"] == "superadmin":
            html = generate_consolidated_html(sites_data, period_start, period_end)
            subj = f"VigilOS — Rapport consolidé tous sites ({period_start} - {period_end})"
            send_email(user["email"], subj, html)

    print("✅ Rapports hebdomadaires envoyés")