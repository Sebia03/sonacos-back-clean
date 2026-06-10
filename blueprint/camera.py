import time
import uuid
import hashlib
import base64
import os
import requests
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, Response
from flask_cors import CORS

camera_bp = Blueprint("camera", __name__)
CORS(camera_bp)

# ─── CONFIG IMOU ──────────────────────────────────────────────────────────────
APP_ID     = os.getenv("IMOU_APP_ID",     "lcea5699cd1d7c4457")
APP_SECRET = os.getenv("IMOU_APP_SECRET", "f464f4b27e934bcba36125d953a4c6")

APP_ID_2     = os.getenv("IMOU_APP_ID_2",     "lcf47e152b3e76434d")
APP_SECRET_2 = os.getenv("IMOU_APP_SECRET_2", "351240ac88464040bb6c9116605fb4")

DATACENTER = "fk"
BASE_URL   = f"https://openapi-{DATACENTER}.easy4ip.com"

# ─── CACHES ───────────────────────────────────────────────────────────────────
IMOU_TOKEN_CACHE = {"accessToken": None, "domain": None, "expires_at": 0}
IMOU_TOKEN_CACHE_2 = {"accessToken": None, "domain": None, "expires_at": 0}
KIT_TOKEN_CACHE = {}


# ─── Détection format image ───────────────────────────────────────────────────
def detect_image_type(data: bytes) -> str:
    if data[:3] == b'\xff\xd8\xff':        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':  return "image/png"
    if data[:6] in (b'GIF87a', b'GIF89a'): return "image/gif"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return "image/webp"
    if b'ftyp' in data[:12]:              return "image/avif"
    return "image/jpeg"


# ─── Helpers compte principal ─────────────────────────────────────────────────
def generate_sign():
    timestamp = int(time.time())
    nonce     = str(uuid.uuid4())
    raw       = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET}"
    sign      = hashlib.md5(raw.encode()).hexdigest()
    return timestamp, nonce, sign

def build_imou_body(params: dict):
    timestamp, nonce, sign = generate_sign()
    return {
        "system": {"ver": "1.0", "appId": APP_ID, "sign": sign, "time": timestamp, "nonce": nonce},
        "id":     str(uuid.uuid4()),
        "params": params,
    }

def post_to_imou(endpoint: str, params: dict, timeout: int = 15):
    url      = f"{BASE_URL}{endpoint}"
    body     = build_imou_body(params)
    response = requests.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if "result" not in result:
        raise Exception("Réponse IMOU invalide : champ 'result' absent")
    return result

def get_access_token():
    now = int(time.time())
    if IMOU_TOKEN_CACHE["accessToken"] and IMOU_TOKEN_CACHE["domain"] and now < IMOU_TOKEN_CACHE["expires_at"]:
        return IMOU_TOKEN_CACHE["accessToken"], IMOU_TOKEN_CACHE["domain"]

    url  = f"{BASE_URL}/openapi/accessToken"
    body = build_imou_body({})
    try:
        response = requests.post(url, json=body, timeout=15)
        print("=== IMOU accessToken DEBUG ===")
        print("STATUS CODE:", response.status_code)
        result = response.json()
        if "result" not in result or "data" not in result["result"]:
            print("Réponse IMOU invalide pour accessToken")
            return None, None
        data         = result["result"]["data"]
        access_token = data.get("accessToken")
        expire_time  = int(data.get("expireTime", 0))
        domain       = IMOU_TOKEN_CACHE.get("domain") or BASE_URL
        if not access_token:
            print("accessToken absent dans la réponse IMOU")
            return None, None
        IMOU_TOKEN_CACHE.update({"accessToken": access_token, "domain": domain, "expires_at": now + expire_time - 60})
        return access_token, domain
    except Exception as e:
        print("Erreur get_access_token:", str(e))
        return None, None


# ─── Helpers compte secondaire SOTILMA ───────────────────────────────────────
def generate_sign_2():
    timestamp = int(time.time())
    nonce     = str(uuid.uuid4())
    raw       = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET_2}"
    sign      = hashlib.md5(raw.encode()).hexdigest()
    return timestamp, nonce, sign

