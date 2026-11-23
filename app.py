"""SocialPulse application factory and entry point."""
import os
from flask import Flask, render_template
from config import Config
from extensions import db, login_manager, csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is missing. Copy .env.example to .env and set it.")

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["REPORT_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    import models  # noqa: F401  (registers tables with SQLAlchemy)
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.uploads import uploads_bp
    from routes.analytics import analytics_bp
    from routes.reports import reports_bp
    for bp in (auth_bp, dashboard_bp, uploads_bp, analytics_bp, reports_bp):
        app.register_blueprint(bp)

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="That page does not exist."), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", code=413, message="That file is too large (50 MB max)."), 413

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return render_template("error.html", code=500, message="Something went wrong on our side."), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
