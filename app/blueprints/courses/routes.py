import io
import os
from flask import render_template, abort, make_response, send_file, current_app
from flask_login import login_required, current_user
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from ...models import Certificate
from ...models import Certificate
from . import courses_bp
from ...models import Certificate, CertificateBranding
from flask import render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from flask import render_template, redirect, url_for, flash, abort, request, make_response
import pdfkit
from ...extensions import db, csrf
from ...models import (
    Course,
    CourseModule,
    Lesson,
    UserCourse,
    UserLessonProgress,
    Test,
    Question,
    AnswerOption,
    UserTestAttempt,
    Certificate,
    LessonBlock,
)
import uuid
from datetime import datetime

from . import courses_bp


# ==========================
#   ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================

def ensure_enrolled(user, course):
    """Гарантируем, что пользователь записан на курс."""
    user_course = UserCourse.query.filter_by(user_id=user.id, course_id=course.id).first()
    if not user_course:
        user_course = UserCourse(
            user_id=user.id,
            course_id=course.id,
            status="enrolled",
            progress_percent=0,
        )
        db.session.add(user_course)
        db.session.commit()
    return user_course

@courses_bp.route("/certificate/<int:cert_id>/pdf")
@login_required
def certificate_pdf(cert_id):
    cert = Certificate.query.get_or_404(cert_id)

    # доступ только своему сертификату или админу
    if cert.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    # безопасно достаём дату (если когда-то добавишь created_at — сразу подхватится)
    issued_date = getattr(cert, "created_at", None)

    # --- Настраиваем шрифты (чтобы русские буквы отображались красиво) ---
    # Положи, например, файл DejaVuSans.ttf в: app/static/fonts/DejaVuSans.ttf
    font_name = "Helvetica"  # запасной вариант, если ttf не найдётся
    try:
        font_path = os.path.join(current_app.root_path, "static", "fonts", "DejaVuSans.ttf")
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            font_name = "DejaVuSans"
    except Exception:
        # если что-то пошло не так — просто останемся на Helvetica
        pass

    # --- Готовим PDF в память ---
    buffer = io.BytesIO()
    page_width, page_height = A4  # 595 x 842 pt примерно

    c = canvas.Canvas(buffer, pagesize=A4)

    # Отступы
    margin = 20 * mm

    # Фон/рамка
    c.setStrokeColor(colors.HexColor("#CBD5E1"))  # slate-300
    c.setLineWidth(2)
    c.roundRect(
        margin / 2,
        margin / 2,
        page_width - margin,
        page_height - margin,
        10 * mm,
        stroke=1,
        fill=0,
    )

    # Логотип / компания
    c.setFont(font_name, 10)
    c.setFillColor(colors.HexColor("#94A3B8"))  # slate-400
    c.drawString(margin, page_height - margin, "Официальный документ")

    c.setFont(font_name, 14)
    c.setFillColor(colors.HexColor("#0F172A"))  # slate-900
    c.drawString(margin, page_height - margin - 18, 'ИП «Illuminart»')

    c.setFont(font_name, 9)
    c.setFillColor(colors.HexColor("#64748B"))  # slate-500
    c.drawString(margin, page_height - margin - 32, "Образовательная платформа Lerna")

    # Номер сертификата и дата справа
    code_text = f"Сертификат № {cert.certificate_code}"
    if issued_date:
        date_text = f"Выдан: {issued_date.strftime('%d.%m.%Y')}"
    else:
        date_text = "Дата выдачи: —"

    c.setFont(font_name, 9)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawRightString(page_width - margin, page_height - margin, code_text)
    c.drawRightString(page_width - margin, page_height - margin - 14, date_text)

    # Заголовок "СЕРТИФИКАТ"
    c.setFont(font_name, 24)
    c.setFillColor(colors.HexColor("#0F172A"))
    title = "СЕРТИФИКАТ"
    c.drawCentredString(page_width / 2, page_height - 120, title)

    # Подзаголовок "Настоящим подтверждается, что"
    c.setFont(font_name, 10)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(
        page_width / 2,
        page_height - 145,
        "Настоящим подтверждается, что",
    )

    # Имя/почта владельца
    owner_name = (
        cert.user.full_name
        if cert.user and getattr(cert.user, "full_name", None)
        else cert.user.email
        if cert.user
        else "Участник курса"
    )
    c.setFont(font_name, 16)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawCentredString(page_width / 2, page_height - 170, owner_name)

    # Текст про прохождение курса
    c.setFont(font_name, 11)
    c.setFillColor(colors.HexColor("#475569"))

    course_line = f"успешно прошёл(а) обучение по программе «{cert.course.title}»"
    c.drawCentredString(page_width / 2, page_height - 200, course_line)

    c.setFont(font_name, 10)
    text_y = page_height - 225
    text_lines = [
        "в рамках которой изучил(а) материалы курса, прошёл(а) тематические модули и успешно сдал(а)",
        "итоговое тестирование, подтвердив необходимый уровень усвоения программы.",
    ]
    for line in text_lines:
        c.drawCentredString(page_width / 2, text_y, line)
        text_y -= 15

    # Блок с дополнительной информацией (внизу по центру)
    info_y = page_height - 280
    c.setFont(font_name, 9)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(
        page_width / 2,
        info_y,
        "Формат обучения: онлайн, с фиксацией прогресса и результатами тестирования.",
    )
    c.drawCentredString(
        page_width / 2,
        info_y - 14,
        "Сертификат может быть использован в портфолио и при отклике на вакансии.",
    )

    # Подпись слева внизу
    bottom_margin = 80
    c.setFont(font_name, 9)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin, bottom_margin + 40, 'Руководитель ИП «Illuminart»')

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(margin, bottom_margin + 25, margin + 120, bottom_margin + 25)
    c.setFont(font_name, 8)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(margin, bottom_margin + 15, "(подпись)")

    # Печать справа
    center_x = page_width - margin - 60
    center_y = bottom_margin + 40
    radius_outer = 35
    radius_inner = 26

    # внешнее кольцо
    c.setStrokeColor(colors.HexColor("#0EA5E9"))  # sky-500
    c.setLineWidth(2)
    c.circle(center_x, center_y, radius_outer, stroke=1, fill=0)

    # внутреннее кольцо
    c.setLineWidth(1)
    c.setStrokeColor(colors.HexColor("#38BDF8"))  # светлее
    c.circle(center_x, center_y, radius_inner, stroke=1, fill=0)

    # текст внутри печати
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont(font_name, 8)
    c.drawCentredString(center_x, center_y + 5, 'ИП «Illuminart»')
    c.setFont(font_name, 6)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawCentredString(center_x, center_y - 7, "Образовательные услуги")

    # Завершение страницы
    c.showPage()
    c.save()

    buffer.seek(0)
    filename = f"certificate_{cert.certificate_code or cert.id}.pdf"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


