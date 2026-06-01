import os

from flask import Flask, send_from_directory
from sqlalchemy import inspect, text

from config import Config
from .extensions import db, login_manager, csrf
from .models import User


def _ensure_branding_columns():
    """
    Лёгкая авто-миграция: добавляет новые колонки в `certificate_branding`,
    если БД создана старой версией приложения. Запускается на старте.
    Работает для SQLite и PostgreSQL.
    """
    try:
        insp = inspect(db.engine)
        if "certificate_branding" not in insp.get_table_names():
            return
        existing = {col["name"] for col in insp.get_columns("certificate_branding")}
        to_add = []
        if "partner_name" not in existing:
            to_add.append(("partner_name", "VARCHAR(255)"))
        if "partner_subtitle" not in existing:
            to_add.append(("partner_subtitle", "VARCHAR(255)"))
        if "partner_logo_image_path" not in existing:
            to_add.append(("partner_logo_image_path", "VARCHAR(255)"))
        if not to_add:
            return
        with db.engine.begin() as conn:
            for name, decl in to_add:
                conn.execute(text(f"ALTER TABLE certificate_branding ADD COLUMN {name} {decl}"))
    except Exception:
        # Если что-то пошло не так — пропускаем; приложение продолжит работу.
        pass


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

    # Создание БД и авто-миграция новых колонок брендинга
    with app.app_context():
        db.create_all()
        _ensure_branding_columns()

    return app
