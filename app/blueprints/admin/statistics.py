"""
Админ-статистика (СТРОГО ТОЛЬКО ЧТЕНИЕ).

Все запросы здесь — исключительно SELECT/aggregate. Модуль НИЧЕГО не пишет в БД:
не создаёт сертификаты, не пересчитывает прогресс, не вызывает db.session.commit().
Используется для дашборда статистики (/admin/statistics) и выгрузок в CSV.

Метрики считаются по обучающимся (role != 'admin'), чтобы тестовые заходы
администратора не искажали цифры. Все три среза согласованы между собой:
overview == сумма по курсам == сумма по студентам.
"""
import csv
import io
from datetime import datetime

from flask import render_template, request, Response
from sqlalchemy import func

from ...extensions import db
from ...models import (
    User,
    Course,
    UserCourse,
    Certificate,
    UserTestAttempt,
    UserLessonProgress,
)
from . import admin_bp


# Человекочитаемые названия статусов записи на курс
STATUS_RU = {
    "enrolled": "Записан",
    "in_progress": "В процессе",
    "completed": "Завершён",
}


# ----------------------------------------------------------------------
#  Вспомогательное
# ----------------------------------------------------------------------
def _as_dt(value):
    """Приводит значение к datetime (на случай, если СУБД вернёт строку — напр. Postgres/raw)."""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _max_dt(*values):
    """Максимальная не-None дата из переданных, либо None."""
    present = [d for d in (_as_dt(v) for v in values) if d is not None]
    return max(present) if present else None


def _fmt_dt(value):
    """Дата для отображения/выгрузки: '16.06.2026 14:30' или ''."""
    dt = _as_dt(value)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else ""


def _pct(part, whole):
    """Безопасный процент с одним знаком после запятой."""
    return round(part / whole * 100, 1) if whole else 0.0


def _student_uc():
    """Базовый запрос по записям на курс ТОЛЬКО для обучающихся (без админов)."""
    return (
        db.session.query(UserCourse)
        .join(User, UserCourse.user_id == User.id)
        .filter(User.role != "admin")
    )


# ----------------------------------------------------------------------
#  Сбор данных
# ----------------------------------------------------------------------
def collect_overview():
    """Общие KPI по платформе (по обучающимся)."""
    total_students = User.query.filter(User.role != "admin").count()

    total_courses = Course.query.count()
    published_courses = Course.query.filter_by(is_published=True).count()

    total_enrollments = _student_uc().count()
    completed = _student_uc().filter(UserCourse.status == "completed").count()
    in_progress = _student_uc().filter(UserCourse.status == "in_progress").count()
    enrolled = _student_uc().filter(UserCourse.status == "enrolled").count()

    # Уникальные студенты, записанные хотя бы на один курс
    active_students = (
        _student_uc()
        .with_entities(func.count(func.distinct(UserCourse.user_id)))
        .scalar()
    ) or 0

    avg_progress = (
        _student_uc()
        .with_entities(func.coalesce(func.avg(UserCourse.progress_percent), 0))
        .scalar()
    ) or 0

    total_certificates = (
        db.session.query(func.count(Certificate.id))
        .select_from(Certificate)
        .join(User, Certificate.user_id == User.id)
        .filter(User.role != "admin")
        .scalar()
    ) or 0
    students_with_cert = (
        db.session.query(func.count(func.distinct(Certificate.user_id)))
        .select_from(Certificate)
        .join(User, Certificate.user_id == User.id)
        .filter(User.role != "admin")
        .scalar()
    ) or 0

    total_attempts = (
        db.session.query(func.count(UserTestAttempt.id))
        .select_from(UserTestAttempt)
        .join(User, UserTestAttempt.user_id == User.id)
        .filter(User.role != "admin")
        .scalar()
    ) or 0
    passed_attempts = (
        db.session.query(func.count(UserTestAttempt.id))
        .select_from(UserTestAttempt)
        .join(User, UserTestAttempt.user_id == User.id)
        .filter(User.role != "admin", UserTestAttempt.is_passed.is_(True))
        .scalar()
    ) or 0

    return {
        "total_students": total_students,
        "active_students": active_students,
        "total_courses": total_courses,
        "published_courses": published_courses,
        "total_enrollments": total_enrollments,
        "completed": completed,
        "in_progress": in_progress,
        "enrolled": enrolled,
        "avg_progress": round(float(avg_progress), 1),
        "total_certificates": total_certificates,
        "students_with_cert": students_with_cert,
        "total_attempts": total_attempts,
        "passed_attempts": passed_attempts,
        "completion_rate": _pct(completed, total_enrollments),
        "pass_rate": _pct(passed_attempts, total_attempts),
    }


