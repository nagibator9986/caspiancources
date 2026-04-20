import os

from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    abort,
    request,
    current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ...extensions import db
from ...models import (
    Course,
    CourseModule,
    Lesson,
    Test,
    Question,
    AnswerOption,
    CourseTheme,
    LessonBlock,
    CertificateBranding,  # <-- добавили сюда
)
from ...forms import (
    CourseForm,
    ModuleForm,
    LessonForm,
    TestForm,
    QuestionForm,
    CourseThemeForm,
    LessonBlockForm,
)
from . import admin_bp

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from flask_wtf.file import FileField, FileAllowed


# --------------------------
# Хелпер: только админ
# --------------------------
def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)

@admin_bp.before_request
def check_admin():
    admin_required()

# --------------------------
# Хелпер для загрузки файлов
# --------------------------
def allowed_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config.get("ALLOWED_EXTENSIONS", set())

def save_upload(file_storage, subdir: str) -> str | None:
    """Сохраняет файл и возвращает относительный путь (для БД), либо None."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    upload_root = current_app.config["UPLOAD_FOLDER"]
    dir_full = os.path.join(upload_root, subdir)
    os.makedirs(dir_full, exist_ok=True)
    full_path = os.path.join(dir_full, filename)
    file_storage.save(full_path)
    # относительный путь, относительно UPLOAD_FOLDER
    rel_path = os.path.join(subdir, filename).replace("\\", "/")
    return rel_path
class CertificateBrandingForm(FlaskForm):
    company_name = StringField(
        "Название компании на сертификате",
        validators=[DataRequired(), Length(max=255)],
    )
    company_subtitle = StringField(
        "Подзаголовок (описание компании / платформы)",
        validators=[Optional(), Length(max=255)],
    )

    director_title = StringField(
        "Должность подписанта",
        default="Руководитель",
        validators=[Optional(), Length(max=255)],
    )
    director_name = StringField(
        "ФИО подписанта",
        validators=[Optional(), Length(max=255)],
    )

    logo_image = FileField(
        "Логотип (PNG / JPG, опционально)",
        validators=[Optional(), FileAllowed(["png", "jpg", "jpeg"], "Разрешены только изображения PNG/JPG")],
    )
    seal_image = FileField(
        "Печать (PNG / JPG, опционально)",
        validators=[Optional(), FileAllowed(["png", "jpg", "jpeg"], "Разрешены только изображения PNG/JPG")],
    )

    submit = SubmitField("Сохранить настройки")


@admin_bp.route("/certificate-branding", methods=["GET", "POST"])
@login_required
def certificate_branding():
    if not current_user.is_admin():
        abort(403)

    branding = CertificateBranding.get_singleton()
    form = CertificateBrandingForm(obj=branding)

    if form.validate_on_submit():
        branding.company_name = form.company_name.data.strip()
        branding.company_subtitle = (form.company_subtitle.data or "").strip()
        branding.director_title = (form.director_title.data or "").strip()
        branding.director_name = (form.director_name.data or "").strip()

        # Папка для картинок брендинга
        upload_root = os.path.join(
            current_app.root_path,
            "static",
            "uploads",
            "certificate_branding",
        )
        os.makedirs(upload_root, exist_ok=True)

        # Логотип
        if form.logo_image.data:
            logo_file = form.logo_image.data
            filename = secure_filename(logo_file.filename)
            _, ext = os.path.splitext(filename)
            ext = ext.lower() or ".png"

            logo_filename = f"logo_{branding.id}{ext}"
            logo_path_abs = os.path.join(upload_root, logo_filename)
            logo_file.save(logo_path_abs)

            branding.logo_image_path = os.path.join(
                "uploads", "certificate_branding", logo_filename
            ).replace("\\", "/")

        # Печать
        if form.seal_image.data:
            seal_file = form.seal_image.data
            filename = secure_filename(seal_file.filename)
            _, ext = os.path.splitext(filename)
            ext = ext.lower() or ".png"

            seal_filename = f"seal_{branding.id}{ext}"
            seal_path_abs = os.path.join(upload_root, seal_filename)
            seal_file.save(seal_path_abs)

            branding.seal_image_path = os.path.join(
                "uploads", "certificate_branding", seal_filename
            ).replace("\\", "/")

        db.session.commit()
        flash("Настройки сертификата успешно обновлены.", "success")
        return redirect(url_for("admin.certificate_branding"))

    return render_template(
        "admin_certificate_branding.html",
        form=form,
        branding=branding,
    )


# --------------------------
# Дашборд
# --------------------------
@admin_bp.route("/")
def dashboard():
    courses_count = Course.query.count()
    tests_count = Test.query.count()
    themes_count = CourseTheme.query.count()
    return render_template("admin_dashboard.html", courses_count=courses_count, tests_count=tests_count, themes_count=themes_count)

# --------------------------
# Темы оформления
# --------------------------
@admin_bp.route("/themes")
def themes_list():
    themes = CourseTheme.query.all()
    return render_template("admin_themes.html", themes=themes)

@admin_bp.route("/themes/create", methods=["GET", "POST"])
def theme_create():
    form = CourseThemeForm()
    if form.validate_on_submit():
        theme = CourseTheme(
            name=form.name.data,
            primary_color=form.primary_color.data or "#6366F1",
            accent_color=form.accent_color.data or "#22C55E",
            background_color=form.background_color.data or "#F8FAFF",
            card_style=form.card_style.data or "flat",
            font_family=form.font_family.data or "Inter",
        )
        db.session.add(theme)
        db.session.commit()
        flash("Тема создана", "success")
        return redirect(url_for("admin.themes_list"))
    return render_template("admin_theme_form.html", form=form)

# --------------------------
# Курсы
# --------------------------
@admin_bp.route("/courses")
def courses_list():
    courses = Course.query.all()
    return render_template("admin_courses.html", courses=courses)
@admin_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required # если используешь CSRF, можешь убрать exempt и оставить скрытое поле в форме
def delete_course(course_id):
    """
    Удаление курса из админки.
    Кнопка будет с двойным подтверждением на стороне фронта (JS),
    а сюда прилетает уже окончательное решение.
    """
    if not current_user.is_admin():
        abort(403)

    course = Course.query.get_or_404(course_id)

    title = course.title  # чтобы показать в сообщении

    # ВАЖНО: предполагается, что в моделях настроены cascade-отношения
    # (модули, уроки, тесты и т.д. удаляются вместе с курсом).
    db.session.delete(course)
    db.session.commit()

    flash(f"Курс «{title}» был окончательно удалён.", "success")
    return redirect(url_for("admin.courses_list"))  # замени на
@admin_bp.route("/courses/create", methods=["GET", "POST"])
def course_create():
    form = CourseForm()
    # Подгрузим темы в select
    themes = CourseTheme.query.all()
    form.theme_id.choices = [(0, "Без темы")] + [(t.id, t.name) for t in themes]

    if form.validate_on_submit():
        theme_id = form.theme_id.data or None
        if theme_id == 0:
            theme_id = None

        course = Course(
            title=form.title.data,
            slug=form.slug.data,
            description=form.description.data,
            category=form.category.data,
            level=form.level.data,
            image_url=form.image_url.data,
            hero_image_url=form.hero_image_url.data,
            requirements=form.requirements.data,
            outcomes=form.outcomes.data,
            is_sequential=form.is_sequential.data,
            is_published=form.is_published.data,
            theme_id=theme_id,
        )
        db.session.add(course)
        db.session.commit()
        flash("Курс создан", "success")
        return redirect(url_for("admin.courses_list"))
    return render_template("admin_course_form.html", form=form)

@admin_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def course_edit(course_id):
    course = Course.query.get_or_404(course_id)
    form = CourseForm(obj=course)
    themes = CourseTheme.query.all()
    form.theme_id.choices = [(0, "Без темы")] + [(t.id, t.name) for t in themes]
    form.theme_id.data = course.theme_id or 0

    if form.validate_on_submit():
        theme_id = form.theme_id.data or None
        if theme_id == 0:
            theme_id = None

        course.title = form.title.data
        course.slug = form.slug.data
        course.description = form.description.data
        course.category = form.category.data
        course.level = form.level.data
        course.image_url = form.image_url.data
        course.hero_image_url = form.hero_image_url.data
        course.requirements = form.requirements.data
        course.outcomes = form.outcomes.data
        course.is_sequential = form.is_sequential.data
        course.is_published = form.is_published.data
        course.theme_id = theme_id
        db.session.commit()
        flash("Курс сохранен", "success")
        return redirect(url_for("admin.courses_list"))
    return render_template("admin_course_form.html", form=form, course=course)

# --------------------------
# Модули
# --------------------------
@admin_bp.route("/courses/<int:course_id>/modules")
def modules_list(course_id):
    course = Course.query.get_or_404(course_id)
    modules = CourseModule.query.filter_by(course_id=course.id).order_by(CourseModule.order_index).all()
    return render_template("admin_modules.html", course=course, modules=modules)

@admin_bp.route("/courses/<int:course_id>/modules/create", methods=["GET", "POST"])
def module_create(course_id):
    course = Course.query.get_or_404(course_id)
    form = ModuleForm()
    if form.validate_on_submit():
        module = CourseModule(
            course_id=course.id,
            title=form.title.data,
            description=form.description.data,
            order_index=form.order_index.data or 0,
        )
        db.session.add(module)
        db.session.commit()
        flash("Модуль создан", "success")
        return redirect(url_for("admin.modules_list", course_id=course.id))
    return render_template("admin_module_form.html", form=form, course=course)

@admin_bp.route("/modules/<int:module_id>/edit", methods=["GET", "POST"])
def module_edit(module_id):
    module = CourseModule.query.get_or_404(module_id)
    form = ModuleForm(obj=module)
    if form.validate_on_submit():
        form.populate_obj(module)
        db.session.commit()
        flash("Модуль сохранен", "success")
        return redirect(url_for("admin.modules_list", course_id=module.course_id))
    return render_template("admin_module_form.html", form=form, course=module.course)

# --------------------------
# Уроки
# --------------------------
@admin_bp.route("/modules/<int:module_id>/lessons")
def lessons_list(module_id):
    module = CourseModule.query.get_or_404(module_id)
    lessons = Lesson.query.filter_by(module_id=module.id).order_by(Lesson.order_index).all()
    return render_template("admin_lessons.html", module=module, lessons=lessons)

@admin_bp.route("/modules/<int:module_id>/lessons/create", methods=["GET", "POST"])
def lesson_create(module_id):
    module = CourseModule.query.get_or_404(module_id)
    form = LessonForm()
    if form.validate_on_submit():
        lesson = Lesson(
            module_id=module.id,
            title=form.title.data,
            summary=form.summary.data,
            order_index=form.order_index.data or 0,
            is_preview=form.is_preview.data,
        )
        db.session.add(lesson)
        db.session.commit()
        flash("Урок создан", "success")
        return redirect(url_for("admin.lessons_list", module_id=module.id))
    return render_template("admin_lesson_form.html", form=form, module=module)

@admin_bp.route("/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
def lesson_edit(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    form = LessonForm(obj=lesson)
    if form.validate_on_submit():
        lesson.title = form.title.data
        lesson.summary = form.summary.data
        lesson.order_index = form.order_index.data or 0
        lesson.is_preview = form.is_preview.data
        db.session.commit()
        flash("Урок сохранен", "success")
        return redirect(url_for("admin.lessons_list", module_id=lesson.module_id))
    return render_template("admin_lesson_form.html", form=form, module=lesson.module)

# --------------------------
# Блоки урока (ТЕКСТ/ВИДЕО/ФАЙЛЫ)
# --------------------------
@admin_bp.route("/lessons/<int:lesson_id>/blocks")
def lesson_blocks_list(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    blocks = LessonBlock.query.filter_by(lesson_id=lesson.id).order_by(LessonBlock.order_index).all()
    return render_template("admin_lesson_blocks.html", lesson=lesson, blocks=blocks)

@admin_bp.route("/lessons/<int:lesson_id>/blocks/create", methods=["GET", "POST"])
def lesson_block_create(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    form = LessonBlockForm()
    if form.validate_on_submit():
        block = LessonBlock(
            lesson_id=lesson.id,
            block_type=form.block_type.data,
            title=form.title.data,
            text_content=form.text_content.data,
            order_index=form.order_index.data or 0,
        )

        # Обработка файлов (для video/image/file)
        upload = request.files.get("upload_file")
        if form.block_type.data == "video":
            if form.video_url.data:
                block.video_source = "youtube"
                block.video_url = form.video_url.data
            elif upload:
                rel_path = save_upload(upload, f"course_{lesson.module.course_id}/lessons/{lesson.id}/video")
                if rel_path:
                    block.video_source = "upload"
                    block.video_file_path = rel_path

        elif form.block_type.data == "image":
            if upload:
                rel_path = save_upload(upload, f"course_{lesson.module.course_id}/lessons/{lesson.id}/images")
                if rel_path:
                    block.image_path = rel_path

        elif form.block_type.data == "file":
            if upload:
                rel_path = save_upload(upload, f"course_{lesson.module.course_id}/lessons/{lesson.id}/files")
                if rel_path:
                    block.file_path = rel_path
                    block.file_name = upload.filename

        db.session.add(block)
        db.session.commit()
        flash("Блок урока создан", "success")
        return redirect(url_for("admin.lesson_blocks_list", lesson_id=lesson.id))

    return render_template("admin_lesson_block_form.html", form=form, lesson=lesson)

# --------------------------
# Тесты / вопросы (как у тебя, с минимальными изменениями)
# --------------------------

@admin_bp.route("/modules/<int:module_id>/tests")
def module_tests(module_id):
    module = CourseModule.query.get_or_404(module_id)
    tests = Test.query.filter_by(module_id=module.id, type="module").all()
    return render_template("admin_tests.html", module=module, tests=tests)

@admin_bp.route("/courses/<int:course_id>/final-tests")
def course_tests(course_id):
    course = Course.query.get_or_404(course_id)
    tests = Test.query.filter_by(course_id=course.id, type="final").all()
    return render_template("admin_tests.html", course=course, tests=tests)

@admin_bp.route("/modules/<int:module_id>/tests/create", methods=["GET", "POST"])
def module_test_create(module_id):
    module = CourseModule.query.get_or_404(module_id)
    form = TestForm()
    if form.validate_on_submit():
        max_attempts = form.max_attempts.data or None
        test = Test(
            module_id=module.id,
            type="module",
            title=form.title.data,
            description=form.description.data,
            pass_score_percent=form.pass_score_percent.data,
            max_attempts=max_attempts,
        )
        db.session.add(test)
        db.session.commit()
        flash("Тест по модулю создан", "success")
        return redirect(url_for("admin.module_tests", module_id=module.id))
    return render_template("admin_test_form.html", form=form, module=module)

@admin_bp.route("/courses/<int:course_id>/final-tests/create", methods=["GET", "POST"])
def course_test_create(course_id):
    course = Course.query.get_or_404(course_id)
    form = TestForm()
    if form.validate_on_submit():
        max_attempts = form.max_attempts.data or None
        test = Test(
            course_id=course.id,
            type="final",
            title=form.title.data,
            description=form.description.data,
            pass_score_percent=form.pass_score_percent.data,
            max_attempts=max_attempts,
        )
        db.session.add(test)
        db.session.commit()
        flash("Финальный тест создан", "success")
        return redirect(url_for("admin.course_tests", course_id=course.id))
    return render_template("admin_test_form.html", form=form, course=course)

@admin_bp.route("/tests/<int:test_id>/questions")
def questions_list(test_id):
    test = Test.query.get_or_404(test_id)
    questions = Question.query.filter_by(test_id=test.id).order_by(Question.order_index).all()
    return render_template("admin_questions.html", test=test, questions=questions)

@admin_bp.route("/tests/<int:test_id>/questions/create", methods=["GET", "POST"])
def question_create(test_id):
    test = Test.query.get_or_404(test_id)
    form = QuestionForm()
    if form.validate_on_submit():
        q = Question(
            test_id=test.id,
            text=form.text.data,
            type=form.type.data,
            points=form.points.data,
            order_index=0,
        )
        db.session.add(q)
        db.session.commit()
        flash("Вопрос создан. Теперь добавьте варианты ответов.", "success")
        return redirect(url_for("admin.answers_manage", question_id=q.id))
    return render_template("admin_question_form.html", form=form, test=test)

@admin_bp.route("/questions/<int:question_id>/answers", methods=["GET", "POST"])
def answers_manage(question_id):
    question = Question.query.get_or_404(question_id)
    if request.method == "POST":
        AnswerOption.query.filter_by(question_id=question.id).delete()
        for i in range(1, 5):
            text = request.form.get(f"opt_text_{i}")
            is_correct = bool(request.form.get(f"opt_correct_{i}"))
            if text:
                opt = AnswerOption(question_id=question.id, text=text, is_correct=is_correct)
                db.session.add(opt)
        db.session.commit()
        flash("Варианты ответов сохранены", "success")
        return redirect(url_for("admin.questions_list", test_id=question.test_id))

    options = AnswerOption.query.filter_by(question_id=question.id).all()
    while len(options) < 4:
        options.append(None)
    return render_template("admin_answers_manage.html", question=question, options=options[:4])
