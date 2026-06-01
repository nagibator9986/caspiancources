"""
Создание демо-студента с УЖЕ ПРОЙДЕННЫМ курсом и выданным сертификатом.

Что делает скрипт:
1. Создаёт (или обновляет) пользователя — обычного студента.
2. Записывает его на указанный курс (по slug).
3. Отмечает ВСЕ уроки курса как пройденные.
4. Для каждого теста курса (модульного и финального) создаёт попытку
   с результатом 100% и флагом is_passed=True.
5. Выдаёт сертификат и проставляет статус курса = completed.

Использование:
    python create_demo_student.py

Можно переопределить через переменные окружения:
    DEMO_EMAIL=...  DEMO_PASSWORD=...  DEMO_FULL_NAME=...  DEMO_COURSE_SLUG=...  python create_demo_student.py

Скрипт идемпотентен: повторный запуск не создаёт дублей —
он обновит пароль/ФИО и убедится, что прогресс и сертификат на месте.
"""

import os
import sys
from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import (
    User,
    Course,
    CourseModule,
    Lesson,
    UserCourse,
    UserLessonProgress,
    Test,
    UserTestAttempt,
    Certificate,
)

# Перехватываем функцию выдачи сертификата из роутов, чтобы код и формат совпадали.
from app.blueprints.courses.routes import maybe_create_certificate


DEFAULT_EMAIL = "demo.student@example.com"
DEFAULT_PASSWORD = "Demo12345"
DEFAULT_FULL_NAME = "Демо Студент"
DEFAULT_COURSE_SLUG = "ai-tools-career"


def upsert_user(email: str, password: str, full_name: str) -> User:
    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if user:
        user.full_name = full_name or user.full_name
        user.set_password(password)
        action = "обновлён"
    else:
        user = User(email=email, full_name=full_name or email, role="student")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        action = "создан"
    db.session.commit()
    return user, action


def enroll(user: User, course: Course) -> UserCourse:
    uc = UserCourse.query.filter_by(user_id=user.id, course_id=course.id).first()
    if not uc:
        uc = UserCourse(
            user_id=user.id,
            course_id=course.id,
            status="enrolled",
            progress_percent=0,
            enrolled_at=datetime.utcnow(),
        )
        db.session.add(uc)
        db.session.commit()
    return uc


def complete_all_lessons(user: User, course: Course) -> int:
    lessons = (
        Lesson.query
        .join(CourseModule, Lesson.module_id == CourseModule.id)
        .filter(CourseModule.course_id == course.id)
        .all()
    )
    n_new = 0
    now = datetime.utcnow()
    for lesson in lessons:
        progress = UserLessonProgress.query.filter_by(
            user_id=user.id, lesson_id=lesson.id
        ).first()
        if progress is None:
            db.session.add(
                UserLessonProgress(
                    user_id=user.id,
                    lesson_id=lesson.id,
                    is_completed=True,
                    completed_at=now,
                )
            )
            n_new += 1
        elif not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = now
            n_new += 1
    db.session.commit()
    return len(lessons), n_new


def add_passing_attempts(user: User, course: Course) -> int:
    """
    Для каждого теста курса (модульного и финального) — добавляем 1 успешную попытку,
    если её ещё нет, со 100% результатом.
    """
    tests = []
    # финальные тесты курса
    tests += Test.query.filter_by(course_id=course.id).all()
    # модульные тесты курса
    for module in CourseModule.query.filter_by(course_id=course.id).all():
        tests += Test.query.filter_by(module_id=module.id).all()

    n_new = 0
    now = datetime.utcnow()
    for test in tests:
        existing = UserTestAttempt.query.filter_by(
            user_id=user.id, test_id=test.id, is_passed=True
        ).first()
        if existing:
            continue
        db.session.add(
            UserTestAttempt(
                user_id=user.id,
                test_id=test.id,
                started_at=now,
                finished_at=now,
                score_percent=100,
                is_passed=True,
            )
        )
        n_new += 1
    db.session.commit()
    return len(tests), n_new


def finalize_course(user: User, course: Course) -> Certificate:
    uc = UserCourse.query.filter_by(user_id=user.id, course_id=course.id).first()
    if uc:
        uc.status = "completed"
        uc.progress_percent = 100
        if not uc.completed_at:
            uc.completed_at = datetime.utcnow()
        db.session.commit()

    return maybe_create_certificate(user, course)


def main() -> int:
    email = os.environ.get("DEMO_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("DEMO_PASSWORD", DEFAULT_PASSWORD)
    full_name = os.environ.get("DEMO_FULL_NAME", DEFAULT_FULL_NAME)
    course_slug = os.environ.get("DEMO_COURSE_SLUG", DEFAULT_COURSE_SLUG)

    app = create_app()
    with app.app_context():
        course = Course.query.filter_by(slug=course_slug).first()
        if not course:
            print(f"❌ Курс со slug '{course_slug}' не найден.")
            print("   Сначала запустите сидер: python seed_html_css_course.py")
            return 1

        user, user_action = upsert_user(email, password, full_name)
        enroll(user, course)
        n_lessons, n_marked = complete_all_lessons(user, course)
        n_tests, n_attempts = add_passing_attempts(user, course)
        cert = finalize_course(user, course)

        print("=" * 60)
        print(f"✅ Демо-студент {user_action}: {user.email}")
        print(f"   ФИО:     {user.full_name}")
        print(f"   Пароль:  {password}")
        print(f"   Курс:    «{course.title}»  (slug={course.slug})")
        print(f"   Уроков пройдено:     {n_lessons}  (новых отмечено: {n_marked})")
        print(f"   Попыток тестов:      {n_tests}   (добавлено: {n_attempts})")
        print(f"   Сертификат №:        {cert.certificate_code}")
        print(f"   Выдан:               {cert.issue_date.strftime('%d.%m.%Y')}")
        print("=" * 60)
        print(f"🔑 Логин:  {user.email}")
        print(f"🔑 Пароль: {password}")
        print(f"🎓 Открыть сертификат: /certificates/{cert.id}")
        print(f"🎓 Скачать PDF:       /certificate/{cert.id}/pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
