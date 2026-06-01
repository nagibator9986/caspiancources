import io
import os
import uuid
from datetime import datetime

from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    abort,
    request,
    send_file,
    current_app,
)
from flask_login import login_required, current_user

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ...extensions import db
from ...models import (
    Course,
    CourseModule,
    Lesson,
    LessonBlock,
    UserCourse,
    UserLessonProgress,
    Test,
    Question,
    AnswerOption,
    UserTestAttempt,
    Certificate,
    CertificateBranding,
)
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


def maybe_create_certificate(user, course):
    """Создаём сертификат, если его ещё нет, и возвращаем существующий/новый."""
    existing = Certificate.query.filter_by(user_id=user.id, course_id=course.id).first()
    if existing:
        return existing

    code = f"CCL-{course.id:03d}-{user.id:04d}-{uuid.uuid4().hex[:6].upper()}"
    cert = Certificate(
        user_id=user.id,
        course_id=course.id,
        certificate_code=code,
        issue_date=datetime.utcnow(),
    )
    db.session.add(cert)
    db.session.commit()
    return cert


def _recalculate_course_progress(user, course):
    """Пересчитывает прогресс курса для пользователя и возвращает (total, completed, user_course)."""
    user_course = ensure_enrolled(user, course)

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
            UserLessonProgress.user_id == user.id,
            UserLessonProgress.is_completed.is_(True),
            CourseModule.course_id == course.id,
        )
        .count()
    )

    if total_lessons > 0:
        user_course.progress_percent = int(completed_lessons / total_lessons * 100)
        if completed_lessons >= total_lessons:
            if user_course.status != "completed":
                user_course.status = "completed"
                user_course.completed_at = datetime.utcnow()
        elif user_course.progress_percent > 0 and user_course.status == "enrolled":
            user_course.status = "in_progress"

    db.session.commit()
    return total_lessons, completed_lessons, user_course


# ==========================
#   КУРСЫ
# ==========================

@courses_bp.route("/course/<slug>")
@login_required
def course_detail(slug):
    """Страница курса (описание, программа, кнопка записи)."""
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    modules = (
        CourseModule.query
        .filter_by(course_id=course.id)
        .order_by(CourseModule.order_index)
        .all()
    )

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


@courses_bp.route("/course/<slug>/enroll", methods=["POST"])
@login_required
def enroll_course(slug):
    """Записаться на курс."""
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    ensure_enrolled(current_user, course)
    flash("Вы записаны на курс", "success")
    return redirect(url_for("courses.course_learn", slug=slug))


@courses_bp.route("/course/<slug>/learn")
@login_required
def course_learn(slug):
    """Страница «Программа курса / прохождение»."""
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    modules = (
        CourseModule.query
        .filter_by(course_id=course.id)
        .order_by(CourseModule.order_index)
        .all()
    )

    total_lessons, completed_lessons, user_course = _recalculate_course_progress(current_user, course)
    all_lessons_completed = total_lessons > 0 and completed_lessons >= total_lessons

    # Подмешиваем флаг "финальный тест пройден" для разблокировки сертификата
    has_final_pass = (
        db.session.query(UserTestAttempt)
        .join(Test, UserTestAttempt.test_id == Test.id)
        .filter(
            UserTestAttempt.user_id == current_user.id,
            UserTestAttempt.is_passed.is_(True),
            Test.course_id == course.id,
            Test.type == "final",
        )
        .first()
        is not None
    )
    certificate = Certificate.query.filter_by(
        user_id=current_user.id, course_id=course.id
    ).first()

    return render_template(
        "course_learn.html",
        course=course,
        modules=modules,
        user_course=user_course,
        all_lessons_completed=all_lessons_completed,
        has_final_pass=has_final_pass,
        certificate=certificate,
    )


# ==========================
#   УРОКИ
# ==========================

@courses_bp.route("/course/<slug>/lesson/<int:lesson_id>")
@login_required
def lesson_view(slug, lesson_id):
    """Просмотр конкретного урока внутри курса."""
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

    progress = UserLessonProgress.query.filter_by(
        user_id=current_user.id,
        lesson_id=lesson.id,
    ).first()
    is_completed = bool(progress and progress.is_completed)

    return render_template(
        "lesson_view.html",
        course=course,
        lesson=lesson,
        blocks=blocks,
        modules=modules,
        user_course=user_course,
        is_completed=is_completed,
    )


