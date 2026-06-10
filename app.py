import os
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, jwt_required
from extension.cors import init_cors
from extension.logging import init_logging
from utils.register import register_routes
from dotenv import load_dotenv
from database import init_db

load_dotenv()

def create_app(test_config=None):
    app = Flask(__name__)

    # JWT config
    app.config["JWT_SECRET_KEY"]           = os.getenv("JWT_SECRET_KEY", "fallback-secret-key")
    app.config["JWT_TOKEN_LOCATION"]       = ["headers"]
    app.config["JWT_HEADER_NAME"]          = "Authorization"
    app.config["JWT_HEADER_TYPE"]          = "Bearer"
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 7200

    JWTManager(app)

    init_db()
    init_logging(app)
    init_cors(app)
    register_routes(app)

    # Scheduler pour les rapports hebdomadaires
    from scheduler import init_scheduler
    init_scheduler(app)
    @app.route("/sync-alerts-now", methods=["POST"])
    @jwt_required()
    def sync_alerts_now():
        from alert_sync import sync_all_alerts
        try:
            sync_all_alerts()
            return jsonify({"message": "Synchronisation terminée"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    # Route de test pour envoyer un rapport immédiatement
    @app.route("/send-report-now", methods=["POST"])
    @jwt_required()
    def send_report_now():
        from email_report import send_weekly_reports
        try:
            send_weekly_reports()
            return jsonify({"message": "Rapports envoyés avec succès"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if test_config is not None:
        app.config.update(test_config)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))