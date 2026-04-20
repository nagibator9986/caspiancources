from flask import render_template
from flask_login import current_user
from ...models import Course
from . import main_bp

@main_bp.route("/")
def index():
    courses = Course.query.filter_by(is_published=True).all()
    return render_template("index.html", courses=courses)

@main_bp.route("/courses")
def courses_list():
    courses = Course.query.filter_by(is_published=True).all()
    return render_template("courses.html", courses=courses)