@courses_bp.route("/lesson/<int:lesson_id>/complete", methods=["POST"])
@login_required
def complete_lesson(lesson_id):
    """Отметить урок как пройденный."""
    lesson = Lesson.query.get_or_404(lesson_id)
    course = lesson.module.course

    ensure_enrolled(current_user, course)

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
    elif not progress.is_completed:
        progress.is_completed = True
        progress.completed_at = datetime.utcnow()

    db.session.commit()
    _recalculate_course_progress(current_user, course)

    flash("Урок отмечен как пройденный", "success")
    return redirect(url_for("courses.course_learn", slug=course.slug))


# ==========================
#   ТЕСТЫ
# ==========================

@courses_bp.route("/test/<int:test_id>", methods=["GET", "POST"])
@login_required
def take_test(test_id):
    """
    Прохождение теста (модульного или финального).
    Для финального теста дополнительно проверяется, что все уроки курса пройдены.
    Корректно поддерживаются single и multiple типы вопросов и max_attempts.
    """
    test = Test.query.get_or_404(test_id)

    # Курс, к которому относится тест
    course = None
    if test.course_id:
        course = test.course
    elif test.module_id:
        course = test.module.course

    user_course = None
    if course:
        user_course = ensure_enrolled(current_user, course)

        if test.type == "final":
            total_lessons, completed_lessons, _ = _recalculate_course_progress(current_user, course)
            if total_lessons == 0 or completed_lessons < total_lessons:
                flash(
                    "Финальный тест доступен только после прохождения всех модулей и уроков курса.",
                    "warning",
                )
                return redirect(url_for("courses.course_learn", slug=course.slug))

    # Проверка количества попыток
    attempts_made = UserTestAttempt.query.filter_by(
        user_id=current_user.id, test_id=test.id
    ).count()
    if test.max_attempts and attempts_made >= test.max_attempts:
        flash(
            f"Достигнут лимит попыток для этого теста ({test.max_attempts}).",
            "danger",
        )
        if course:
            return redirect(url_for("courses.course_learn", slug=course.slug))
        return redirect(url_for("courses.dashboard"))

    questions = (
        Question.query
        .filter_by(test_id=test.id)
        .order_by(Question.order_index, Question.id)
        .all()
    )

    if request.method == "POST":
        total_points = 0
        earned_points = 0

        for q in questions:
            total_points += q.points

            field_name = f"q_{q.id}"
            chosen_raw = request.form.getlist(field_name)
            if not chosen_raw:
                continue

            try:
                chosen_ids = {int(x) for x in chosen_raw if x.isdigit() or x.lstrip("-").isdigit()}
            except (TypeError, ValueError):
                continue
            if not chosen_ids:
                continue

            options = AnswerOption.query.filter_by(question_id=q.id).all()
            correct_ids = {o.id for o in options if o.is_correct}

            if q.type == "single":
                # Берём первый выбранный — radio даёт ровно один
                first = next(iter(chosen_ids))
                if first in correct_ids:
                    earned_points += q.points
            elif q.type == "multiple":
                # Полное совпадение множеств — иначе вопрос не засчитан
                if chosen_ids == correct_ids and correct_ids:
                    earned_points += q.points
            else:
                # Открытый ответ — без автоматической проверки
                pass

        score_percent = int(round(earned_points / total_points * 100)) if total_points > 0 else 0
        is_passed = score_percent >= (test.pass_score_percent or 0)

        attempt = UserTestAttempt(
            user_id=current_user.id,
            test_id=test.id,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            score_percent=score_percent,
            is_passed=is_passed,
        )
        db.session.add(attempt)
        db.session.commit()

        # Финальный тест пройден — закрываем курс и выдаём сертификат
        cert = None
        if course and is_passed and test.type == "final":
            if user_course:
                user_course.status = "completed"
                user_course.completed_at = datetime.utcnow()
                user_course.progress_percent = 100
                db.session.commit()
            cert = maybe_create_certificate(current_user, course)

        if is_passed:
            if cert:
                flash(
                    f"🎉 Поздравляем! Финальный тест пройден ({score_percent}%). "
                    f"Сертификат № {cert.certificate_code} доступен в личном кабинете.",
                    "success",
                )
            else:
                flash(
                    f"Тест пройден! Результат: {score_percent}% "
                    f"(проходной балл — {test.pass_score_percent}%)",
                    "success",
                )
        else:
            flash(
                f"Тест не пройден. Результат: {score_percent}% "
                f"(проходной балл — {test.pass_score_percent}%). Можно попробовать ещё раз.",
                "warning",
            )

        if course:
            return redirect(url_for("courses.course_learn", slug=course.slug))
        return redirect(url_for("courses.dashboard"))

    return render_template(
        "take_test.html",
        test=test,
        questions=questions,
        course=course,
        attempts_made=attempts_made,
    )


