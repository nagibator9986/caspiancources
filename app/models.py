from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db

# -----------------------------
# Пользователь
# -----------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="student")  # 'student' или 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    courses = db.relationship("UserCourse", back_populates="user", cascade="all, delete-orphan")
    lesson_progress = db.relationship("UserLessonProgress", back_populates="user", cascade="all, delete-orphan")
    test_attempts = db.relationship("UserTestAttempt", back_populates="user", cascade="all, delete-orphan")
    certificates = db.relationship("Certificate", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        return self.role == "admin"

# -----------------------------
# Темы оформления курсов
# -----------------------------
class CourseTheme(db.Model):
    __tablename__ = "course_themes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # "Светлый минимализм"
    primary_color = db.Column(db.String(20), default="#6366F1")
    accent_color = db.Column(db.String(20), default="#22C55E")
    background_color = db.Column(db.String(20), default="#F8FAFF")
    card_style = db.Column(db.String(50), default="flat")  # "glass", "flat", "outlined"
    font_family = db.Column(db.String(100), default="Inter")
    extra_config = db.Column(db.Text, nullable=True)

    courses = db.relationship("Course", back_populates="theme")

# -----------------------------
# Курсы / Модули / Уроки
# -----------------------------
class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    level = db.Column(db.String(50), nullable=True)

    image_url = db.Column(db.String(255), nullable=True)      # обложка
    hero_image_url = db.Column(db.String(255), nullable=True) # фон в шапке
    logo_url = db.Column(db.String(255), nullable=True)       # логотип курса

    theme_id = db.Column(db.Integer, db.ForeignKey("course_themes.id"), nullable=True)
    theme = db.relationship("CourseTheme", back_populates="courses")

    language = db.Column(db.String(20), default="ru")
    estimated_duration_minutes = db.Column(db.Integer, default=0)
    requirements = db.Column(db.Text, nullable=True)
    outcomes = db.Column(db.Text, nullable=True)

    is_sequential = db.Column(db.Boolean, default=True)  # модули по порядку
    is_published = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    modules = db.relationship("CourseModule", back_populates="course", cascade="all, delete-orphan")
    tests = db.relationship("Test", back_populates="course", cascade="all, delete-orphan")  # финальные тесты
    user_courses = db.relationship("UserCourse", back_populates="course", cascade="all, delete-orphan")
    certificates = db.relationship("Certificate", back_populates="course", cascade="all, delete-orphan")

class CourseModule(db.Model):
    __tablename__ = "course_modules"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order_index = db.Column(db.Integer, default=0)

    course = db.relationship("Course", back_populates="modules")
    lessons = db.relationship("Lesson", back_populates="module", cascade="all, delete-orphan")
    tests = db.relationship("Test", back_populates="module", cascade="all, delete-orphan")  # тесты по модулю

class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("course_modules.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    order_index = db.Column(db.Integer, default=0)
    is_preview = db.Column(db.Boolean, default=False)

    module = db.relationship("CourseModule", back_populates="lessons")
    blocks = db.relationship("LessonBlock", back_populates="lesson", cascade="all, delete-orphan")
    progress = db.relationship("UserLessonProgress", back_populates="lesson", cascade="all, delete-orphan")

# Блоки урока: текст, видео, картинка, файл, цитата и т.п.
class LessonBlock(db.Model):
    __tablename__ = "lesson_blocks"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    lesson = db.relationship("Lesson", back_populates="blocks")

    block_type = db.Column(db.String(20), nullable=False)  # text, video, image, file, quote
    order_index = db.Column(db.Integer, default=0)

    title = db.Column(db.String(255), nullable=True)
    text_content = db.Column(db.Text, nullable=True)  # для text/quote

    # Видео
    video_source = db.Column(db.String(20), nullable=True)  # upload/youtube
    video_url = db.Column(db.String(255), nullable=True)
    video_file_path = db.Column(db.String(255), nullable=True)

    # Изображения
    image_path = db.Column(db.String(255), nullable=True)
    alt_text = db.Column(db.String(255), nullable=True)

    # Документы/файлы
    file_path = db.Column(db.String(255), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)

# -----------------------------
# Тесты и вопросы
# -----------------------------
class Test(db.Model):
    __tablename__ = "tests"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)   # финальный
    module_id = db.Column(db.Integer, db.ForeignKey("course_modules.id"), nullable=True)  # по модулю
    type = db.Column(db.String(20), nullable=False)  # 'module' или 'final'
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    pass_score_percent = db.Column(db.Integer, default=70)
    max_attempts = db.Column(db.Integer, nullable=True)  # None = бесконечно

    course = db.relationship("Course", back_populates="tests")
    module = db.relationship("CourseModule", back_populates="tests")
    questions = db.relationship("Question", back_populates="test", cascade="all, delete-orphan")
    attempts = db.relationship("UserTestAttempt", back_populates="test", cascade="all, delete-orphan")

class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey("tests.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default="single")  # single, multiple
    order_index = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=1)

    image_path = db.Column(db.String(255), nullable=True)
    explanation = db.Column(db.Text, nullable=True)

    test = db.relationship("Test", back_populates="questions")
    answer_options = db.relationship("AnswerOption", back_populates="question", cascade="all, delete-orphan")

class AnswerOption(db.Model):
    __tablename__ = "answer_options"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    question = db.relationship("Question", back_populates="answer_options")

# -----------------------------
# Прогресс и попытки
# -----------------------------
class UserCourse(db.Model):
    __tablename__ = "user_courses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    status = db.Column(db.String(20), default="enrolled")  # enrolled, in_progress, completed
    progress_percent = db.Column(db.Integer, default=0)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="courses")
    course = db.relationship("Course", back_populates="user_courses")