def build_imou_body_2(params: dict):
    timestamp, nonce, sign = generate_sign_2()
    return {
        "system": {"ver": "1.0", "appId": APP_ID_2, "sign": sign, "time": timestamp, "nonce": nonce},
        "id":     str(uuid.uuid4()),
        "params": params,
    }

def post_to_imou_2(endpoint: str, params: dict, timeout: int = 15):
    url      = f"{BASE_URL}{endpoint}"
    body     = build_imou_body_2(params)
    response = requests.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if "result" not in result:
        raise Exception("Réponse IMOU invalide")
    return result

def get_access_token_2():
    now = int(time.time())
    if IMOU_TOKEN_CACHE_2["accessToken"] and IMOU_TOKEN_CACHE_2["domain"] and now < IMOU_TOKEN_CACHE_2["expires_at"]:
        return IMOU_TOKEN_CACHE_2["accessToken"], IMOU_TOKEN_CACHE_2["domain"]

    url  = f"{BASE_URL}/openapi/accessToken"
    body = build_imou_body_2({})
    try:
        response = requests.post(url, json=body, timeout=15)
        result   = response.json()
        data     = result["result"]["data"]
        access_token = data.get("accessToken")
        expire_time  = int(data.get("expireTime", 0))
        IMOU_TOKEN_CACHE_2.update({"accessToken": access_token, "domain": BASE_URL, "expires_at": now + expire_time - 60})
        return access_token, BASE_URL
    except Exception as e:
        print("Erreur get_access_token_2:", str(e))
        return None, None


# ─── Alertes ──────────────────────────────────────────────────────────────────
def normalize_alarm(alarm: dict):
    type_map = {0: "human_infrared", 1: "motion_detection", 2: "unknown_alarm", 3: "low_voltage_alarm"}
    raw_type = alarm.get("type")
    return {
        "alarmId":     alarm.get("alarmId"),
        "time":        alarm.get("time"),
        "type":        raw_type,
        "typeLabel":   type_map.get(raw_type, "unknown"),
        "thumbUrl":    alarm.get("thumbUrl"),
        "picurlArray": alarm.get("picurlArray", []),
        "raw":         alarm,
    }

def get_imou_alerts(token, device_id, channel_id="0", begin_time=None, end_time=None, count=30, next_alarm_id="-1"):
    if not begin_time or not end_time:
        now   = datetime.now()
        start = now - timedelta(hours=24)
        begin_time = start.strftime("%Y-%m-%d %H:%M:%S")
        end_time   = now.strftime("%Y-%m-%d %H:%M:%S")
    if count < 1 or count > 30:
        raise ValueError("count doit être compris entre 1 et 30")
    params = {
        "token": token, "deviceId": device_id, "channelId": str(channel_id),
        "beginTime": begin_time, "endTime": end_time, "count": count, "nextAlarmId": str(next_alarm_id),
    }
    result  = post_to_imou("/openapi/getAlarmMessage", params, timeout=20)
    data    = result.get("result", {}).get("data", {})
    alarms  = data.get("alarms", data.get("alarmMessages", []))
    next_id = data.get("nextAlarmId")
    return {"beginTime": begin_time, "endTime": end_time, "rawResult": result, "rawData": data, "alarms": alarms, "nextAlarmId": next_id}

def get_imou_alerts_2(token, device_id, channel_id="0", begin_time=None, end_time=None, count=30, next_alarm_id="-1"):
    if not begin_time or not end_time:
        now   = datetime.now()
        start = now - timedelta(hours=24)
        begin_time = start.strftime("%Y-%m-%d %H:%M:%S")
        end_time   = now.strftime("%Y-%m-%d %H:%M:%S")
    params = {
        "token": token, "deviceId": device_id, "channelId": str(channel_id),
        "beginTime": begin_time, "endTime": end_time,
        "count": count, "nextAlarmId": str(next_alarm_id),
    }
    result  = post_to_imou_2("/openapi/getAlarmMessage", params, timeout=20)
    data    = result.get("result", {}).get("data", {})
    alarms  = data.get("alarms", data.get("alarmMessages", []))
    return {"alarms": alarms, "rawData": data}

# ─── Routes ───────────────────────────────────────────────────────────────────