def maybe_create_certificate(user, course):
    """Создаём сертификат, если его ещё нет."""
    existing = Certificate.query.filter_by(user_id=user.id, course_id=course.id).first()
    if existing:
        return existing

    code = f"{course.id}-{user.id}-{uuid.uuid4().hex[:8]}"
    cert = Certificate(
        user_id=user.id,
        course_id=course.id,
        certificate_code=code,
    )
    db.session.add(cert)
    db.session.commit()
    return cert


# ==========================
#   КУРСЫ
# ==========================

@courses_bp.route("/course/<slug>")
@login_required
def course_detail(slug):
    """Страница курса (описание, инфо, кнопка записи)."""
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    modules = (
        CourseModule.query
        .filter_by(course_id=course.id)
        .order_by(CourseModule.order_index)
        .all()
    )

    user_course = None
    if current_user.is_authenticated:
        user_course = UserCourse.query.filter_by(
            user_id=current_user.id,
            course_id=course.id,
        ).first()

    return render_template(
        "course_detail.html",
        course=course,
        modules=modules,
        user_course=user_course,
    )


@courses_bp.route("/test/<int:test_id>", methods=["GET", "POST"])
@login_required
def take_test(test_id):
    """
    Прохождение теста (модульного или финального).
    Для финального теста дополнительно проверяется, что все уроки курса пройдены.
    """
    test = Test.query.get_or_404(test_id)

    # Определяем, к какому курсу относится тест
    course = None
    if test.course_id:
        course = test.course
    elif test.module_id:
        course = test.module.course

    # Если тест привязан к курсу/модулю — удостоверимся, что пользователь записан
    user_course = None
    if course:
        user_course = ensure_enrolled(current_user, course)

        # Если тест финальный — блокируем доступ, пока не пройдены все уроки
        if test.type == "final":
            total_lessons = (
                Lesson.query
                .join(CourseModule, Lesson.module_id == CourseModule.id)
                .filter(CourseModule.course_id == course.id)
                .count()
            )

            completed_lessons = (
                UserLessonProgress.query
                .join(Lesson, UserLessonProgress.lesson_id == Lesson.id)
                .join(CourseModule, Lesson.module_id == CourseModule.id)
                .filter(
                    UserLessonProgress.user_id == current_user.id,
                    UserLessonProgress.is_completed.is_(True),
                    CourseModule.course_id == course.id,
                )
                .count()
            )

            if total_lessons == 0 or completed_lessons < total_lessons:
                flash(
                    "Финальный тест доступен только после прохождения всех модулей и уроков курса.",
                    "warning",
                )
                return redirect(url_for("courses.course_learn", slug=course.slug))

    # Загружаем вопросы теста
    questions = (
        Question.query
        .filter_by(test_id=test.id)
        .order_by(Question.order_index)
        .all()
    )

    if request.method == "POST":
        # Подсчёт результата
        total_points = 0
        earned_points = 0

        for q in questions:
            total_points += q.points
            chosen_id = request.form.get(f"q{q.id}")
            if not chosen_id:
                continue

            try:
                chosen_id_int = int(chosen_id)
            except ValueError:
                continue

            answer = AnswerOption.query.filter_by(
                id=chosen_id_int,
                question_id=q.id,
            ).first()

            if answer and answer.is_correct:
                earned_points += q.points

        score_percent = int(earned_points / total_points * 100) if total_points > 0 else 0
        is_passed = score_percent >= test.pass_score_percent

        # ✅ Убрали taken_at — оставили только существующие поля
        attempt = UserTestAttempt(
            user_id=current_user.id,
            test_id=test.id,
            score_percent=score_percent,
            is_passed=is_passed,
        )
        db.session.add(attempt)

        # Если это финальный тест и он успешно пройден — завершаем курс и выдаём сертификат
        if course and is_passed and test.type == "final":
            if user_course:
                user_course.status = "completed"
                db.session.commit()
            maybe_create_certificate(current_user, course)
        else:
            db.session.commit()

        if is_passed:
            flash(
                f"Тест пройден! Результат: {score_percent}% (проходной: {test.pass_score_percent}%)",
                "success",
            )
        else:
            flash(
                f"Тест не пройден. Результат: {score_percent}% (проходной: {test.pass_score_percent}%). "
                f"Вы можете попробовать ещё раз.",
                "warning",
            )

        if course:
            return redirect(url_for("courses.course_learn", slug=course.slug))
        else:
            return redirect(url_for("courses.dashboard"))

    # GET — показ формы теста
    return render_template(
        "take_test.html",
        test=test,
        questions=questions,
        course=course,
    )



