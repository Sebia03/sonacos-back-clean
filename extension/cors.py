from flask_cors import CORS

def init_cors(app):

    @app.after_request
    def add_headers(response):
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    CORS(app, resources={
        r"/image-proxy": {"origins": "*"},
        r"/*": {
            "origins": [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5000",
                "http://127.0.0.1:5000"
            ],
            "supports_credentials": True
        }
    })