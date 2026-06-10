from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from database import get_all_users, create_user, update_user, delete_user

users_bp = Blueprint("users", __name__)

VALID_SITES = ["dakar", "louga", "kaolack", "diourbel"]
VALID_ROLES = ["superadmin", "admin_site"]


def require_superadmin():
    claims = get_jwt()
    if claims.get("role") != "superadmin":
        return jsonify({"error": "Accès réservé au super administrateur"}), 403
    return None


# ==========================
# 📋 LISTE DES UTILISATEURS
# ==========================
@users_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    err = require_superadmin()
    if err: return err
    return jsonify(get_all_users())


# ==========================
# ➕ CRÉER UN UTILISATEUR
# ==========================
@users_bp.route("/users", methods=["POST"])
@jwt_required()
def add_user():
    err = require_superadmin()
    if err: return err

    data     = request.get_json(silent=True) or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    role     = data.get("role", "admin_site")
    site     = data.get("site")

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    if role not in VALID_ROLES:
        return jsonify({"error": f"Rôle invalide. Valeurs acceptées : {VALID_ROLES}"}), 400

    if role == "admin_site" and site not in VALID_SITES:
        return jsonify({"error": f"Site invalide. Valeurs acceptées : {VALID_SITES}"}), 400

    if role == "superadmin":
        site = None

    success, msg = create_user(email, password, role, site)
    if not success:
        return jsonify({"error": msg}), 409

    return jsonify({"message": msg}), 201


# ==========================
# ✏️ MODIFIER UN UTILISATEUR
# ==========================
@users_bp.route("/users/<int:user_id>", methods=["PUT"])
@jwt_required()
def edit_user(user_id):
    err = require_superadmin()
    if err: return err

    data     = request.get_json(silent=True) or {}
    email    = data.get("email")
    password = data.get("password")
    role     = data.get("role")
    site     = data.get("site")

    if role and role not in VALID_ROLES:
        return jsonify({"error": f"Rôle invalide. Valeurs acceptées : {VALID_ROLES}"}), 400

    if role == "admin_site" and site and site not in VALID_SITES:
        return jsonify({"error": f"Site invalide. Valeurs acceptées : {VALID_SITES}"}), 400

    success, msg = update_user(user_id, email, password, role, site)
    if not success:
        return jsonify({"error": msg}), 400

    return jsonify({"message": msg})


# ==========================
# 🗑️ SUPPRIMER UN UTILISATEUR
# ==========================
@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def remove_user(user_id):
    err = require_superadmin()
    if err: return err

    success, msg = delete_user(user_id)
    if not success:
        return jsonify({"error": msg}), 400

    return jsonify({"message": msg})