@courses_bp.route("/course/<slug>/enroll", methods=["POST"])
@login_required
@csrf.exempt  # если захочешь включить CSRF, убери это и добавь {{ csrf_token() }} в форму
def enroll_course(slug):
    """Записаться на курс."""
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    ensure_enrolled(current_user, course)
    flash("Вы записаны на курс", "success")
    return redirect(url_for("courses.course_learn", slug=slug))


@courses_bp.route("/course/<slug>/learn")
@login_required
def course_learn(slug):
    """
    Страница «Программа курса / прохождение».

    Здесь считаем:
    - общее количество уроков,
    - количество завершённых уроков,
    - прогресс курса,
    - флаг all_lessons_completed (для блокировки финального теста).
    """
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    modules = (
        CourseModule.query
        .filter_by(course_id=course.id)
        .order_by(CourseModule.order_index)
        .all()
    )

    # гарантируем, что пользователь записан
    user_course = ensure_enrolled(current_user, course)

    # считаем общее количество уроков в курсе
    total_lessons = (
        Lesson.query
        .join(CourseModule, Lesson.module_id == CourseModule.id)
        .filter(CourseModule.course_id == course.id)
        .count()
    )

    # считаем количество завершённых уроков пользователем
    completed_lessons = (
        UserLessonProgress.query
        .join(Lesson, UserLessonProgress.lesson_id == Lesson.id)
        .join(CourseModule, Lesson.module_id == CourseModule.id)
        .filter(
            UserLessonProgress.user_id == current_user.id,
            UserLessonProgress.is_completed.is_(True),
            CourseModule.course_id == course.id,
        )
        .count()
    )

    all_lessons_completed = total_lessons > 0 and completed_lessons >= total_lessons

    # обновляем прогресс курса
    if total_lessons > 0:
        progress_percent = int(completed_lessons / total_lessons * 100)
        user_course.progress_percent = progress_percent

        if all_lessons_completed:
            user_course.status = "completed"
            # здесь при желании можно создавать сертификат
            # maybe_create_certificate(current_user, course)
        elif completed_lessons > 0 and user_course.status == "enrolled":
            user_course.status = "in_progress"

        db.session.commit()
    else:
        all_lessons_completed = False

    return render_template(
        "course_learn.html",
        course=course,
        modules=modules,
        user_course=user_course,
        all_lessons_completed=all_lessons_completed,
    )


