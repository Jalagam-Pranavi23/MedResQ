import os
import sqlite3
import secrets
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "medresq.sqlite3"
app = Flask(__name__)
app.secret_key = os.environ.get("MEDRESQ_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Directory preview entries; replace with verified provider information before public launch.
RESOURCES = [
    {"id": "sample-hospital-1", "name": "City Care Hospital · Directory Preview", "type": "Hospital", "area": "Madhapur", "icon": "🏥", "description": "Hospital directory entry with location information for easy browsing.", "details": "Check the provider’s current address, services and availability before travelling."},
    {"id": "sample-hospital-2", "name": "Lifeline Medical Centre · Directory Preview", "type": "Hospital", "area": "Kondapur", "icon": "🏥", "description": "Healthcare directory entry to help you explore nearby options.", "details": "Check the provider’s current address, services and availability before travelling."},
    {"id": "sample-blood-1", "name": "Red Drop Blood Bank · Directory Preview", "type": "Blood bank", "area": "Ameerpet", "icon": "🩸", "description": "Blood-bank directory entry. Contact the provider to confirm current stock and eligibility.", "details": "Contact a registered blood bank to confirm blood-group stock and eligibility."},
    {"id": "sample-blood-2", "name": "Hope Blood Centre · Directory Preview", "type": "Blood bank", "area": "Secunderabad", "icon": "🩸", "description": "Blood donation directory entry. Contact the provider for current service information.", "details": "Contact a registered blood bank to confirm blood-group stock and eligibility."},
    {"id": "sample-ambulance-1", "name": "Rapid Response Ambulance · Directory Preview", "type": "Ambulance service", "area": "Gachibowli", "icon": "🚑", "description": "Ambulance service directory entry. Contact the provider for current service information.", "details": "For immediate emergency assistance in India, call 112."},
    {"id": "sample-ambulance-2", "name": "City Ambulance Network · Directory Preview", "type": "Ambulance service", "area": "Begumpet", "icon": "🚑", "description": "Ambulance service directory entry for browsing by area.", "details": "For immediate emergency assistance in India, call 112."},
]
RESOURCE_BY_ID = {item["id"]: item for item in RESOURCES}


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'patient', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS suggestions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      resource_name TEXT NOT NULL, resource_type TEXT NOT NULL, area TEXT NOT NULL,
      notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending review',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS saved_resources(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      resource_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, resource_id),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS contact_messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
      name TEXT NOT NULL, email TEXT NOT NULL, subject TEXT NOT NULL,
      message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Received',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL);
    """)
    # Add columns when opening a database created by the earlier MedResQ ZIP.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(suggestions)")}
    if "notes" not in columns:
        conn.execute("ALTER TABLE suggestions ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    if "status" not in columns:
        conn.execute("ALTER TABLE suggestions ADD COLUMN status TEXT NOT NULL DEFAULT 'Pending review'")
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "role" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'patient'")
    # Local demonstration accounts for the provider and administrator workspaces.
    demo_accounts = [
        ("MedResQ Administrator", "admin@medresq.local", "Admin@12345", "admin"),
        ("MedResQ Provider", "provider@medresq.local", "Provider@12345", "provider"),
    ]
    for name, email, password, role in demo_accounts:
        exists = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not exists:
            conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
                         (name, email, generate_password_hash(password), role))
    conn.commit()
    conn.close()


def get_user():
    uid = session.get("user_id")
    return db().execute("SELECT id,name,email,role FROM users WHERE id=?", (uid,)).fetchone() if uid else None


@app.context_processor
def inject():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"current_user": get_user(), "csrf_token": session["csrf_token"]}


@app.before_request
def csrf_check():
    if request.method == "POST":
        sent, expected = request.form.get("csrf_token", ""), session.get("csrf_token", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Your session expired. Please return to the page and try again.")


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            user = get_user()
            if not user or user["role"] not in allowed_roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def home_for_role(role):
    if role == "admin":
        return url_for("admin_dashboard")
    if role == "provider":
        return url_for("provider_dashboard")
    return url_for("dashboard")


@app.get("/")
def index():
    saved_ids = set()
    if session.get("user_id"):
        rows = db().execute("SELECT resource_id FROM saved_resources WHERE user_id=?", (session["user_id"],)).fetchall()
        saved_ids = {row["resource_id"] for row in rows}
    return render_template("index.html", resources=RESOURCES, saved_ids=saved_ids)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or len(name) > 80:
            flash("Please enter your name (up to 80 characters).", "error")
        elif "@" not in email or "." not in email.rsplit("@", 1)[-1] or len(email) > 254:
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif password != request.form.get("confirm_password", ""):
            flash("The passwords do not match.", "error")
        else:
            try:
                cur = db().execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'patient')",
                                   (name, email, generate_password_hash(password)))
                db().commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                session["csrf_token"] = secrets.token_urlsafe(32)
                flash("Your patient account is ready. Welcome to MedResQ!", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists. Please log in.", "error")
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        user = get_user()
        return redirect(home_for_role(user["role"] if user else "patient"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        requested_role = request.form.get("role", "patient").strip().lower()
        if requested_role not in {"patient", "provider", "admin"}:
            requested_role = "patient"
        user = db().execute("SELECT id,password_hash,role FROM users WHERE email=?", (email,)).fetchone()
        if user and user["role"] == requested_role and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            flash("Welcome back to MedResQ.", "success")
            nxt = request.args.get("next", "")
            if requested_role == "patient" and nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(home_for_role(requested_role))
        flash("The selected account type, email or password does not match.", "error")
    return render_template("auth.html", mode="login")

@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("index"))


@app.get("/dashboard")
@login_required
def dashboard():
    user = get_user()
    if user and user["role"] != "patient":
        return redirect(home_for_role(user["role"]))
    items = db().execute("SELECT * FROM suggestions WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    saved_rows = db().execute("SELECT resource_id FROM saved_resources WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    saved_resources = [RESOURCE_BY_ID[row["resource_id"]] for row in saved_rows if row["resource_id"] in RESOURCE_BY_ID]
    messages = db().execute("SELECT * FROM contact_messages WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    return render_template("dashboard.html", user=user, items=items, saved_resources=saved_resources, messages=messages)


@app.get("/provider")
@role_required("provider")
def provider_dashboard():
    user = get_user()
    return render_template("provider_dashboard.html", user=user, resources=RESOURCES)


@app.get("/admin")
@role_required("admin")
def admin_dashboard():
    users = db().execute("SELECT id,name,email,role,created_at FROM users ORDER BY id DESC").fetchall()
    suggestions = db().execute("SELECT s.*,u.name AS user_name,u.email AS user_email FROM suggestions s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC").fetchall()
    messages = db().execute("SELECT * FROM contact_messages ORDER BY id DESC").fetchall()
    return render_template("admin_dashboard.html", user=get_user(), users=users, suggestions=suggestions, messages=messages)


@app.post("/admin/suggestion/<int:suggestion_id>/status")
@role_required("admin")
def update_suggestion_status(suggestion_id):
    status = request.form.get("status", "").strip()
    if status not in {"Pending review", "Approved", "Rejected"}:
        abort(400, "Choose a valid suggestion status.")
    cur = db().execute("UPDATE suggestions SET status=? WHERE id=?", (status, suggestion_id))
    db().commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Suggestion status updated.", "success")
    return redirect(url_for("admin_dashboard") + "#suggestions")


@app.post("/suggest")
@login_required
def suggest():
    name = request.form.get("resource_name", "").strip()
    kind = request.form.get("resource_type", "").strip()
    area = request.form.get("area", "").strip()
    notes = request.form.get("notes", "").strip()
    if not name or len(name) > 120 or not area or len(area) > 120 or len(notes) > 500 or kind not in {"Hospital", "Blood bank", "Ambulance service", "Other"}:
        flash("Please check the resource name, type, area and notes.", "error")
        return redirect(url_for("index") + "#suggest-resource")
    db().execute("INSERT INTO suggestions(user_id,resource_name,resource_type,area,notes) VALUES(?,?,?,?,?)",
                 (session["user_id"], name, kind, area, notes))
    db().commit()
    flash("Suggestion received. Its status is Pending review.", "success")
    return redirect(url_for("dashboard"))


@app.post("/save-resource/<resource_id>")
@login_required
def save_resource(resource_id):
    if resource_id not in RESOURCE_BY_ID:
        abort(404)
    db().execute("INSERT OR IGNORE INTO saved_resources(user_id,resource_id) VALUES(?,?)",
                 (session["user_id"], resource_id))
    db().commit()
    flash("Resource saved to your dashboard.", "success")
    return redirect(request.form.get("next") if request.form.get("next") == "dashboard" else url_for("index") + "#resources")


@app.post("/unsave-resource/<resource_id>")
@login_required
def unsave_resource(resource_id):
    db().execute("DELETE FROM saved_resources WHERE user_id=? AND resource_id=?", (session["user_id"], resource_id))
    db().commit()
    flash("Saved resource removed.", "success")
    return redirect(url_for("dashboard"))


@app.route("/contact", methods=["GET", "POST"])
def contact():
    user = get_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if not name or len(name) > 80 or "@" not in email or len(email) > 254 or not subject or len(subject) > 120 or not message or len(message) > 2000:
            flash("Please complete all fields with valid information. Messages can be up to 2,000 characters.", "error")
            return render_template("contact.html", user=user), 400
        db().execute("INSERT INTO contact_messages(user_id,name,email,subject,message) VALUES(?,?,?,?,?)",
                     (user["id"] if user else None, name, email, subject, message))
        db().commit()
        flash("Thanks — your message has been recorded.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html", user=user)


@app.errorhandler(400)
def bad_request(err):
    return render_template("error.html", code=400, message=getattr(err, "description", "Please try again.")), 400


@app.errorhandler(403)
def forbidden(err):
    return render_template("error.html", code=403, message="This workspace is not available for your account type."), 403


@app.errorhandler(404)
def missing(err):
    return render_template("error.html", code=404, message="The page you requested could not be found."), 404


@app.errorhandler(500)
def server_error(err):
    return render_template("error.html", code=500, message="Something went wrong. Please return to MedResQ and try again."), 500


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