def collect_course_rows():
    """Срез по каждому курсу: записи по статусам, сертификаты, средний прогресс."""
    courses = Course.query.order_by(Course.title).all()

    status_map = {}  # course_id -> {status: count}
    for cid, status, cnt in (
        _student_uc()
        .with_entities(UserCourse.course_id, UserCourse.status, func.count(UserCourse.id))
        .group_by(UserCourse.course_id, UserCourse.status)
    ):
        status_map.setdefault(cid, {})[status] = cnt

    avg_map = dict(
        _student_uc()
        .with_entities(UserCourse.course_id, func.avg(UserCourse.progress_percent))
        .group_by(UserCourse.course_id)
        .all()
    )
    cert_map = dict(
        db.session.query(Certificate.course_id, func.count(Certificate.id))
        .join(User, Certificate.user_id == User.id)
        .filter(User.role != "admin")
        .group_by(Certificate.course_id)
        .all()
    )

    rows = []
    for c in courses:
        s = status_map.get(c.id, {})
        enrolled = s.get("enrolled", 0)
        in_progress = s.get("in_progress", 0)
        completed = s.get("completed", 0)
        total = enrolled + in_progress + completed
        rows.append({
            "id": c.id,
            "title": c.title,
            "is_published": c.is_published,
            "enrolled": enrolled,
            "in_progress": in_progress,
            "completed": completed,
            "total": total,
            "certificates": cert_map.get(c.id, 0),
            "avg_progress": round(float(avg_map.get(c.id) or 0), 1),
            "completion_rate": _pct(completed, total),
        })
    return rows


def collect_student_rows(only_passed=False):
    """
    Срез по каждому обучающемуся: записи, завершения, сертификаты, тесты,
    последняя активность. `only_passed=True` — оставить только тех, кто завершил
    хотя бы один курс или получил сертификат.
    """
    students = User.query.filter(User.role != "admin").order_by(User.full_name).all()

    status_map = {}  # user_id -> {status: count}
    for uid, status, cnt in (
        db.session.query(UserCourse.user_id, UserCourse.status, func.count(UserCourse.id))
        .group_by(UserCourse.user_id, UserCourse.status)
    ):
        status_map.setdefault(uid, {})[status] = cnt

    avg_map = dict(
        db.session.query(UserCourse.user_id, func.avg(UserCourse.progress_percent))
        .group_by(UserCourse.user_id).all()
    )
    cert_map = dict(
        db.session.query(Certificate.user_id, func.count(Certificate.id))
        .group_by(Certificate.user_id).all()
    )
    attempts_map = dict(
        db.session.query(UserTestAttempt.user_id, func.count(UserTestAttempt.id))
        .group_by(UserTestAttempt.user_id).all()
    )
    passed_map = dict(
        db.session.query(UserTestAttempt.user_id, func.count(UserTestAttempt.id))
        .filter(UserTestAttempt.is_passed.is_(True))
        .group_by(UserTestAttempt.user_id).all()
    )
    best_score_map = dict(
        db.session.query(UserTestAttempt.user_id, func.max(UserTestAttempt.score_percent))
        .group_by(UserTestAttempt.user_id).all()
    )

    # Компоненты «последней активности»
    last_lesson_map = dict(
        db.session.query(UserLessonProgress.user_id, func.max(UserLessonProgress.completed_at))
        .group_by(UserLessonProgress.user_id).all()
    )
    last_attempt_map = dict(
        db.session.query(UserTestAttempt.user_id, func.max(UserTestAttempt.finished_at))
        .group_by(UserTestAttempt.user_id).all()
    )
    last_enroll_map = dict(
        db.session.query(UserCourse.user_id, func.max(UserCourse.enrolled_at))
        .group_by(UserCourse.user_id).all()
    )
    last_completed_map = dict(
        db.session.query(UserCourse.user_id, func.max(UserCourse.completed_at))
        .group_by(UserCourse.user_id).all()
    )

    rows = []
    for u in students:
        s = status_map.get(u.id, {})
        enrolled = s.get("enrolled", 0)
        in_progress = s.get("in_progress", 0)
        completed = s.get("completed", 0)
        certs = cert_map.get(u.id, 0)
        rows.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "registered_at": u.created_at,
            "enrollments": enrolled + in_progress + completed,
            "in_progress": in_progress,
            "completed": completed,
            "certificates": certs,
            "avg_progress": round(float(avg_map.get(u.id) or 0), 1),
            "attempts": attempts_map.get(u.id, 0),
            "passed_attempts": passed_map.get(u.id, 0),
            "best_score": best_score_map.get(u.id),
            "last_activity": _max_dt(
                last_lesson_map.get(u.id),
                last_attempt_map.get(u.id),
                last_enroll_map.get(u.id),
                last_completed_map.get(u.id),
            ),
            "has_passed": completed > 0 or certs > 0,
        })

    if only_passed:
        rows = [r for r in rows if r["has_passed"]]
    return rows