# ==========================
#   ЛИЧНЫЙ КАБИНЕТ
# ==========================

@courses_bp.route("/dashboard")
@login_required
def dashboard():
    user_courses = (
        UserCourse.query
        .filter_by(user_id=current_user.id)
        .order_by(UserCourse.enrolled_at.desc())
        .all()
    )
    certificates = (
        Certificate.query
        .filter_by(user_id=current_user.id)
        .order_by(Certificate.issue_date.desc())
        .all()
    )
    return render_template(
        "dashboard.html",
        user_courses=user_courses,
        certificates=certificates,
    )


# ==========================
#   СЕРТИФИКАТЫ
# ==========================

@courses_bp.route("/certificates")
@login_required
def certificates():
    certificates_list = (
        Certificate.query
        .filter_by(user_id=current_user.id)
        .order_by(Certificate.issue_date.desc())
        .all()
    )
    return render_template("certificates.html", certificates=certificates_list)


@courses_bp.route("/certificates/<int:cert_id>")
@login_required
def certificate_view(cert_id):
    certificate = Certificate.query.get_or_404(cert_id)

    if certificate.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    branding = CertificateBranding.get_singleton()

    return render_template(
        "certificate_view.html",
        certificate=certificate,
        branding=branding,
    )


# --------------------------
#  Шрифты для PDF (регистрация один раз)
# --------------------------
_PDF_FONTS_REGISTERED = False


def _register_pdf_fonts():
    global _PDF_FONTS_REGISTERED
    if _PDF_FONTS_REGISTERED:
        return ("DejaVuSans", "DejaVuSans-Bold")

    reg_path = current_app.config.get("PDF_FONT_REGULAR")
    bold_path = current_app.config.get("PDF_FONT_BOLD")

    regular_name = "Helvetica"
    bold_name = "Helvetica-Bold"

    try:
        if reg_path and os.path.exists(reg_path):
            pdfmetrics.registerFont(TTFont("DejaVuSans", reg_path))
            regular_name = "DejaVuSans"
        if bold_path and os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
            bold_name = "DejaVuSans-Bold"
    except Exception:
        # При ошибке остаёмся на стандартных шрифтах — кириллица может побиться,
        # но PDF всё равно сгенерируется и приложение не упадёт.
        pass

    _PDF_FONTS_REGISTERED = True
    return regular_name, bold_name


def _branding_image_path(rel_path):
    """Возвращает абсолютный путь к изображению брендинга или None."""
    if not rel_path:
        return None
    base = current_app.root_path  # .../app
    full = os.path.join(base, "static", rel_path.lstrip("/"))
    return full if os.path.exists(full) else None