class UserLessonProgress(db.Model):
    __tablename__ = "user_lesson_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="lesson_progress")
    lesson = db.relationship("Lesson", back_populates="progress")

class UserTestAttempt(db.Model):
    __tablename__ = "user_test_attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("tests.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    score_percent = db.Column(db.Integer, nullable=True)
    is_passed = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="test_attempts")
    test = db.relationship("Test", back_populates="attempts")

# -----------------------------
# Сертификаты
# -----------------------------
class Certificate(db.Model):
    __tablename__ = "certificates"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    certificate_code = db.Column(db.String(100), unique=True, nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="certificates")
    course = db.relationship("Course", back_populates="certificates")
# -----------------------------
# Брендинг сертификатов (настройки)
# -----------------------------
class CertificateBranding(db.Model):
    __tablename__ = "certificate_branding"

    id = db.Column(db.Integer, primary_key=True)

    # === Основная компания (юридическое лицо, выдающее сертификат) ===
    company_name = db.Column(db.String(255), nullable=False, default='ИП "Illuminart"')
    company_subtitle = db.Column(
        db.String(255),
        nullable=True,
        default="Образовательная платформа Lerna",
    )

    # === Партнёр (учебное заведение, на базе которого шло обучение) ===
    partner_name = db.Column(
        db.String(255),
        nullable=True,
        default="Caspian College",
    )
    partner_subtitle = db.Column(
        db.String(255),
        nullable=True,
        default="Учебный партнёр",
    )

    # === Подпись ===
    director_title = db.Column(
        db.String(255),
        nullable=True,
        default="Руководитель",
    )
    director_name = db.Column(
        db.String(255),
        nullable=True,
    )

    # === Изображения ===
    logo_image_path = db.Column(db.String(255), nullable=True)         # основной (Illuminart)
    partner_logo_image_path = db.Column(db.String(255), nullable=True) # партнёр (College)
    seal_image_path = db.Column(db.String(255), nullable=True)         # печать (Illuminart)

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    @classmethod
    def get_singleton(cls):
        """
        Возвращает единственную запись с настройками.
        Если её нет — создаёт с дефолтными значениями.
        """
        inst = cls.query.first()
        if not inst:
            inst = cls()
            db.session.add(inst)
            db.session.commit()
        return inst