# ----------------------------------------------------------------------
#  CSV-выгрузка (stdlib, BOM + ';' — корректная кириллица и колонки в Excel)
# ----------------------------------------------------------------------
def _csv_response(basename, header, data_rows):
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM — чтобы Excel распознал UTF-8 и кириллицу
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for row in data_rows:
        writer.writerow(row)

    filename = f"{basename}_{datetime.utcnow():%Y%m%d}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------
#  Маршруты
# ----------------------------------------------------------------------
@admin_bp.route("/statistics")
def statistics():
    filter_passed = request.args.get("filter") == "passed"

    overview = collect_overview()
    course_rows = collect_course_rows()
    all_students = collect_student_rows()
    passed_students = [r for r in all_students if r["has_passed"]]
    student_rows = passed_students if filter_passed else all_students

    return render_template(
        "admin_statistics.html",
        overview=overview,
        course_rows=course_rows,
        student_rows=student_rows,
        total_count=len(all_students),
        passed_count=len(passed_students),
        filter_passed=filter_passed,
        status_ru=STATUS_RU,
    )


@admin_bp.route("/statistics/export/students.csv")
def export_students_csv():
    filter_passed = request.args.get("filter") == "passed"
    rows = collect_student_rows(only_passed=filter_passed)

    header = [
        "ID", "ФИО", "Email", "Дата регистрации",
        "Курсов (всего)", "В процессе", "Завершено", "Сертификатов",
        "Средний прогресс, %", "Попыток тестов", "Успешных попыток",
        "Лучший балл, %", "Последняя активность", "Статус",
    ]
    data = [[
        r["id"], r["full_name"], r["email"], _fmt_dt(r["registered_at"]),
        r["enrollments"], r["in_progress"], r["completed"], r["certificates"],
        r["avg_progress"], r["attempts"], r["passed_attempts"],
        "" if r["best_score"] is None else r["best_score"],
        _fmt_dt(r["last_activity"]),
        "Завершил курс" if r["has_passed"] else "Учится",
    ] for r in rows]

    basename = "students_passed" if filter_passed else "students"
    return _csv_response(basename, header, data)


@admin_bp.route("/statistics/export/courses.csv")
def export_courses_csv():
    rows = collect_course_rows()
    header = [
        "ID", "Курс", "Опубликован", "Записей (всего)", "Записаны",
        "В процессе", "Завершили", "Сертификатов", "Средний прогресс, %",
        "Доля завершивших, %",
    ]
    data = [[
        r["id"], r["title"], "Да" if r["is_published"] else "Нет",
        r["total"], r["enrolled"], r["in_progress"], r["completed"],
        r["certificates"], r["avg_progress"], r["completion_rate"],
    ] for r in rows]
    return _csv_response("courses", header, data)


@admin_bp.route("/statistics/export/enrollments.csv")
def export_enrollments_csv():
    rows = (
        _student_uc()
        .join(Course, UserCourse.course_id == Course.id)
        .order_by(UserCourse.enrolled_at.desc())
        .all()
    )
    header = ["ФИО", "Email", "Курс", "Статус", "Прогресс, %", "Записан", "Завершён"]
    data = [[
        uc.user.full_name, uc.user.email, uc.course.title,
        STATUS_RU.get(uc.status, uc.status), uc.progress_percent,
        _fmt_dt(uc.enrolled_at), _fmt_dt(uc.completed_at),
    ] for uc in rows]
    return _csv_response("enrollments", header, data)


@admin_bp.route("/statistics/export/certificates.csv")
def export_certificates_csv():
    certs = (
        db.session.query(Certificate)
        .join(User, Certificate.user_id == User.id)
        .join(Course, Certificate.course_id == Course.id)
        .filter(User.role != "admin")
        .order_by(Certificate.issue_date.desc())
        .all()
    )
    header = ["Код сертификата", "ФИО", "Email", "Курс", "Дата выдачи"]
    data = [[
        c.certificate_code,
        c.user.full_name if c.user else "",
        c.user.email if c.user else "",
        c.course.title if c.course else "",
        _fmt_dt(c.issue_date),
    ] for c in certs]
    return _csv_response("certificates", header, data)
