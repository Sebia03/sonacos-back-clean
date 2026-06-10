"""
Synchronisation des alertes depuis l'API IMOU vers la DB SQLite locale.
Tourne toutes les heures via le scheduler.
"""
import requests
from datetime import datetime, timedelta
from database import save_alerts, cleanup_old_alerts


def detect_site(name: str = "") -> str:
    n = name.upper()
    if n.startswith("LOUGA"):                          return "louga"
    if n.startswith("KAOLACK") or n.startswith("KOALOACK"): return "kaolack"
    if n.startswith("DIOURBEL"):                       return "diourbel"
    return "dakar"


def sync_all_alerts():
    """Récupère les alertes des dernières 2h pour toutes les caméras et les sauvegarde."""
    print("🔄 Synchronisation des alertes en cours...")

    from blueprint.camera import get_access_token, get_access_token_2, post_to_imou, post_to_imou_2, get_imou_alerts

    token, _  = get_access_token()
    token2, _ = get_access_token_2()

    if not token:
        print("❌ Impossible de récupérer le token IMOU pour la sync")
        return

    # Récupérer la liste des caméras
    try:
        result = post_to_imou("/openapi/listDeviceDetailsByPage", {
            "token": token, "page": 1, "pageSize": 50, "source": "bindAndShare"
        })
        device_list = result["result"]["data"].get("deviceList", [])
    except Exception as e:
        print(f"❌ Erreur récupération caméras pour sync: {e}")
        return

    now        = datetime.now()
    begin_time = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    end_time   = now.strftime("%Y-%m-%d %H:%M:%S")

    total_saved = 0

    for device in device_list:
        device_id   = device.get("deviceId")
        device_name = device.get("deviceName", "")
        site        = detect_site(device_name)

        if not device_id:
            continue

        try:
            alert_result = get_imou_alerts(
                token=token,
                device_id=device_id,
                channel_id="0",
                begin_time=begin_time,
                end_time=end_time,
                count=30,
            )
            alarms = alert_result.get("alarms", [])

            if alarms:
                saved = save_alerts(alarms, device_id, device_name, site)
                if saved > 0:
                    total_saved += saved
                    print(f"   ✅ {device_name} : {saved} nouvelles alertes sauvegardées")

        except Exception as e:
            # Si OP1009, essayer avec le compte secondaire
            if "OP1009" in str(e) and token2:
                try:
                    from blueprint.camera import get_imou_alerts_2
                    alert_result = get_imou_alerts_2(
                        token=token2,
                        device_id=device_id,
                        channel_id="0",
                        begin_time=begin_time,
                        end_time=end_time,
                        count=30,
                    )
                    alarms = alert_result.get("alarms", [])
                    if alarms:
                        saved = save_alerts(alarms, device_id, device_name, site)
                        total_saved += saved
                except Exception as e2:
                    pass
            else:
                print(f"   ⚠️ {device_name} : {e}")

    print(f"✅ Sync terminée — {total_saved} nouvelles alertes sauvegardées")

    # Nettoyage des alertes anciennes
    cleanup_old_alerts(days=7)