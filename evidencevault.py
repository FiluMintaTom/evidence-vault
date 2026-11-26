"""
Evidence Vault - Digital Evidence Management System
Flask + SQLite web application with full CRUD on all six tables.

Setup (Windows):
    pip install flask
    python evidencevault.py
    open http://127.0.0.1:5000

The database file (evidencevault.db) is created in the same folder as this file.
"""
import os
import sqlite3

from flask import (Flask, abort, flash, g, redirect, render_template_string,
                   request, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "evidencevault.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "evidencevault_schema.sql")

app = Flask(__name__)
app.secret_key = "evidencevault-change-this-secret"


def fld(col, label, kind="text", req=False, options=None, ref=None, hint=None):
    """kind: text | textarea | date | datetime | select | fk"""
    return {"col": col, "label": label, "kind": kind, "req": req,
            "options": options, "ref": ref, "hint": hint}


ENTITIES = {
    "cases": {
        "label": "Case", "plural": "Cases", "table": "cases", "pk": "case_id",
        "blurb": "Investigations opened against cybercrime incidents.",
        "fields": [
            fld("case_name", "Case name", req=True),
            fld("case_type", "Case type", hint="e.g. Fraud, Phishing, Ransomware"),
            fld("description", "Description", "textarea"),
            fld("date_opened", "Date opened", "date", req=True),
            fld("date_closed", "Date closed", "date"),
            fld("status", "Status", "select", req=True, options=["Open", "Closed"]),
        ],
    },
    "investigations": {
        "label": "Investigation", "plural": "Investigations", "table": "investigations",
        "pk": "investigation_id",
        "blurb": "Investigators and analysts assigned to a case.",
        "fields": [
            fld("case_id", "Case", "fk", req=True, ref=("cases", "case_id", "case_name")),
            fld("name", "Investigator name", req=True),
            fld("email", "Email"),
            fld("phone", "Phone"),
            fld("role", "Role", "select", req=True,
                options=["Investigator", "Analyst", "Admin"]),
            fld("description", "Description", "textarea"),
            fld("start_date", "Start date", "date"),
            fld("end_date", "End date", "date"),
            fld("status", "Status", "select", req=True,
                options=["Active", "Inactive", "Completed"]),
        ],
    },
    "evidence_types": {
        "label": "Evidence type", "plural": "Evidence types", "table": "evidence_types",
        "pk": "evidence_type_id",
        "blurb": "Categories of digital evidence. Each type is unique.",
        "fields": [
            fld("type_name", "Type name", "select", req=True,
                options=["File", "Image", "Video", "Log", "Device"]),
            fld("description", "Description", "textarea"),
        ],
    },
    "evidence": {
        "label": "Evidence", "plural": "Evidence", "table": "evidence", "pk": "evidence_id",
        "blurb": "Digital items collected during an investigation.",
        "fields": [
            fld("case_id", "Case", "fk", req=True, ref=("cases", "case_id", "case_name")),
            fld("investigation_id", "Collected by", "fk", req=True,
                ref=("investigations", "investigation_id", "name")),
            fld("evidence_type_id", "Evidence type", "fk", req=True,
                ref=("evidence_types", "evidence_type_id", "type_name")),
            fld("file_name", "File / item name", req=True),
            fld("description", "Description", "textarea"),
            fld("hash_value", "Hash value", hint="Integrity checksum, e.g. SHA-256"),
            fld("date_collected", "Date collected", "date", req=True),
            fld("status", "Status", "select", req=True,
                options=["Collected", "Under Examination", "Analysed", "Archived"]),
        ],
    },
    "storage": {
        "label": "Storage record", "plural": "Storage", "table": "storage", "pk": "storage_id",
        "blurb": "Where each evidence item is kept. One storage record per evidence item.",
        "fields": [
            fld("evidence_id", "Evidence", "fk", req=True,
                ref=("evidence", "evidence_id", "file_name")),
            fld("location", "Location", req=True, hint="e.g. Locker B2, Server rack 3"),
            fld("storage_type", "Storage type", "select", req=True,
                options=["Server", "Cloud", "Local"]),
            fld("access_status", "Access status", "select", req=True,
                options=["Available", "Restricted"]),
        ],
    },
    "chain_of_custody": {
        "label": "Custody record", "plural": "Chain of custody", "table": "chain_of_custody",
        "pk": "custody_id",
        "blurb": "A timestamped log of every action taken on evidence.",
        "fields": [
            fld("evidence_id", "Evidence", "fk", req=True,
                ref=("evidence", "evidence_id", "file_name")),
            fld("investigation_id", "Handled by", "fk", req=True,
                ref=("investigations", "investigation_id", "name")),
            fld("action", "Action", "select", req=True,
                options=["Collected", "Transferred", "Examined", "Stored"]),
            fld("date_time", "Date and time", "datetime", req=True),
            fld("remarks", "Remarks", "textarea"),
        ],
    },
}


# ---------------- database ----------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            conn.executescript(fh.read())
    finally:
        conn.close()


def get_entity(name):
    if name not in ENTITIES:
        abort(404)
    return ENTITIES[name]


def choices_for(field):
    if field["kind"] == "select":
        return [(o, o) for o in field["options"]]
    if field["kind"] == "fk":
        table, pk, disp = field["ref"]
        rows = get_db().execute(
            f"SELECT {pk}, {disp} FROM {table} ORDER BY {pk}").fetchall()
        return [(r[pk], f"#{r[pk]} {r[disp]}") for r in rows]
    return []


def form_fields(ent):
    return [dict(f, choices=choices_for(f)) for f in ent["fields"]]


def read_form(ent):
    data, errors = {}, []
    for f in ent["fields"]:
        val = request.form.get(f["col"], "").strip()
        if f["req"] and not val:
            errors.append(f"{f['label']} is required.")
        if f["kind"] == "select" and val and val not in f["options"]:
            errors.append(f"{f['label']} has an invalid value.")
        data[f["col"]] = val or None
    return data, errors


def friendly_error(exc):
    msg = str(exc)
    if "UNIQUE" in msg:
        return "That value already exists and must be unique."
    if "CHECK" in msg:
        return "A value is not allowed by the database rules."
    if "FOREIGN KEY" in msg:
        return "The selected related record does not exist."
    if "NOT NULL" in msg:
        return "A required field is missing."
    return f"Database error: {msg}"


# ---------------- templates ----------------

LAYOUT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} · Evidence Vault</title>
<style>
:root{--navy:#0c1a2e;--navy2:#17305a;--gold:#c9a227;--gold2:#e3be4f;--bg:#f3f5f9;
      --ink:#1c2333;--muted:#6b7385;--line:#e4e8f0;
      --shadow:0 1px 2px rgba(12,26,46,.04),0 10px 30px rgba(12,26,46,.07)}
