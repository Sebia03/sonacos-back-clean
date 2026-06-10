import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from datetime import timedelta
from database import get_user_by_email, verify_password

auth_bp = Blueprint("auth", __name__)


# ==========================
# 🔑 LOGIN
# ==========================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    email    = data.get("email") or data.get("username")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    user = get_user_by_email(email)

    if not user or not verify_password(password, user["password"]):
        return jsonify({"error": "Identifiants invalides"}), 401

    additional_claims = {
        "role":  user["role"],
        "site":  user["site"],
        "email": user["email"],
    }

    access_token = create_access_token(
        identity=str(user["id"]),
        additional_claims=additional_claims,
        expires_delta=timedelta(hours=2),
    )

    return jsonify({
        "message":      "Login successful",
        "access_token": access_token,
        "user": {
            "id":    user["id"],
            "email": user["email"],
            "role":  user["role"],
            "site":  user["site"],
        }
    }), 200


# ==========================
# 🚪 LOGOUT
# ==========================
@auth_bp.route("/logout", methods=["POST"])
def logout():
    return jsonify({"message": "Logout successful"}), 200


# ==========================
# 👤 MOI (profil connecté)
# ==========================
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    claims = get_jwt()
    return jsonify({
        "id":    get_jwt_identity(),
        "email": claims.get("email"),
        "role":  claims.get("role"),
        "site":  claims.get("site"),
    })