import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _resolve_secret_key() -> str:
    env_key = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    # На случай локальной разработки без .env — генерируем стабильный ключ и кладём в файл,
    # чтобы сессии не сбрасывались при перезапуске.
    key_file = os.path.join(BASE_DIR, ".flask_secret")
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    generated = secrets.token_hex(32)
    try:
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(generated)
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return generated


class Config:
    SECRET_KEY = _resolve_secret_key()

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "app.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Загрузка файлов (видео, картинки, документы)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 МБ
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "webp",
        "mp4", "webm", "mov",
        "pdf", "docx", "pptx", "xlsx", "zip",
    }

    # Cookies / сессии
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    # SESSION_COOKIE_SECURE=True следует включать только под HTTPS
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_COOKIE_SECURE", "0") == "1"

    # Шрифты для PDF-сертификатов
    PDF_FONT_REGULAR = os.path.join(BASE_DIR, "app", "static", "fonts", "DejaVuSans.ttf")
    PDF_FONT_BOLD = os.path.join(BASE_DIR, "app", "static", "fonts", "DejaVuSans-Bold.ttf")
