"""Локальный API для регистрации проектов на локализацию игр."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
DB_PATH = Path(os.getenv("DATABASE_PATH", "data/leads.sqlite3"))
REQUIRED_FIELDS = ("name", "contact", "source", "comment")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db() -> None:
    """Create the MVP tables. Safe to run more than once."""
    with connect_db() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                source TEXT NOT NULL,
                comment TEXT NOT NULL,
                direction TEXT NOT NULL DEFAULT 'incoming',
                company TEXT,
                game_title TEXT,
                project_url TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('genre','platform','language')),
                name TEXT NOT NULL COLLATE NOCASE,
                UNIQUE(kind,name)
            );
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(leads)")}
        if "game_id" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN game_id TEXT")
        if "status" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")
        if "materials_url" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN materials_url TEXT")
        for column in ("genres", "platforms", "languages"):
            if column not in columns:
                connection.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'")
        defaults = {
            "genre": ["Экшен", "Приключение", "RPG", "Стратегия", "Симулятор", "Головоломка", "Казуальная", "Хоррор", "Спорт", "Другое"],
            "platform": ["PC", "PlayStation", "Xbox", "Nintendo Switch", "iOS", "Android", "Web", "Другое"],
            "language": ["Английский", "Русский", "Китайский (упрощённый)", "Китайский (традиционный)", "Японский", "Корейский", "Немецкий", "Французский", "Испанский", "Португальский", "Другой"],
        }
        for kind, names in defaults.items():
            connection.executemany("INSERT OR IGNORE INTO categories(kind,name) VALUES (?,?)", [(kind, name) for name in names])


@app.cli.command("init-db")
def init_db_command() -> None:
    """Initialize the database with: flask --app app init-db"""
    initialize_db()
    print(f"SQLite database is ready: {DB_PATH}")


@app.get("/")
def index():
    filters = {
        "q": request.args.get("q", "").strip(),
        "direction": request.args.get("direction", ""),
        "status": request.args.get("status", ""),
        "genre": request.args.get("genre", ""),
        "platform": request.args.get("platform", ""),
        "language": request.args.get("language", ""),
    }
    with connect_db() as connection:
        all_leads = [dict(row) for row in connection.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()]
        categories = {
            kind: [row["name"] for row in connection.execute("SELECT name FROM categories WHERE kind=? ORDER BY name", (kind,))]
            for kind in ("genre", "platform", "language")
        }
    for lead in all_leads:
        for field in ("genres", "platforms", "languages"):
            try:
                lead[field + "_values"] = json.loads(lead[field])
            except (TypeError, json.JSONDecodeError):
                lead[field + "_values"] = []
            lead[field + "_display"] = ", ".join(lead[field + "_values"])
    leads = all_leads
    if filters["q"]:
        needle = filters["q"].casefold()
        leads = [x for x in leads if needle in " ".join(str(x.get(k) or "") for k in ("game_title", "company", "name", "contact", "source", "comment")).casefold()]
    if filters["direction"] in ("incoming", "outgoing"):
        leads = [x for x in leads if x["direction"] == filters["direction"]]
    if filters["status"]:
        leads = [x for x in leads if x["status"] == filters["status"]]
    for key, field in (("genre", "genres_values"), ("platform", "platforms_values"), ("language", "languages_values")):
        if filters[key]:
            leads = [x for x in leads if filters[key] in x[field]]
    return render_template_string("""
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Игровые проекты</title>
<style>
:root{color-scheme:light;--page:#f3f5f2;--surface:#fff;--text:#202923;--muted:#718078;--border:#e2e8e3;--field-border:#ccd7cf;--soft:#eaf3ee;--soft-text:#276049;--shadow:#20352b0b}
:root[data-theme="dark"]{color-scheme:dark;--page:#151b18;--surface:#202923;--text:#e8eee9;--muted:#a2b1a7;--border:#35443b;--field-border:#52645a;--soft:#2b4035;--soft-text:#b5dec8;--shadow:#0005}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--text);font:15px Segoe UI,Arial,sans-serif;transition:background .2s,color .2s}header{background:#183d32;color:white;padding:28px max(22px,calc((100% - 1040px)/2))}header p{color:#c5d9ce;margin-bottom:0}.wrap{max-width:1040px;margin:28px auto;padding:0 20px}.grid{display:grid;grid-template-columns:340px 1fr;gap:22px;align-items:start}.panel{min-width:0;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:22px;box-shadow:0 4px 18px var(--shadow)}h1{margin:0;font-size:25px}h2{font-size:18px;margin:0 0 16px}label{display:block;font-size:13px;font-weight:600;margin:13px 0 5px}input,select,textarea{width:100%;min-width:0;padding:10px;border:1px solid var(--field-border);border-radius:8px;font:inherit;background:var(--surface);color:var(--text)}textarea{min-height:76px}button{min-height:44px;margin-top:16px;border:0;border-radius:8px;background:#23634e;color:white;padding:11px 16px;font:inherit;font-weight:600;cursor:pointer}.hint,.meta{font-size:12px;color:var(--muted);line-height:1.5}.lead{overflow-wrap:anywhere;border-top:1px solid var(--border);padding:15px 0}.tag{display:inline-block;padding:4px 8px;border-radius:99px;background:var(--soft);color:var(--soft-text);font-size:12px}.game-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:20px}.game-item{min-width:0;border:1px solid var(--border);border-radius:10px;padding:12px;margin-top:10px}.game-item textarea{min-height:55px}.secondary{margin:0;background:var(--soft);color:var(--soft-text);padding:8px 10px}.category-list{display:flex;flex-wrap:wrap;gap:6px;padding:7px;border:1px solid var(--border);border-radius:8px}.choice{display:inline-flex;align-items:center;gap:5px;margin:0;padding:5px 8px;border-radius:7px;background:var(--soft);font-size:13px}.choice input{width:auto;margin:0}.library{grid-column:1/-1}.library-row{display:flex;gap:8px}.library-row select{max-width:140px}.library-row button{margin:0}.library-chips{display:flex;flex-wrap:wrap;gap:6px}.chip{background:var(--soft);color:var(--soft-text);padding:5px 9px;border-radius:99px;font-size:12px}.library h3{margin:14px 0 7px}.success{color:#23634e}.error{color:#a13a32}.header-row{display:flex;justify-content:space-between;align-items:center;gap:16px}.theme-toggle{margin:0;background:#ffffff20;color:white;border:1px solid #ffffff55;min-height:40px;white-space:nowrap}
@media(max-width:760px){header{padding:22px 18px}.wrap{margin:16px auto;padding:0 14px}.grid{grid-template-columns:minmax(0,1fr);gap:14px}.panel{padding:17px;border-radius:12px}h1{font-size:22px}h2{font-size:17px}.game-head{align-items:flex-start;flex-wrap:wrap}.game-head .secondary{max-width:100%}.lead{padding:13px 0}}
@media(max-width:420px){.panel{padding:14px}.wrap{padding:0 10px}.header-row{align-items:flex-start;flex-direction:column}.game-head{display:block}.game-head button{margin-top:10px;width:100%}button[type=submit]{width:100%}}
.filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;align-items:center;margin-bottom:14px}.filters input{grid-column:1/-1}.filters button{margin:0;white-space:nowrap}.multi-select{position:relative}.multi-select summary{cursor:pointer;list-style:none;padding:10px;border:1px solid var(--field-border);border-radius:8px;background:var(--surface);color:var(--text)}.multi-select summary::-webkit-details-marker{display:none}.multi-select summary:after{content:"▾";float:right;color:var(--muted)}.multi-select[open] summary{border-color:#4b8a70;border-radius:8px 8px 0 0}.option-list{display:grid;grid-template-columns:1fr;gap:3px;max-height:180px;overflow:auto;padding:8px;border:1px solid var(--field-border);border-top:0;border-radius:0 0 8px 8px;background:var(--surface)}.option-list .choice{cursor:pointer}.option-list input{accent-color:#23634e}.clear-filter{font-size:13px;color:var(--soft-text)}@media(max-width:760px){.filters{grid-template-columns:1fr 1fr}.filters input{grid-column:1/-1}.filters button{width:100%}}@media(max-width:420px){.filters{grid-template-columns:1fr}.filters input{grid-column:auto}}
</style><script>try{document.documentElement.dataset.theme=localStorage.getItem('vpk01-theme')||'light'}catch(e){}</script></head><body><header><div class="header-row" style="max-width:1040px;margin:auto"><div><h1>Игровые проекты для локализации</h1><p>Входящие предложения и кандидаты, найденные командой</p></div><button type="button" class="theme-toggle" id="theme-toggle">🌙 Тёмная тема</button></div></header><main class="wrap"><div class="grid"><section class="panel"><h2>Добавить кандидата</h2>
<form id="f"><label>Направление</label><select name="direction"><option value="incoming">Входящее предложение</option><option value="outgoing">Наш кандидат / исходящий контакт</option></select><label>Имя контактного лица *</label><input name="name" required><label>Контакт *</label><input name="contact" required><label>Источник *</label><input name="source" required placeholder="Письмо, сайт, рекомендация"><label>Комментарий к контакту *</label><textarea name="comment" required></textarea><label>Компания / правообладатель</label><input name="company"><div class="game-head"><strong>Игры-кандидаты</strong><button type="button" id="add-game" class="secondary">＋ Добавить игру</button></div><div id="games"></div><button>Сохранить игровые карточки</button><p id="msg"></p><p class="hint">Каждая игра будет сохранена отдельной карточкой. Общие контакт и компания свяжутся со всеми добавленными играми.</p></form></section>
<section class="panel"><h2>Карточки игр</h2><form method="get" class="filters"><input name="q" value="{{ filters.q }}" placeholder="Поиск: игра, компания, контакт"><select name="direction"><option value="">Все направления</option><option value="incoming" {% if filters.direction=='incoming' %}selected{% endif %}>Входящие</option><option value="outgoing" {% if filters.direction=='outgoing' %}selected{% endif %}>Исходящие</option></select><select name="status"><option value="">Все статусы</option><option value="new" {% if filters.status=='new' %}selected{% endif %}>Новая</option></select><select name="genre"><option value="">Все жанры</option>{% for value in categories['genre'] %}<option value="{{ value }}" {% if filters.genre==value %}selected{% endif %}>{{ value }}</option>{% endfor %}</select><select name="platform"><option value="">Все платформы</option>{% for value in categories['platform'] %}<option value="{{ value }}" {% if filters.platform==value %}selected{% endif %}>{{ value }}</option>{% endfor %}</select><select name="language"><option value="">Все языки</option>{% for value in categories['language'] %}<option value="{{ value }}" {% if filters.language==value %}selected{% endif %}>{{ value }}</option>{% endfor %}</select><button type="submit">Найти</button><a class="clear-filter" href="/">Сбросить</a></form><p class="hint">Показано карточек: {{ leads|length }} из {{ all_count }}</p>{% if leads %}{% for x in leads %}<article class="lead"><span class="tag">{{ 'Входящий' if x['direction']=='incoming' else 'Исходящий' }}</span> <span class="tag">{{ x['status'] }}</span> <strong>{{ x['game_title'] or 'Игра не указана' }}</strong><div>{{ x['company'] or x['name'] }}</div><div class="meta">Карточка игры #{{ x['id'] }} · {{ x['created_at'] }} · {{ x['source'] }}</div><p>{{ x['comment'] }}</p><div class="meta">Жанры: {{ x['genres_display'] }} · Платформы: {{ x['platforms_display'] }} · Языки: {{ x['languages_display'] }}</div>{% if x['project_url'] %}<p><a href="{{ x['project_url'] }}" target="_blank" rel="noreferrer">Страница игры</a></p>{% endif %}{% if x['materials_url'] %}<p><a href="{{ x['materials_url'] }}" target="_blank" rel="noreferrer">Скриншоты, видео и другие материалы</a></p>{% endif %}</article>{% endfor %}{% else %}<p class="hint">Пока заявок нет. Добавь тестового кандидата через форму.</p>{% endif %}</section><section class="panel library"><h2>Библиотека категорий</h2><p class="hint">Добавляй значения сюда — они появятся в выборе для новых игровых карточек.</p><div class="library-row"><select id="category-kind"><option value="genre">Жанр</option><option value="platform">Платформа</option><option value="language">Язык</option></select><input id="category-name" placeholder="Новое значение"><button type="button" id="category-add">Добавить</button></div><p id="library-msg" class="hint"></p><div id="library-items">{% for kind, names in categories.items() %}<h3>{{ {'genre':'Жанры','platform':'Платформы','language':'Языки'}[kind] }}</h3><div class="library-chips">{% for name in names %}<span class="chip">{{ name }}</span>{% endfor %}</div>{% endfor %}</div></section></div></main>
<script>
const games=document.getElementById('games');
function selectedValues(element){return [...element.querySelectorAll('input:checked')].map(input=>input.value)}
function addGame(){const box=document.createElement('div');box.className='game-item';box.innerHTML='<button type="button" class="secondary remove" style="float:right">Убрать</button><label>Название игры *</label><input class="title" required><label>Ссылка на страницу игры</label><input class="url" type="url" placeholder="https://…"><label>Ссылка на материалы (скриншоты, видео)</label><input class="materials" type="url" placeholder="https://…"><label>Жанры *</label><details class="multi-select genres"><summary>Выбрать жанры</summary><div class="option-list">{% for value in categories['genre'] %}<label class="choice"><input type="checkbox" value="{{ value }}">{{ value }}</label>{% endfor %}</div></details><label>Платформы *</label><details class="multi-select platforms"><summary>Выбрать платформы</summary><div class="option-list">{% for value in categories['platform'] %}<label class="choice"><input type="checkbox" value="{{ value }}">{{ value }}</label>{% endfor %}</div></details><label>Языки игры *</label><details class="multi-select languages"><summary>Выбрать языки</summary><div class="option-list">{% for value in categories['language'] %}<label class="choice"><input type="checkbox" value="{{ value }}">{{ value }}</label>{% endfor %}</div></details><label>Дополнительные заметки</label><textarea class="notes"></textarea>';box.querySelector('.remove').onclick=()=>{if(games.children.length>1)box.remove()};games.appendChild(box)}
addGame();document.getElementById('add-game').onclick=addGame;
document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.currentTarget));d.games=[...games.children].map(x=>({title:x.querySelector('.title').value,url:x.querySelector('.url').value,materials_url:x.querySelector('.materials').value,notes:x.querySelector('.notes').value,genres:selectedValues(x.querySelector('.genres')),platforms:selectedValues(x.querySelector('.platforms')),languages:selectedValues(x.querySelector('.languages'))}));let m=document.getElementById('msg');try{let r=await fetch('/lead',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}),j=await r.json();if(!r.ok)throw Error(j.error);m.className='success';m.textContent='Создано карточек игр: '+j.games.length+' — обновляю список';setTimeout(()=>location.reload(),600)}catch(x){m.className='error';m.textContent=x.message}});
</script><script>const themeButton=document.getElementById('theme-toggle');function syncThemeButton(){const dark=document.documentElement.dataset.theme==='dark';themeButton.textContent=dark?'☀️ Светлая тема':'🌙 Тёмная тема'}syncThemeButton();themeButton.addEventListener('click',()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('vpk01-theme',next)}catch(e){}syncThemeButton()});</script><script>
document.getElementById('category-add').onclick=async()=>{const kind=document.getElementById('category-kind').value,name=document.getElementById('category-name').value.trim(),msg=document.getElementById('library-msg');if(!name){msg.textContent='Введи название категории.';return}try{const r=await fetch('/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,name})}),j=await r.json();if(!r.ok)throw Error(j.error);location.reload()}catch(e){msg.textContent=e.message}};
</script></body></html>
    """, leads=leads, all_count=len(all_leads), categories=categories, filters=filters)


@app.post("/categories")
def add_category():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("kind") not in ("genre", "platform", "language"):
        return jsonify(error="Выбери тип: жанр, платформа или язык"), 400
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        return jsonify(error="Название категории должно содержать от 1 до 60 символов"), 400
    try:
        with connect_db() as connection:
            connection.execute("INSERT INTO categories(kind,name) VALUES (?,?)", (payload["kind"], name.strip()))
    except sqlite3.IntegrityError:
        return jsonify(error="Такая категория уже есть в библиотеке"), 409
    except sqlite3.Error:
        logger.exception("Could not add a category")
        return jsonify(error="Не удалось сохранить категорию"), 500
    return jsonify(status="created", kind=payload["kind"], name=name.strip()), 201


@app.post("/lead")
def create_lead():
    if not request.is_json:
        return jsonify(error="Content-Type должен быть application/json"), 400
    payload: Any = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Ожидается JSON-объект с данными предложения"), 400
    missing = [f for f in REQUIRED_FIELDS if not isinstance(payload.get(f), str) or not payload[f].strip()]
    if missing:
        return jsonify(error="Обязательные поля должны быть непустыми строками", fields=missing), 400
    direction = payload.get("direction", "incoming")
    if not isinstance(direction, str) or direction not in ("incoming", "outgoing"):
        return jsonify(error="direction должен быть incoming или outgoing"), 400
    games = payload.get("games")
    if games is None and isinstance(payload.get("game_title"), str):
        games = [{"title": payload["game_title"], "url": payload.get("project_url", ""), "notes": ""}]
    if not isinstance(games, list) or not games:
        return jsonify(error="Добавьте хотя бы одну игру"), 400
    normalized = []
    for i, game in enumerate(games, 1):
        if not isinstance(game, dict) or not isinstance(game.get("title"), str) or not game["title"].strip():
            return jsonify(error=f"Укажите название игры №{i}"), 400
        item = {"title": game["title"].strip()}
        for field in ("url", "materials_url", "notes"):
            value = game.get(field, "")
            if not isinstance(value, str):
                return jsonify(error=f"Поле {field} игры №{i} должно быть строкой"), 400
            item[field] = value.strip()
        for field in ("genres", "platforms", "languages"):
            values = game.get(field)
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                return jsonify(error=f"Выберите хотя бы одно значение в поле {field} для игры №{i}"), 400
            clean_values = list(dict.fromkeys(v.strip() for v in values))
            kind = {"genres": "genre", "platforms": "platform", "languages": "language"}[field]
            with connect_db() as connection:
                known = {row["name"] for row in connection.execute("SELECT name FROM categories WHERE kind=?", (kind,))}
            if any(value not in known for value in clean_values):
                return jsonify(error=f"В поле {field} есть значение, отсутствующее в библиотеке"), 400
            item[field] = json.dumps(clean_values, ensure_ascii=False)
        normalized.append(item)
    company = payload.get("company", "")
    if not isinstance(company, str):
        return jsonify(error="Поле company должно быть строкой"), 400

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ids = []
    try:
        with connect_db() as connection:
            for game in normalized:
                cursor = connection.execute(
                    """INSERT INTO leads
                    (created_at,name,contact,source,comment,direction,company,game_title,project_url,status,materials_url,genres,platforms,languages)
                    VALUES (?,?,?,?,?,?,?,?,?, 'new', ?,?,?,?)""",
                    (created_at, *(payload[k].strip() for k in REQUIRED_FIELDS), direction,
                     company.strip() or None, game["title"], game["url"] or None, game["materials_url"] or None, game["genres"], game["platforms"], game["languages"]),
                )
                lead_id = cursor.lastrowid
                ids.append(lead_id)
                connection.execute("INSERT INTO events (created_at,message) VALUES (?,?)",
                    (created_at, f"New lead saved: {lead_id}"))
    except sqlite3.Error:
        logger.exception("Database error while saving game candidates")
        return jsonify(error="Не удалось сохранить кандидатов. Попробуйте позже."), 500
    return jsonify(status="accepted", games=[{"id": i} for i in ids], created_at=created_at), 201


if __name__ == "__main__":
    initialize_db()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