# ==========================
#   УРОКИ
# ==========================

@courses_bp.route("/lesson/<int:lesson_id>/complete", methods=["POST"])
@login_required
@csrf.exempt  # можно снять exempt, если в форме есть {{ csrf_token() }}
def complete_lesson(lesson_id):
    """
    Отметить урок как пройденный.
    Обновляет UserLessonProgress и пересчитывает прогресс курса.
    """
    lesson = Lesson.query.get_or_404(lesson_id)
    course = lesson.module.course

    # гарантируем, что пользователь записан
    user_course = ensure_enrolled(current_user, course)

    progress = UserLessonProgress.query.filter_by(
        user_id=current_user.id,
        lesson_id=lesson.id,
    ).first()

    if not progress:
        progress = UserLessonProgress(
            user_id=current_user.id,
            lesson_id=lesson.id,
            is_completed=True,
            completed_at=datetime.utcnow(),
        )
        db.session.add(progress)
    else:
        if not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = datetime.utcnow()

    # перерасчет прогресса курса
    total_lessons = (
        Lesson.query
        .join(CourseModule, Lesson.module_id == CourseModule.id)
        .filter(CourseModule.course_id == course.id)
        .count()
    )

    completed_lessons = (
        UserLessonProgress.query
        .join(Lesson, UserLessonProgress.lesson_id == Lesson.id)
        .join(CourseModule, Lesson.module_id == CourseModule.id)
        .filter(
            UserLessonProgress.user_id == current_user.id,
            UserLessonProgress.is_completed.is_(True),
            CourseModule.course_id == course.id,
        )
        .count()
    )

    if total_lessons > 0:
        user_course.progress_percent = int(completed_lessons / total_lessons * 100)

        if user_course.progress_percent > 0 and user_course.status == "enrolled":
            user_course.status = "in_progress"

        if completed_lessons >= total_lessons:
            user_course.status = "completed"
            # можно автоматически выдать сертификат
            # maybe_create_certificate(current_user, course)

    db.session.commit()
    flash("Урок отмечен как пройденный", "success")
    return redirect(url_for("courses.course_learn", slug=course.slug))


@courses_bp.route("/course/<slug>/lesson/<int:lesson_id>")
@login_required
def lesson_view(slug, lesson_id):
    """
    Просмотр конкретного урока внутри курса.
    """
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    lesson = Lesson.query.get_or_404(lesson_id)

    if lesson.module.course_id != course.id:
        abort(404)

    user_course = ensure_enrolled(current_user, course)

    blocks = (
        LessonBlock.query
        .filter_by(lesson_id=lesson.id)
        .order_by(LessonBlock.order_index)
        .all()
    )
    modules = (
        CourseModule.query
        .filter_by(course_id=course.id)
        .order_by(CourseModule.order_index)
        .all()
    )

    return render_template(
        "lesson_view.html",
        course=course,
        lesson=lesson,
        blocks=blocks,
        modules=modules,
        user_course=user_course,
    )


# ==========================
#   ЛИЧНЫЙ КАБИНЕТ / СЕРТИФИКАТЫ
# ==========================

@courses_bp.route("/dashboard")
@login_required
def dashboard():
    user_courses = UserCourse.query.filter_by(user_id=current_user.id).all()
    certificates = Certificate.query.filter_by(user_id=current_user.id).all()
    return render_template(
        "dashboard.html",
        user_courses=user_courses,
        certificates=certificates,
    )


@courses_bp.route("/certificates")
@login_required
def certificates():
    certificates_list = Certificate.query.filter_by(user_id=current_user.id).all()
    return render_template("certificates.html", certificates=certificates_list)


@courses_bp.route("/certificates/<int:cert_id>")
@login_required
def certificate_view(cert_id):
    certificate = Certificate.query.get_or_404(cert_id)

    # проверка доступа: свой сертификат или админ
    if certificate.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    branding = CertificateBranding.get_singleton()

    return render_template(
        "certificate_view.html",
        certificate=certificate,
        branding=branding,
    )