@camera_bp.route("/sdk-config", methods=["GET"])
def sdk_config():
    token, domain = get_access_token()
    if not token or not domain:
        return jsonify({"error": "Impossible de récupérer la configuration SDK IMOU"}), 500
    return jsonify({"accessToken": token, "domain": domain})


@camera_bp.route("/devices", methods=["GET"])
def devices():
    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500
    try:
        result = post_to_imou("/openapi/listDeviceDetailsByPage", {
            "token": token, "page": 1, "pageSize": 50, "source": "bindAndShare",
        })
        if "data" not in result["result"]:
            return jsonify({"error": "Réponse invalide de IMOU", "imou_response": result}), 400
        device_list = result["result"]["data"].get("deviceList", [])
        return jsonify([
            {"deviceId": d.get("deviceId"), "deviceName": d.get("deviceName"), "status": d.get("deviceStatus"), "channelId": 0}
            for d in device_list
        ])
    except Exception as e:
        return jsonify({"error": "Erreur récupération caméras", "details": str(e)}), 500


@camera_bp.route("/device-online", methods=["POST"])
def device_online():
    data      = request.get_json(silent=True) or {}
    device_id = data.get("deviceId")
    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400
    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500
    try:
        result = post_to_imou("/openapi/deviceOnline", {"token": token, "deviceId": device_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": "Erreur vérification statut caméra", "details": str(e)}), 500


@camera_bp.route("/kit-token", methods=["POST"])
def kit_token():
    data        = request.get_json(silent=True) or {}
    device_id   = data.get("deviceId")
    channel_id  = str(data.get("channelId", 0))
    stream_type = str(data.get("type", 1))
    encrypt_pwd = data.get("encryptPwd")

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    cache_key = f"{device_id}_{channel_id}"
    now       = int(time.time())
    cached    = KIT_TOKEN_CACHE.get(cache_key)
    if cached and now < cached["expires_at"]:
        return jsonify({"kitToken": cached["kitToken"], "domain": cached["domain"]})

    token, domain = get_access_token()
    if not token or not domain:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    token2, domain2 = get_access_token_2()

    try:
        params = {"token": token, "deviceId": device_id, "channelId": channel_id, "type": stream_type}
        if encrypt_pwd:
            params["encryptPwd"] = encrypt_pwd

        result = post_to_imou("/openapi/getKitToken", params)

        # Si OP1009, essayer avec le compte secondaire SOTILMA
        if result.get("result", {}).get("code") == "OP1009" and token2:
            print(f"OP1009 sur compte principal, essai compte secondaire pour {device_id}")
            params2 = {"token": token2, "deviceId": device_id, "channelId": channel_id, "type": stream_type}
            if encrypt_pwd:
                params2["encryptPwd"] = encrypt_pwd
            result = post_to_imou_2("/openapi/getKitToken", params2)
            domain = domain2

        if "data" not in result["result"]:
            return jsonify({"error": "Réponse invalide", "imou_response": result}), 400

        kit_token_value = result["result"]["data"].get("kitToken")
        if not kit_token_value:
            return jsonify({"error": "kitToken absent", "imou_response": result}), 400

        KIT_TOKEN_CACHE[cache_key] = {"kitToken": kit_token_value, "domain": domain, "expires_at": now + 300}
        return jsonify({"kitToken": kit_token_value, "domain": domain})

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur génération kit token", "details": str(e)}), 500


@camera_bp.route("/image-proxy", methods=["GET"])
def image_proxy():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url manquante"}), 400
    try:
        from PIL import Image
        import io
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or len(r.content) < 100:
            return jsonify({"error": "image vide ou expirée"}), 404
        content_type = r.headers.get("Content-Type", "")
        if "xml" in content_type.lower() or "text" in content_type.lower():
            return jsonify({"error": "pas une image"}), 404
        img = Image.open(io.BytesIO(r.content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)
        output.seek(0)
        b64      = base64.b64encode(output.read()).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64}"
        return jsonify({"dataUrl": data_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@camera_bp.route("/wakeup", methods=["POST"])
def wakeup_device():
    data      = request.get_json(silent=True) or {}
    device_id = data.get("deviceId")
    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400
    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500
    try:
        result = post_to_imou("/openapi/wakeupDevice", {"token": token, "deviceId": device_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@camera_bp.route("/alarm-video", methods=["GET"])
def alarm_video():
    device_id  = request.args.get("deviceId")
    alarm_id   = request.args.get("alarmId")
    channel_id = request.args.get("channelId", "0")
    if not device_id or not alarm_id:
        return jsonify({"error": "deviceId et alarmId requis"}), 400
    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Token IMOU introuvable"}), 500
    try:
        result = post_to_imou("/openapi/getAlarmVideo", {
            "token": token, "deviceId": device_id, "channelId": channel_id, "alarmId": alarm_id,
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@camera_bp.route("/alerts", methods=["GET"])
def alerts():
    device_id     = request.args.get("deviceId")
    channel_id    = request.args.get("channelId", "0")
    begin_time    = request.args.get("beginTime")
    end_time      = request.args.get("endTime")
    next_alarm_id = request.args.get("nextAlarmId", "-1")
    use_db        = request.args.get("useDb", "true").lower() == "true"

    try:
        count = int(request.args.get("count", 100))
    except ValueError:
        return jsonify({"error": "count doit être un entier"}), 400

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    # ── DB locale en priorité ─────────────────────────────────────────
    if use_db:
        try:
            from database import get_alerts_from_db
            import json

            conn_args = {"device_id": device_id, "days": 7, "limit": count}
            db_alerts = get_alerts_from_db(**conn_args)

            # Filtrer par date si fourni
            if begin_time or end_time:
                from datetime import datetime
                def parse_dt(s):
                    try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                    except: return None
                begin_dt = parse_dt(begin_time) if begin_time else None
                end_dt   = parse_dt(end_time)   if end_time   else None

                filtered = []
                for a in db_alerts:
                    local_date = a.get("local_date") or ""
                    try:
                        alert_dt = datetime.strptime(local_date, "%Y-%m-%d %H:%M:%S")
                        if begin_dt and alert_dt < begin_dt: continue
                        if end_dt   and alert_dt > end_dt:   continue
                        filtered.append(a)
                    except:
                        filtered.append(a)
                db_alerts = filtered

            if db_alerts:
                cleaned = []
                for a in db_alerts:
                    raw = a.get("raw", {})
                    cleaned.append({
                        "alarmId":     a.get("alarm_id"),
                        "time":        a.get("local_date"),
                        "typeLabel":   a.get("type_label", "unknown"),
                        "thumbUrl":    a.get("thumb_url"),
                        "picurlArray": [],
                        "raw": {
                            **raw,
                            "localDate":  a.get("local_date"),
                            "msgType":    a.get("msg_type"),
                            "labelType":  a.get("label_type"),
                            "deviceId":   a.get("device_id"),
                            "name":       a.get("device_name"),
                            "channelId":  a.get("channel_id", "0"),
                        }
                    })
                return jsonify({
                    "success": True, "deviceId": device_id, "channelId": channel_id,
                    "count": len(cleaned), "source": "local_db",
                    "message": f"{len(cleaned)} alertes depuis la base locale",
                    "alarms": cleaned,
                }), 200
        except Exception as e:
            print(f"⚠️ Erreur DB locale, fallback IMOU: {e}")

    # ── Fallback API IMOU ─────────────────────────────────────────────
    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500
    try:
        alert_result   = get_imou_alerts(token=token, device_id=device_id, channel_id=channel_id,
                                          begin_time=begin_time, end_time=end_time,
                                          count=min(count, 30), next_alarm_id=next_alarm_id)
        raw_alarms     = alert_result.get("alarms", [])
        cleaned_alarms = [normalize_alarm(a) for a in raw_alarms]

        # Sauvegarder en DB
        if cleaned_alarms:
            try:
                from database import save_alerts
                save_alerts(raw_alarms, device_id, device_id, "unknown")
            except: pass

        return jsonify({
            "success": True, "deviceId": device_id, "channelId": channel_id,
            "count": len(cleaned_alarms), "source": "imou_api",
            "message": "Alertes récupérées depuis l'API IMOU",
            "alarms": cleaned_alarms,
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Erreur récupération alertes", "details": str(e)}), 500