*{box-sizing:border-box}
body{margin:0;font-family:"Segoe UI Variable","Segoe UI",Inter,system-ui,sans-serif;
     background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased;min-height:100vh;
     display:flex;flex-direction:column}
header{background:linear-gradient(120deg,var(--navy) 0%,var(--navy2) 100%);color:#fff;
       border-bottom:3px solid var(--gold)}
.top{max-width:1200px;margin:0 auto;padding:22px 32px 0;display:flex;justify-content:space-between;
     align-items:flex-end;gap:20px;flex-wrap:wrap}
.brand{font-family:Georgia,"Times New Roman",serif;font-size:24px;letter-spacing:.3px}
.brand small{display:block;font-family:"Segoe UI",sans-serif;font-size:10.5px;letter-spacing:2.5px;
             text-transform:uppercase;color:#9fb0cc;margin-top:6px}
.seal{font-size:12px;color:#9fb0cc;letter-spacing:.5px;padding-bottom:14px}
nav{max-width:1200px;margin:14px auto 0;padding:0 32px;display:flex;flex-wrap:wrap;gap:4px}
nav a{color:#c7d2e6;text-decoration:none;font-size:13.5px;padding:11px 15px;border-radius:9px 9px 0 0;
      transition:background .15s,color .15s}
nav a:hover{color:#fff;background:rgba(255,255,255,.08)}
nav a.on{color:#fff;background:rgba(255,255,255,.14);box-shadow:inset 0 -2px 0 var(--gold)}
main{max-width:1200px;width:100%;margin:0 auto;padding:34px 32px 60px;flex:1}
h2{font-family:Georgia,"Times New Roman",serif;font-weight:normal;font-size:30px;margin:0 0 4px;color:var(--navy)}
.sub{color:var(--muted);font-size:14px;margin:0 0 26px;line-height:1.5}
.toolbar{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}
.search{display:flex;gap:8px;flex:1;max-width:420px}
.search input{flex:1}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 17px;border:0;border-radius:9px;
     background:var(--navy);color:#fff;text-decoration:none;font:inherit;font-size:13.5px;font-weight:600;
     cursor:pointer;transition:background .15s,transform .05s,box-shadow .15s}
.btn:hover{background:var(--navy2);box-shadow:0 4px 12px rgba(12,26,46,.18)}
.btn:active{transform:translateY(1px)}
.btn.gold{background:linear-gradient(120deg,var(--gold),var(--gold2));color:var(--navy)}
.btn.gold:hover{box-shadow:0 4px 14px rgba(201,162,39,.35)}
.btn.ghost{background:#fff;color:var(--navy);border:1px solid #d3d9e5}
.btn.ghost:hover{background:#f7f9fc;box-shadow:none}
.btn.danger{background:#fff;color:#b3261e;border:1px solid #f1cfcb}
.btn.danger:hover{background:#fdecea;box-shadow:none}
.btn.sm{padding:5px 11px;font-size:12.5px}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);overflow:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{background:#f9fafc;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.7px;
   font-size:11px;text-align:left;padding:14px 16px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:14px 16px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
tbody tr:hover td{background:#fbfcfe}
td.id{font-family:Consolas,monospace;color:var(--muted);font-size:12.5px}
td.actions{white-space:nowrap}
td.actions a{color:var(--navy);text-decoration:none;font-weight:600;margin-right:14px}
td.actions a:hover{text-decoration:underline}
td.actions form{display:inline}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;
       background:#eef1f7;color:#41506b;white-space:nowrap}
.b-open,.b-active,.b-available,.b-completed{background:#e6f5ec;color:#17693a}
.b-closed,.b-inactive,.b-archived{background:#eceef2;color:#555e6e}
.b-restricted{background:#fdecea;color:#a3271f}
.b-under-examination{background:#fff3d6;color:#8a5a00}
.b-analysed,.b-collected,.b-stored,.b-transferred,.b-examined{background:#e8effb;color:#2452a0}
.empty{text-align:center;color:var(--muted);padding:56px 16px}
.flash{padding:13px 18px;margin-bottom:24px;border-radius:12px;background:#fff8e1;
       border:1px solid #f0d98a;color:#5b4a12;font-size:14px;box-shadow:var(--shadow)}
.flash.bad{background:#fdecea;border-color:#f1c0bb;color:#7a1f18}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:32px;max-width:700px;
      box-shadow:var(--shadow)}
label{display:block;font-size:11.5px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;
      color:var(--muted);margin:22px 0 7px}
label:first-of-type{margin-top:0}
.hint{display:block;font-size:12px;color:#9aa2b3;text-transform:none;letter-spacing:0;margin-top:5px;font-weight:400}
input,select,textarea{width:100%;padding:11px 13px;border:1px solid #d3d9e5;border-radius:9px;
      font:inherit;font-size:14px;background:#fff;color:var(--ink);transition:border-color .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--navy2);box-shadow:0 0 0 3px rgba(23,48,90,.13)}
.req{color:var(--gold)}
.form-actions{margin-top:28px;display:flex;gap:16px;align-items:center}
.form-actions a{color:var(--muted);text-decoration:none;font-size:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:20px}
.stat{padding:26px;border-radius:16px;background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);
      text-decoration:none;color:inherit;display:block;transition:transform .18s,box-shadow .18s;
      border-top:3px solid var(--gold)}
.stat:hover{transform:translateY(-3px);box-shadow:0 16px 34px rgba(12,26,46,.12)}
.stat .l{font-size:11.5px;text-transform:uppercase;letter-spacing:1.1px;color:var(--muted)}
.stat .n{font-family:Georgia,"Times New Roman",serif;font-size:42px;color:var(--navy);margin:10px 0 6px}
.stat .d{font-size:12.5px;color:var(--muted);line-height:1.45;min-height:36px}
.stat .go{font-size:13px;color:var(--gold);font-weight:700;margin-top:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:16px;margin-bottom:34px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:var(--shadow)}
.kpi .v{font-family:Georgia,serif;font-size:26px;color:var(--navy)}
.kpi .k{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.9px;margin-top:4px}
.seed{margin-top:34px;padding:22px 24px;border-radius:14px;background:linear-gradient(120deg,#fffaf0,#fff);
      border:1px dashed #e0c97a;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.seed p{margin:0;font-size:14px;color:#5c4d1d}
footer{max-width:1200px;margin:0 auto;padding:18px 32px 28px;color:#9aa2b3;font-size:12px;width:100%}
</style></head><body>
<header>
  <div class="top">
    <div class="brand">Evidence Vault<small>Digital Evidence Management System</small></div>
    <div class="seal">Cybercrime investigation records</div>
  </div>
  <nav>
    <a href="{{ url_for('dashboard') }}" class="{{ 'on' if active == 'dashboard' }}">Dashboard</a>
    {% for key, ent in entities.items() %}
      <a href="{{ url_for('list_rows', entity=key) }}" class="{{ 'on' if active == key }}">{{ ent.plural }}</a>
    {% endfor %}
  </nav>
</header>
<main>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% for cat, m in messages %}<div class="flash {{ cat }}">{{ m }}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</main>
<footer>Evidence Vault · Database Systems project · SQLite + Flask</footer>
</body></html>"""

DASHBOARD = """
<h2>Overview</h2>
<p class="sub">Live view of every case, investigator and piece of evidence in the vault.</p>
<div class="kpis">
  <div class="kpi"><div class="v">{{ kpi.open_cases }}</div><div class="k">Open cases</div></div>
  <div class="kpi"><div class="v">{{ kpi.under_exam }}</div><div class="k">Under examination</div></div>
  <div class="kpi"><div class="v">{{ kpi.restricted }}</div><div class="k">Restricted storage</div></div>
  <div class="kpi"><div class="v">{{ kpi.custody }}</div><div class="k">Custody events</div></div>
</div>
<div class="cards">
{% for key, ent in entities.items() %}
  <a class="stat" href="{{ url_for('list_rows', entity=key) }}">
    <div class="l">{{ ent.plural }}</div>
    <div class="n">{{ counts[key] }}</div>
    <div class="d">{{ ent.blurb }}</div>
    <div class="go">Manage &rarr;</div>
  </a>
{% endfor %}
</div>
{% if total == 0 %}
<div class="seed">
  <p><strong>The vault is empty.</strong> Load the sample scenario (Case 101, a suspicious laptop) to see every feature working.</p>
  <form method="post" action="{{ url_for('load_sample') }}">
    <button class="btn gold" type="submit">Load sample data</button>
  </form>
</div>
{% endif %}
"""

LIST = """
<h2>{{ ent.plural }}</h2>
<p class="sub">{{ ent.blurb }} <strong>{{ rows|length }}</strong> record{{ '' if rows|length == 1 else 's' }}{% if q %} matching “{{ q }}”{% endif %}.</p>
<div class="toolbar">
  <form class="search" method="get">
    <input type="search" name="q" value="{{ q or '' }}" placeholder="Search {{ ent.plural|lower }}…">
    <button class="btn ghost" type="submit">Search</button>
  </form>
  <a class="btn gold" href="{{ url_for('create_row', entity=key) }}">+ Add {{ ent.label|lower }}</a>
</div>
{% set badges = ['Open','Closed','Active','Inactive','Completed','Collected','Under Examination',
                 'Analysed','Archived','Available','Restricted','Transferred','Examined','Stored'] %}
<div class="panel">
<table>
<thead><tr><th>#</th>{% for f in ent.fields %}<th>{{ f.label }}</th>{% endfor %}<th>Actions</th></tr></thead>
<tbody>
{% for row in rows %}
<tr><td class="id">{{ row.id }}</td>
  {% for c in row.cells %}<td>{% if c in badges %}<span class="badge b-{{ c|lower|replace(' ', '-') }}">{{ c }}</span>{% else %}{{ c }}{% endif %}</td>{% endfor %}
  <td class="actions">
    <a href="{{ url_for('edit_row', entity=key, rid=row.id) }}">Edit</a>
    <form method="post" action="{{ url_for('delete_row', entity=key, rid=row.id) }}"
          onsubmit="return confirm('Delete this record? This cannot be undone.');">
      <button class="btn danger sm" type="submit">Delete</button>
    </form>
  </td></tr>
{% else %}
<tr><td class="empty" colspan="{{ ent.fields|length + 2 }}">{% if q %}No records match your search.{% else %}No records yet. Add the first one above.{% endif %}</td></tr>
{% endfor %}
</tbody>
</table>
</div>
"""

FORM = """
<h2>{{ heading }}</h2>
<p class="sub">Fields marked <span class="req">*</span> are required.</p>
<form class="card" method="post">
{% for f in fields %}
  <label for="{{ f.col }}">{{ f.label }}{% if f.req %} <span class="req">*</span>{% endif %}
    {% if f.hint %}<span class="hint">{{ f.hint }}</span>{% endif %}</label>
  {% if f.kind == 'textarea' %}
    <textarea id="{{ f.col }}" name="{{ f.col }}" rows="3">{{ values.get(f.col) or '' }}</textarea>
  {% elif f.kind in ['select', 'fk'] %}
    <select id="{{ f.col }}" name="{{ f.col }}" {% if f.req %}required{% endif %}>
      <option value="">Select…</option>
      {% for v, label in f.choices %}
        <option value="{{ v }}" {% if values.get(f.col) is not none and values.get(f.col)|string == v|string %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
  {% else %}
    <input id="{{ f.col }}" name="{{ f.col }}"
           type="{{ {'date': 'date', 'datetime': 'datetime-local'}.get(f.kind, 'text') }}"
           value="{{ values.get(f.col) or '' }}" {% if f.req %}required{% endif %}>
  {% endif %}
{% endfor %}
<div class="form-actions">
  <button class="btn" type="submit">Save record</button>
  <a href="{{ url_for('list_rows', entity=key) }}">Cancel</a>
</div>
</form>
"""


def page(title, template, active=None, **ctx):
    body = render_template_string(template, **ctx)
    return render_template_string(LAYOUT, title=title, body=body,
                                  entities=ENTITIES, active=active)


# ---------------- routes ----------------

@app.route("/")
def dashboard():
    db = get_db()
    counts = {k: db.execute(f"SELECT COUNT(*) FROM {e['table']}").fetchone()[0]
              for k, e in ENTITIES.items()}
    kpi = {
        "open_cases": db.execute("SELECT COUNT(*) FROM cases WHERE status='Open'").fetchone()[0],
        "under_exam": db.execute("SELECT COUNT(*) FROM evidence WHERE status='Under Examination'").fetchone()[0],
        "restricted": db.execute("SELECT COUNT(*) FROM storage WHERE access_status='Restricted'").fetchone()[0],
        "custody": counts["chain_of_custody"],
    }
    return page("Overview", DASHBOARD, active="dashboard", entities=ENTITIES,
                counts=counts, kpi=kpi, total=sum(counts.values()))


@app.route("/<entity>")
def list_rows(entity):
    ent = get_entity(entity)
    q = request.args.get("q", "").strip()
    sql = f"SELECT * FROM {ent['table']}"
    params = []
    if q:
        cols = [f["col"] for f in ent["fields"]]
        sql += " WHERE " + " OR ".join(f"CAST({c} AS TEXT) LIKE ?" for c in cols)
        params = [f"%{q}%"] * len(cols)
    sql += f" ORDER BY {ent['pk']}"
    rows = get_db().execute(sql, params).fetchall()

    lookups = {f["col"]: dict(choices_for(f)) for f in ent["fields"] if f["kind"] == "fk"}
    view = []
    for r in rows:
        cells = []
        for f in ent["fields"]:
            v = r[f["col"]]
            if f["kind"] == "fk":
                v = lookups[f["col"]].get(v, v)
            cells.append("" if v is None else v)
        view.append({"id": r[ent["pk"]], "cells": cells})
    return page(ent["plural"], LIST, active=entity, ent=ent, key=entity, rows=view, q=q)


@app.route("/<entity>/new", methods=["GET", "POST"])
def create_row(entity):
    ent = get_entity(entity)
    values = {}
    if request.method == "POST":
        data, errors = read_form(ent)
        if not errors:
            db = get_db()
            cols = list(data)
            sql = (f"INSERT INTO {ent['table']} ({', '.join(cols)}) "
                   f"VALUES ({', '.join('?' for _ in cols)})")
            try:
                db.execute(sql, [data[c] for c in cols])
                db.commit()
                flash(f"{ent['label']} added successfully.")
                return redirect(url_for("list_rows", entity=entity))
            except sqlite3.IntegrityError as exc:
                db.rollback()
                errors.append(friendly_error(exc))
        for msg in errors:
            flash(msg, "bad")
        values = request.form.to_dict()
    return page(f"Add {ent['label']}", FORM, active=entity,
                heading=f"Add {ent['label'].lower()}", fields=form_fields(ent),
                values=values, key=entity)


@app.route("/<entity>/<int:rid>/edit", methods=["GET", "POST"])
def edit_row(entity, rid):
    ent = get_entity(entity)
    db = get_db()
    row = db.execute(f"SELECT * FROM {ent['table']} WHERE {ent['pk']} = ?", (rid,)).fetchone()
    if row is None:
        abort(404)
    if request.method == "POST":
        data, errors = read_form(ent)
        if not errors:
            sets = ", ".join(f"{c} = ?" for c in data)
            try:
                db.execute(f"UPDATE {ent['table']} SET {sets} WHERE {ent['pk']} = ?",
                           [*data.values(), rid])
                db.commit()
                flash(f"{ent['label']} updated successfully.")
                return redirect(url_for("list_rows", entity=entity))
            except sqlite3.IntegrityError as exc:
                db.rollback()
                errors.append(friendly_error(exc))
        for msg in errors:
            flash(msg, "bad")
        values = request.form.to_dict()
    else:
        values = dict(row)
    return page(f"Edit {ent['label']}", FORM, active=entity,
                heading=f"Edit {ent['label'].lower()} #{rid}", fields=form_fields(ent),
                values=values, key=entity)


@app.route("/<entity>/<int:rid>/delete", methods=["POST"])
def delete_row(entity, rid):
    ent = get_entity(entity)
    db = get_db()
    try:
        cur = db.execute(f"DELETE FROM {ent['table']} WHERE {ent['pk']} = ?", (rid,))
        db.commit()
        if cur.rowcount:
            flash(f"{ent['label']} deleted.")
        else:
            flash("Record not found.", "bad")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Cannot delete: other records depend on this one. "
              "Delete the dependent records first.", "bad")
    return redirect(url_for("list_rows", entity=entity))


SAMPLE_SQL = [
    # Explicit IDs so the sample can be reloaded after records are deleted.
    "INSERT INTO cases (case_id, case_name, case_type, description, date_opened, status) "
    "VALUES (1, 'Cybercrime Case 101', 'Fraud', 'Suspicious laptop linked to online fraud', '2026-09-15', 'Open')",
    "INSERT INTO investigations (investigation_id, case_id, name, email, phone, role, start_date, status) "
    "VALUES (1, 1, 'Investigator A', 'investigator.a@example.com', '+91 90000 00001', 'Investigator', '2026-09-15', 'Active')",
    "INSERT INTO evidence_types (evidence_type_id, type_name, description) VALUES "
    "(1, 'Device', 'Physical hardware such as laptops and phones'), "
    "(2, 'Log', 'System and network log files'), (3, 'Image', 'Screenshots and photographs')",
    "INSERT INTO evidence (evidence_id, case_id, investigation_id, evidence_type_id, file_name, description, "
    "hash_value, date_collected, status) VALUES (1, 1, 1, 1, 'Laptop-01', 'Suspicious laptop', "
    "'abc123def456', '2026-09-15', 'Under Examination')",
    "INSERT INTO evidence (evidence_id, case_id, investigation_id, evidence_type_id, file_name, description, "
    "hash_value, date_collected, status) VALUES (2, 1, 1, 2, 'Firewall-log-0915', 'Firewall export', "
    "'9f8e7d6c5b4a', '2026-09-15', 'Collected')",
    "INSERT INTO storage (storage_id, evidence_id, location, storage_type, access_status) "
    "VALUES (1, 1, 'Locker B2', 'Local', 'Restricted')",
    "INSERT INTO storage (storage_id, evidence_id, location, storage_type, access_status) "
    "VALUES (2, 2, 'Server rack 3', 'Server', 'Available')",
    "INSERT INTO chain_of_custody (custody_id, evidence_id, investigation_id, action, date_time, remarks) "
    "VALUES (1, 1, 1, 'Collected', '2026-09-15T10:30', 'Seized on site')",
    "INSERT INTO chain_of_custody (custody_id, evidence_id, investigation_id, action, date_time, remarks) "
    "VALUES (2, 1, 1, 'Stored', '2026-09-15T12:00', 'Moved to evidence locker')",
]


@app.route("/load-sample", methods=["POST"])
def load_sample():
    db = get_db()
    total = sum(db.execute(f"SELECT COUNT(*) FROM {e['table']}").fetchone()[0]
                for e in ENTITIES.values())
    if total:
        flash("Vault already contains data. Sample data was not loaded.", "bad")
    else:
        for stmt in SAMPLE_SQL:
            db.execute(stmt)
        db.commit()
        flash("Sample scenario loaded: Cybercrime Case 101.")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
