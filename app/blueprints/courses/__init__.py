from flask import Blueprint

courses_bp = Blueprint("courses", __name__, template_folder="../../templates")

from . import routes  # noqa
    