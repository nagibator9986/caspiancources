# CLAUDE.md — caspiancources (Caspian College Lerna LMS)

> Брифинг для Claude Code на следующий заход в этот проект.
> Цель документа — за 60 секунд погрузить в архитектуру, ловушки и правила работы.

---

## 1. Что это за проект

Учебная LMS-платформа на Flask. Пользователь записывается на курс → проходит уроки (модули с блоками: текст/видео/картинка/файл/цитата) → сдаёт модульные и финальный тесты → получает сертификат (HTML + PDF с кириллицей и брендингом).

- **Стэк:** Python 3.10+ / Flask 3 / Flask-SQLAlchemy / Flask-Login / Flask-WTF / SQLite / Jinja2 / Tailwind (CDN) / ReportLab для PDF.
- **Точка входа:** [run.py](run.py) → `create_app()` в [app/__init__.py](app/__init__.py).
- **Конфиг:** [config.py](config.py) — `SECRET_KEY` из env, иначе генерируется и кладётся в `.flask_secret` (gitignored). `UPLOAD_FOLDER = app/static/uploads`.
- **Запуск:** `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python run.py`. По умолчанию `http://127.0.0.1:5000`, debug-режим через `FLASK_DEBUG=1`.

---

## 2. Карта кодовой базы

```
app/
├── __init__.py              # фабрика приложения, регистрация blueprints, /uploads/<f>
├── extensions.py            # db, login_manager, csrf
├── models.py                # 12 моделей (см. §3)
├── forms.py                 # WTForms (Register/Login/Course/Module/Lesson/Test/Question/Theme/LessonBlock)
├── blueprints/
│   ├── auth/routes.py       # /register, /login, /logout
│   ├── main/routes.py       # /, /courses
│   ├── courses/routes.py    # курсы, уроки, тесты, личный кабинет, сертификаты, PDF
│   └── admin/routes.py      # /admin/* — CRUD + certificate-branding
├── templates/               # ~30 Jinja2-шаблонов под Tailwind
└── static/
    ├── css/styles.css       # пустой; стили в Tailwind-классах
    ├── js/main.js           # пустой
    ├── fonts/DejaVuSans*.ttf # шрифты с кириллицей для PDF
    └── uploads/             # пользовательский контент (gitignored)
```

Blueprint `admin` смонтирован под `/admin` и закрыт `@admin_bp.before_request → admin_required()` — проверка идёт **до** каждого хендлера, не нужно вешать декоратор индивидуально.

---

## 3. Доменная модель (ключевые отношения)

```
User ──┬─ UserCourse ─── Course ───┬─ CourseModule ─── Lesson ─── LessonBlock
       ├─ UserLessonProgress ──────┘                     │            (text/video/image/file/quote)
       ├─ UserTestAttempt ─── Test ◄─── Question ─── AnswerOption
       └─ Certificate ──── Course
                                  CourseTheme  (цвета/шрифт оформления)
                                  CertificateBranding  (singleton: компания, директор, логотип, печать)
```

- `Test.type ∈ {'module', 'final'}` — финальный связан с `course_id`, модульный — с `module_id`.
- `Question.type ∈ {'single', 'multiple'}`. Открытые ответы (`textarea`) **не оцениваются автоматически** — это сознательное решение.
- `CertificateBranding.get_singleton()` — паттерн «единственная запись», вызывайте через классметод, не создавайте новые.
- Каскады удаления настроены через `cascade="all, delete-orphan"` — удаление курса корректно сносит модули/уроки/тесты.

---

## 4. Бизнес-логика, которую легко сломать

### 4.1 Имена полей формы теста ↔ парсер

Шаблоны [take_test.html](app/templates/take_test.html) и [test_take.html](app/templates/test_take.html) рендерят инпуты как `name="q_{{ q.id }}"` (с подчёркиванием). Бэкенд в [courses/routes.py:344](app/blueprints/courses/routes.py) читает их через `request.form.getlist(f"q_{q.id}")`. **Менять имя — только в обоих местах одновременно**, иначе все попытки получат 0% (был такой баг, починен).

### 4.2 Подсчёт `multiple`

`single` — берём первый id из POST, сравниваем с правильным. `multiple` — собираем `set` из POST и сравниваем **на полное равенство** с `set(correct_ids)`. Частичное совпадение засчитывается как 0 баллов (можно поменять политику, если бизнес попросит — это явное место).

### 4.3 Финальный тест и сертификат

В [take_test()](app/blueprints/courses/routes.py) сертификат выдаётся **только если**:
1. `test.type == "final"`
2. `is_passed == True` (то есть `score_percent >= test.pass_score_percent`)
3. Все уроки курса уже пройдены (проверяется до показа теста)

