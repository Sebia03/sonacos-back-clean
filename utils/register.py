from blueprint.camera import camera_bp
from blueprint.auth import auth_bp
from blueprint.users import users_bp
from utils.error_class import CheckError

BLUEPRINTS = [
    camera_bp,
    auth_bp,
    users_bp,
]

def register_routes(app):
    try:
        for bp in BLUEPRINTS:
            app.register_blueprint(bp)
    except Exception as err:
        raise CheckError(f'Failed to register blueprint: {err}', 500)