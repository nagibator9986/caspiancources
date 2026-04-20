import os
from flask import Flask, send_from_directory
from config import Config
from .extensions import db, login_manager, csrf
from .models import User

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Инициализация расширений
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Папка для upload'ов
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Роут для отдачи загруженных файлов
    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    # Регистрация blueprints
    from .blueprints.auth import auth_bp
    from .blueprints.main import main_bp
    from .blueprints.courses import courses_bp
    from .blueprints.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Создание БД
    with app.app_context():
        db.create_all()

    return app