Функция `maybe_create_certificate()` идемпотентна — повторное прохождение не создаёт дубль. Формат кода: `CCL-<course_id:03>-<user_id:04>-<6hex>`.

### 4.4 Загрузка файлов

`UPLOAD_FOLDER = app/static/uploads`. Файлы блоков урока хранятся как `course_<cid>/lessons/<lid>/{video|images|files}/<unique_name>`. Имя файла рандомизируется через `uuid.uuid4().hex[:10]` — НЕ убирать, иначе коллизии перетрут чужие файлы.

Раздача: маршрут `/uploads/<path:filename>` (см. [app/__init__.py](app/__init__.py)) — единая точка отдачи. В шаблонах используйте `url_for('uploaded_file', filename=block.image_path)`. **Не используйте** `block.image_url` / `block.file_url` — таких атрибутов в модели нет (был баг в шаблонах).

### 4.5 CSRF

`Flask-WTF CSRFProtect` включён глобально. Все самописные `<form method="post">` ОБЯЗАНЫ иметь `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. Формы через WTForms (`{{ form.hidden_tag() }}`) делают это автоматически.

`@csrf.exempt` мы НЕ используем — раньше стояло на `enroll_course` и `complete_lesson`, это было дырой. Включено обратно.

---

## 5. PDF-сертификат: что нужно знать

[`certificate_pdf`](app/blueprints/courses/routes.py) генерирует PDF на ReportLab в landscape A4. Ключевые моменты:

- **Кириллица** работает только потому что регистрируются TTF-шрифты `app/static/fonts/DejaVuSans.ttf` и `DejaVuSans-Bold.ttf`. Если их нет — fallback на Helvetica, и кириллица побьётся. Файлы лежат в репо, **не удалять**.
- Регистрация фонтов идёт **один раз** через модульный кэш `_PDF_FONTS_REGISTERED` (не перерегистрировать при каждом запросе).
- **Брендинг**: все тексты (компания, директор, печать-картинка) подтягиваются из `CertificateBranding.get_singleton()`. Изменения брендинга в админке мгновенно отражаются в новых PDF.
- **Вертикальная сетка** строго рассчитана, чтобы блоки не наезжали друг на друга (см. комментарий в коде «Вертикальная сетка»). Перед изменением координат **обязательно** регенерировать PDF и визуально проверить, что:
  1. Большой «СЕРТИФИКАТ» НЕ перекрывает шапку.
  2. Описание не уезжает в info-блоки.
  3. Печать не залезает за нижнюю рамку (допустим лёгкий выход в margin — выглядит как настоящая печать).
- Декоративная «печать» (`_draw_default_seal`) рисуется только если изображение печати не загружено или битое.

---

## 6. Шаблоны и UI

- Tailwind подключён через CDN — для прод-проекта стоит собрать локально (purge). Для дипломного MVP — приемлемо.
- HTML-сертификат [certificate_view.html](app/templates/certificate_view.html) использует шрифт Cormorant Garamond (Google Fonts) для имени — серифный почерк, имитирующий каллиграфию. CSS-уголки и декор делаются псевдоэлементами `::before/::after`. Печать и подпись имеют hover-анимации (`transform`).
- В шаблонах **не дёргайте** несуществующих эндпоинтов через `url_for(...)` — Jinja упадёт на 500. Каталог курсов = `main.courses_list` (а не `courses.courses`).
- Видео в уроках поддерживает 2 режима: загруженный файл (`block.video_source == 'upload'` → `<video>`) и внешняя ссылка (`block.video_url` → `<iframe>` с автопреобразованием YouTube `watch?v=` и `youtu.be/` в `embed/`-форму). См. макрос `youtube_embed` в [lesson_view.html](app/templates/lesson_view.html).

---

## 7. Сиды и тестовые данные

- [seed_html_css_course.py](seed_html_css_course.py) — несмотря на имя, **сеит курс по ИИ** (3 модуля, 10 уроков, ~87 вопросов, ~348 вариантов, финальный тест на 27 вопросов). Запуск: `python seed_html_css_course.py` (внутри `create_app()` контекст). Идемпотентен по `slug='ai-tools-career'`.
- В склонированной БД есть админ `admin@example.com` и тестовые студенты. Пароли восстанавливать через скрипт типа:
  ```python
  from app import create_app; from app.models import User; from app.extensions import db
  app = create_app()
  with app.app_context():
      u = User.query.filter_by(email="admin@example.com").first()
      u.set_password("admin123"); db.session.commit()
  ```

---

## 8. Безопасность — checklist перед deploy

- `FLASK_SECRET_KEY` — обязательно из env, не дефолтный.
- `FLASK_DEBUG=0` в продакшне (werkzeug debugger = RCE).
- `FLASK_COOKIE_SECURE=1` под HTTPS.
- Не коммитить `app.db` (есть в `.gitignore`).
- При смене SQLite на PostgreSQL — добавить миграции (сейчас `db.create_all()` достаточно для разработки, для прод-БД переезд должен идти через Alembic / Flask-Migrate).

---

## 9. Правила работы в этом репозитории

1. **Сначала прочитать модели и роуты, потом править шаблоны.** В этой кодобазе шаблоны несколько раз ссылались на атрибуты, которых нет в модели (`block.image_url`, `cert.created_at`). Это компилируется, но валит страницу на 500. Сразу пробивайте имена через `grep`.

2. **После любой правки PDF — визуально проверить.** Reportlab не предупреждает о наложениях. Делайте `curl /certificate/<id>/pdf -o /tmp/cert.pdf && open /tmp/cert.pdf` и смотрите глазами.

3. **CSRF и `csrf_token()` в каждой кастомной форме.** Не временный fix через `@csrf.exempt` — это закрытая дыра, не открывайте обратно.

4. **Не плодите дубли импортов.** Старая версия `courses/routes.py` импортировала `Certificate` трижды, `make_response`/`redirect`/`url_for` дважды. Это уже почистили — следите, чтобы не возвращалось.

5. **Не вычисляйте суммы list-атрибутов через `|sum(attribute='lessons')`.** Это не работает в Jinja (получите `int + list`). Используйте `namespace` + явный цикл (пример — `course_detail.html:138-143`).

6. **Порядок (`order_index`) считайте от текущего максимума через `func.coalesce(func.max(...), 0) + 1`.** Иначе все новые сущности схлопнутся в 0 и порядок сломается.

7. **Файлы загрузок храните с уникальными именами (`uuid.uuid4().hex[:10]`).** Если решите вернуть «человеческое» имя — оригинал можно положить в отдельную колонку, но физический файл должен быть уникальным.

8. **Перед `git commit` всегда проверять, что `app.db` и `__pycache__` не утекают в индекс** (см. `.gitignore`). История репозитория когда-то хранила БД с хэшами паролей — больше так не делаем.

9. **«Чинить причину, не симптом».** Если запрос валится — не оборачивайте в `try/except: pass`, найдите, почему. Подавление ошибок в PDF-генерации допустимо ТОЛЬКО для отрисовки опциональных декораций (логотип, печать), и должно быть с дефолтным fallback.

10. **Не добавляйте новые зависимости без острой нужды.** Текущий `requirements.txt` минимален и хорошо подобран. Если хотите PDF из HTML — не вытаскивайте `pdfkit`/`weasyprint` (оба требуют тяжёлые системные либы). ReportLab у нас уже работает.

---

## 10. Что осталось «на потом» (не баг, но улучшение)

- Перевести Tailwind на локальную сборку (purge → ~30 КБ вместо 3 МБ через CDN).
- Прикрутить Flask-Migrate (миграции схемы).
- Добавить QR-код на PDF-сертификат со ссылкой на верификацию (`/certificates/<id>` публичный read-only).
- Тесты с `pytest` — сейчас их нет совсем. Минимум: smoke-тесты для `take_test` и `certificate_pdf`.
- Лог попыток теста в UI (сейчас в БД хранится, но в кабинете не показывается).
- Открытый ответ (`textarea` в вопросе) — оценивается вручную преподавателем; нужен админ-UI для ручной проверки.

---

## 11. Команды-шпаргалки

```bash
# Запуск
source .venv/bin/activate && FLASK_DEBUG=1 python run.py

# Сид (один раз)
python seed_html_css_course.py

# Сброс админского пароля
python -c "from app import create_app; from app.models import User; from app.extensions import db; \
  app=create_app(); ctx=app.app_context(); ctx.push(); \
  u=User.query.filter_by(email='admin@example.com').first(); u.set_password('admin123'); db.session.commit(); print('done')"

# Сгенерировать PDF и открыть
curl -sL --cookie-jar /tmp/c -d "email=admin@example.com&password=admin123&csrf_token=$(curl -s --cookie /tmp/c http://127.0.0.1:5000/login | grep -oE 'csrf_token[^"]*"[^"]+' | grep -oE '[^"]+$')" http://127.0.0.1:5000/login > /dev/null
curl -sL --cookie /tmp/c -o /tmp/cert.pdf http://127.0.0.1:5000/certificate/1/pdf && open /tmp/cert.pdf

# Граф маршрутов
python -c "from app import create_app; [print(r.rule, '->', r.endpoint) for r in create_app().url_map.iter_rules()]"
```
