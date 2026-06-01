"""
Создание/обновление администратора платформы.

Использование:
    python create_admin.py

Можно переопределить креды через переменные окружения:
    ADMIN_EMAIL=... ADMIN_PASSWORD=... ADMIN_FULL_NAME=... python create_admin.py

Скрипт идемпотентен:
- если пользователь с таким email уже есть — обновит пароль и поднимет роль до admin;
- если нет — создаст нового админа.
"""

import os
import sys

from app import create_app
from app.extensions import db
from app.models import User


DEFAULT_EMAIL = "tleubekov.super@gmail.com"
DEFAULT_PASSWORD = "Azamat65"
DEFAULT_FULL_NAME = "Тлеубеков А.Г."


def create_or_update_admin(email: str, password: str, full_name: str) -> User:
    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()

    if user:
        user.role = "admin"
        if full_name:
            user.full_name = full_name
        user.set_password(password)
        action = "обновлён"
    else:
        user = User(
            email=email,
            full_name=full_name or email,
            role="admin",
        )
        user.set_password(password)
        db.session.add(user)
        action = "создан"

    db.session.commit()
    return user, action


def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("ADMIN_PASSWORD", DEFAULT_PASSWORD)
    full_name = os.environ.get("ADMIN_FULL_NAME", DEFAULT_FULL_NAME)

    app = create_app()
    with app.app_context():
        user, action = create_or_update_admin(email, password, full_name)
        print(f"Админ {action}: {user.email}  (ФИО: {user.full_name}, роль: {user.role})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
