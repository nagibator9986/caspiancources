from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    BooleanField,
    TextAreaField,
    IntegerField,
    SelectField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
)


# =========================
#   AUTH ФОРМЫ
# =========================

class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("ФИО", validators=[DataRequired(), Length(min=3, max=255)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        "Повтор пароля",
        validators=[DataRequired(), EqualTo("password", message="Пароли должны совпадать")],
    )
    submit = SubmitField("Зарегистрироваться")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember_me = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")


# =========================
#   КУРСЫ / МОДУЛИ / УРОКИ
# =========================

class CourseForm(FlaskForm):
    title = StringField("Название курса", validators=[DataRequired()])
    slug = StringField("Slug", validators=[DataRequired()])
    description = TextAreaField("Описание", validators=[Optional()])
    category = StringField("Категория", validators=[Optional()])
    level = StringField("Уровень", validators=[Optional()])

    image_url = StringField("URL обложки (если без загрузки файла)", validators=[Optional()])
    hero_image_url = StringField("URL фонового изображения", validators=[Optional()])

    requirements = TextAreaField("Требования к студенту", validators=[Optional()])
    outcomes = TextAreaField("Результаты обучения", validators=[Optional()])

    is_sequential = BooleanField("Проходить модули по порядку")
    is_published = BooleanField("Опубликован")

    # тема подставляется в админке через .choices
    theme_id = SelectField("Тема оформления", coerce=int, validators=[Optional()])

    submit = SubmitField("Сохранить курс")


class ModuleForm(FlaskForm):
    title = StringField("Название модуля", validators=[DataRequired()])
    description = TextAreaField("Описание", validators=[Optional()])
    order_index = IntegerField("Порядок", validators=[Optional()])
    submit = SubmitField("Сохранить модуль")


class LessonForm(FlaskForm):
    title = StringField("Название урока", validators=[DataRequired()])
    summary = TextAreaField("Краткое описание", validators=[Optional()])
    order_index = IntegerField("Порядок", validators=[Optional()])
    is_preview = BooleanField("Доступен без записи на курс (превью)")
    submit = SubmitField("Сохранить урок")


# =========================
#   ТЕСТЫ / ВОПРОСЫ
# =========================

class TestForm(FlaskForm):
    title = StringField("Название теста", validators=[DataRequired()])
    description = TextAreaField("Описание", validators=[Optional()])
    pass_score_percent = IntegerField("Проходной %", validators=[DataRequired()])
    max_attempts = IntegerField(
        "Максимум попыток (0 или пусто — бесконечно)",
        validators=[Optional()],
    )
    submit = SubmitField("Сохранить тест")


class QuestionForm(FlaskForm):
    text = TextAreaField("Текст вопроса", validators=[DataRequired()])
    type = SelectField(
        "Тип вопроса",
        choices=[
            ("single", "Один правильный ответ"),
            ("multiple", "Несколько правильных ответов"),
        ],
        validators=[DataRequired()],
    )
    points = IntegerField("Баллы за вопрос", validators=[DataRequired()])
    submit = SubmitField("Сохранить вопрос")


# =========================
#   ТЕМЫ ОФОРМЛЕНИЯ КУРСОВ
# =========================

class CourseThemeForm(FlaskForm):
    name = StringField("Название темы", validators=[DataRequired()])
    primary_color = StringField("Основной цвет (#hex)", validators=[Optional()])
    accent_color = StringField("Акцентный цвет (#hex)", validators=[Optional()])
    background_color = StringField("Цвет фона (#hex)", validators=[Optional()])
    card_style = StringField("Стиль карточек (glass/flat/outlined)", validators=[Optional()])
    font_family = StringField("Шрифт", validators=[Optional()])
    submit = SubmitField("Сохранить тему")


# =========================
#   БЛОКИ УРОКА
# =========================

class LessonBlockForm(FlaskForm):
    block_type = SelectField(
        "Тип блока",
        choices=[
            ("text", "Текст"),
            ("video", "Видео"),
            ("image", "Картинка"),
            ("file", "Документ/файл"),
            ("quote", "Цитата"),
        ],
        validators=[DataRequired()],
    )
    title = StringField("Заголовок блока", validators=[Optional()])
    text_content = TextAreaField("Текст", validators=[Optional()])
    video_url = StringField("Ссылка на видео (YouTube и т.п.)", validators=[Optional()])
    order_index = IntegerField("Порядок", validators=[Optional()])
    submit = SubmitField("Сохранить блок")