@courses_bp.route("/certificate/<int:cert_id>/pdf")
@login_required
def certificate_pdf(cert_id):
    """Генерирует красивый PDF-сертификат с учётом брендинга и поддержкой кириллицы."""
    cert = Certificate.query.get_or_404(cert_id)

    if cert.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    branding = CertificateBranding.get_singleton()
    font_regular, font_bold = _register_pdf_fonts()

    buffer = io.BytesIO()
    page_size = landscape(A4)  # 842 x 595 pt
    page_w, page_h = page_size
    c = canvas.Canvas(buffer, pagesize=page_size)

    # ============ ФОН И РАМКИ ============
    # Светлая кремовая подложка
    c.setFillColor(colors.HexColor("#FFFBF5"))
    c.rect(0, 0, page_w, page_h, stroke=0, fill=1)

    # Декоративные «акварельные» круги
    c.saveState()
    c.setFillColorRGB(0.98, 0.72, 0.45, alpha=0.18)  # оранжевый
    c.circle(60, page_h - 60, 130, stroke=0, fill=1)
    c.setFillColorRGB(0.99, 0.85, 0.61, alpha=0.22)  # светло-янтарный
    c.circle(page_w - 80, 80, 160, stroke=0, fill=1)
    c.setFillColorRGB(0.93, 0.58, 0.21, alpha=0.10)  # глубокий оранжевый
    c.circle(page_w - 220, page_h - 40, 90, stroke=0, fill=1)
    c.restoreState()

    # Внешняя двойная рамка
    margin = 18 * mm
    inner_margin = margin + 4 * mm

    c.setStrokeColor(colors.HexColor("#E2A55F"))
    c.setLineWidth(2.2)
    c.roundRect(margin, margin, page_w - 2 * margin, page_h - 2 * margin, 12, stroke=1, fill=0)

    c.setStrokeColor(colors.HexColor("#F4C58A"))
    c.setLineWidth(0.8)
    c.roundRect(
        inner_margin, inner_margin,
        page_w - 2 * inner_margin, page_h - 2 * inner_margin,
        8, stroke=1, fill=0,
    )

    # Уголковые декоры (точки)
    def corner_dots(cx, cy):
        c.setFillColor(colors.HexColor("#E2A55F"))
        for dx, dy in [(0, 0), (8, 0), (0, 8), (8, 8)]:
            c.circle(cx + dx, cy + dy, 0.9, stroke=0, fill=1)

    corner_dots(margin + 6, margin + 6)
    corner_dots(page_w - margin - 14, margin + 6)
    corner_dots(margin + 6, page_h - margin - 14)
    corner_dots(page_w - margin - 14, page_h - margin - 14)

    # ============ ШАПКА: ДВА ЛОГОТИПА ============
    top_y = page_h - margin - 18 * mm
    issued_date = cert.issue_date or datetime.utcnow()

    # --- Слева: логотип Illuminart + название ---
    logo_path = _branding_image_path(branding.logo_image_path)
    if logo_path:
        try:
            c.drawImage(
                ImageReader(logo_path),
                margin + 12 * mm, top_y - 14 * mm,
                width=22 * mm, height=22 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    c.setFillColor(colors.HexColor("#C2782C"))
    c.setFont(font_regular, 8)
    c.drawString(margin + 40 * mm, top_y - 2 * mm, "ОФИЦИАЛЬНЫЙ ДОКУМЕНТ")

    c.setFillColor(colors.HexColor("#1F2937"))
    c.setFont(font_bold, 12)
    c.drawString(margin + 40 * mm, top_y - 8 * mm, branding.company_name or 'ИП "Illuminart"')

    if branding.company_subtitle:
        c.setFont(font_regular, 8)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(margin + 40 * mm, top_y - 13 * mm, branding.company_subtitle)

    # --- В центре сверху: бейдж «Сертификат о прохождении курса» ---
    badge_text = "СЕРТИФИКАТ О ПРОХОЖДЕНИИ КУРСА"
    badge_w = pdfmetrics.stringWidth(badge_text, font_regular, 7.5) + 14
    badge_x = (page_w - badge_w) / 2
    badge_y = top_y - 6 * mm
    c.setFillColor(colors.HexColor("#0F172A"))
    c.roundRect(badge_x, badge_y, badge_w, 5.5 * mm, 6, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setFont(font_regular, 7.5)
    c.drawCentredString(page_w / 2, badge_y + 1.8 * mm, badge_text)

    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont(font_regular, 7.5)
    c.drawCentredString(page_w / 2, top_y - 13 * mm,
                        f"№ {cert.certificate_code}  ·  {issued_date.strftime('%d.%m.%Y')}")

    # --- Справа: логотип партнёра + название ---
    partner_logo_path = _branding_image_path(branding.partner_logo_image_path)
    partner_name = branding.partner_name or "Caspian College"
    partner_sub = branding.partner_subtitle or "Учебный партнёр"

    if partner_logo_path:
        try:
            c.drawImage(
                ImageReader(partner_logo_path),
                page_w - margin - 34 * mm, top_y - 14 * mm,
                width=22 * mm, height=22 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass
    else:
        # Лёгкая плашка-заглушка, если логотип партнёра не загружен
        c.setStrokeColor(colors.HexColor("#7DD3FC"))
        c.setLineWidth(1.2)
        c.roundRect(page_w - margin - 34 * mm, top_y - 14 * mm, 22 * mm, 22 * mm, 4, stroke=1, fill=0)
        c.setFillColor(colors.HexColor("#0EA5E9"))
        c.setFont(font_bold, 7)
        c.drawCentredString(page_w - margin - 23 * mm, top_y - 7 * mm, "LOGO")

    c.setFillColor(colors.HexColor("#0EA5E9"))
    c.setFont(font_regular, 8)
    c.drawRightString(page_w - margin - 38 * mm, top_y - 2 * mm, partner_sub.upper())

    c.setFillColor(colors.HexColor("#1F2937"))
    c.setFont(font_bold, 12)
    c.drawRightString(page_w - margin - 38 * mm, top_y - 8 * mm, partner_name)

    # ============ ЗАГОЛОВОК (по центру) ============
    # Координаты считаем от низа страницы (origin reportlab — нижний-левый).
    # page_h (A4 landscape) = 210 mm. Вертикальная сетка:
    #
    #   161-176 mm — header (логотип, компания, № сертификата)
    #   148-152 mm — мелкое «CERTIFICATE»
    #   132-144 mm — большой заголовок «СЕРТИФИКАТ»
    #   126-130 mm — орнаментальная линия с ромбиком
    #   115-120 mm — «Настоящим подтверждается, что»
    #   100-110 mm — имя
    #    95-99  mm — подчёркивание под именем
    #    83-88  mm — «успешно прошёл…»
    #    73-80  mm — название курса
    #    58-67  mm — описание (две строки)
    #    38-54  mm — три info-блока
    #    10-32  mm — подпись (слева) + печать (справа)
    center_x = page_w / 2

    c.setFont(font_regular, 8)
    c.setFillColor(colors.HexColor("#C2782C"))
    c.drawCentredString(center_x, 150 * mm, "C E R T I F I C A T E")

    c.setFont(font_bold, 30)
    c.setFillColor(colors.HexColor("#1F2937"))
    c.drawCentredString(center_x, 134 * mm, "СЕРТИФИКАТ")

    # Тонкая разделительная линия с ромбиком
    c.setStrokeColor(colors.HexColor("#E2A55F"))
    c.setLineWidth(0.8)
    line_y = 127 * mm
    c.line(center_x - 50 * mm, line_y, center_x - 8 * mm, line_y)
    c.line(center_x + 8 * mm, line_y, center_x + 50 * mm, line_y)
    c.saveState()
    c.translate(center_x, line_y)
    c.rotate(45)
    c.setFillColor(colors.HexColor("#E2A55F"))
    c.rect(-2.4, -2.4, 4.8, 4.8, stroke=0, fill=1)
    c.restoreState()

    # ============ «НАСТОЯЩИМ ПОДТВЕРЖДАЕТСЯ» + ИМЯ ============
    c.setFont(font_regular, 10)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(center_x, 118 * mm, "Настоящим подтверждается, что")

    owner_name = (
        cert.user.full_name
        if cert.user and cert.user.full_name
        else (cert.user.email if cert.user else "Участник курса")
    )
    name_size = 22
    while pdfmetrics.stringWidth(owner_name, font_bold, name_size) > page_w - 2 * margin - 80 and name_size > 12:
        name_size -= 1
    c.setFont(font_bold, name_size)
    c.setFillColor(colors.HexColor("#1F2937"))
    c.drawCentredString(center_x, 103 * mm, owner_name)

    # Подчёркивание под именем
    name_width = pdfmetrics.stringWidth(owner_name, font_bold, name_size)
    underline_w = min(name_width + 30, page_w - 2 * margin - 60)
    c.setStrokeColor(colors.HexColor("#E2A55F"))
    c.setLineWidth(0.8)
    c.line(center_x - underline_w / 2, 98 * mm,
           center_x + underline_w / 2, 98 * mm)

    # ============ ТЕКСТ ПРО КУРС ============
    c.setFont(font_regular, 11)
    c.setFillColor(colors.HexColor("#374151"))
    c.drawCentredString(center_x, 87 * mm,
                        "успешно прошёл(а) обучение по образовательной программе")

    course_title = f"«{cert.course.title}»"
    title_size = 14
    while pdfmetrics.stringWidth(course_title, font_bold, title_size) > page_w - 2 * margin - 60 and title_size > 9:
        title_size -= 1
    c.setFont(font_bold, title_size)
    c.setFillColor(colors.HexColor("#1F2937"))
    c.drawCentredString(center_x, 77 * mm, course_title)

    c.setFont(font_regular, 9.5)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawCentredString(
        center_x, 66 * mm,
        "освоил(а) ключевые темы курса, прошёл(а) тематические модули и успешно сдал(а) итоговый тест,",
    )
    c.drawCentredString(
        center_x, 60 * mm,
        "подтвердив требуемый уровень усвоения учебного материала.",
    )

    # ============ КОД ПРОВЕРКИ (один центральный блок) ============
    code_text = cert.certificate_code
    code_size = 13
    while pdfmetrics.stringWidth(code_text, font_bold, code_size) > 70 * mm and code_size > 9:
        code_size -= 0.5

    code_block_w = max(pdfmetrics.stringWidth(code_text, font_bold, code_size) + 22 * mm, 70 * mm)
    code_block_h = 14 * mm
    code_block_x = (page_w - code_block_w) / 2
    code_block_y = 40 * mm

    c.setFillColor(colors.HexColor("#FFF3E0"))
    c.roundRect(code_block_x, code_block_y, code_block_w, code_block_h, 6, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#F4C58A"))
    c.setLineWidth(0.7)
    c.roundRect(code_block_x, code_block_y, code_block_w, code_block_h, 6, stroke=1, fill=0)

    c.setFillColor(colors.HexColor("#C2782C"))
    c.setFont(font_regular, 7)
    c.drawCentredString(page_w / 2, code_block_y + code_block_h - 4.5 * mm, "КОД ПРОВЕРКИ")

    c.setFillColor(colors.HexColor("#1F2937"))
    c.setFont(font_bold, code_size)
    c.drawCentredString(page_w / 2, code_block_y + 4 * mm, code_text)

    # ============ ПОДПИСЬ И ПЕЧАТЬ ============
    sign_y = 8 * mm  # базовая координата для нижнего ряда

    # Подпись (слева)
    c.setFont(font_regular, 7.5)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin + 16 * mm, sign_y + 18 * mm,
                 (branding.director_title or "Руководитель").upper())

    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.8)
    c.line(margin + 16 * mm, sign_y + 13 * mm, margin + 16 * mm + 60 * mm, sign_y + 13 * mm)

    c.setFont(font_bold, 10)
    c.setFillColor(colors.HexColor("#1F2937"))
    c.drawString(margin + 16 * mm, sign_y + 8 * mm,
                 branding.director_name or "Ответственное лицо")

    c.setFont(font_regular, 7)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(margin + 16 * mm, sign_y + 3 * mm,
                 "(подпись и расшифровка)")

    # Печать (справа)
    seal_path = _branding_image_path(branding.seal_image_path)
    seal_cx = page_w - margin - 26 * mm
    seal_cy = sign_y + 14 * mm
    radius = 11 * mm

    if seal_path:
        try:
            c.drawImage(
                ImageReader(seal_path),
                seal_cx - radius, seal_cy - radius,
                width=radius * 2, height=radius * 2,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            _draw_default_seal(c, seal_cx, seal_cy, radius, branding, font_regular, font_bold)
    else:
        _draw_default_seal(c, seal_cx, seal_cy, radius, branding, font_regular, font_bold)

    c.showPage()
    c.save()

    buffer.seek(0)
    filename = f"certificate_{cert.certificate_code}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


def _draw_default_seal(c, cx, cy, r, branding, font_regular, font_bold):
    """Рисует декоративную «печать» поверх PDF, когда нет загруженного изображения."""
    c.saveState()
    c.setStrokeColor(colors.HexColor("#C2782C"))
    c.setLineWidth(2)
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.setLineWidth(0.7)
    c.circle(cx, cy, r - 4, stroke=1, fill=0)

    c.setFillColor(colors.HexColor("#C2782C"))
    c.setFont(font_bold, 8)
    c.drawCentredString(cx, cy + 2, (branding.company_name or "CCL")[:22])
    c.setFont(font_regular, 6)
    c.drawCentredString(cx, cy - 7, "Образовательные услуги")
    c.restoreState()
