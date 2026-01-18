from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime, timedelta
import pytz

import sqlite3, pandas as pd, os



app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False

#app.secret_key = "rnsit_admin_secret_2025"

app.secret_key = "rnsit-multidisciplinary-project-2025-26"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "rnsit_multidisciplinary_project_2025_26_v3.db")


ADMIN_USER = "rnsit_admin"
ADMIN_PASS = "RNSIT@2025"

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con
def ensure_students_table():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usn TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    con.close()
 
def add_column_if_not_exists(table, column, col_type):
    con = db()
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        con.commit()
    con.close()

from datetime import datetime, timedelta

def get_week_deadline(team_created_at, week_no):
    """
    Deadline rule:
    Week N deadline = Saturday 11:59 PM IST of that week,
    where Week 1 deadline is the first Saturday after team_created_at.
    """
    if isinstance(team_created_at, str):
        try:
            team_created_at = datetime.fromisoformat(team_created_at)
        except:
            team_created_at = datetime.strptime(team_created_at, "%Y-%m-%d %H:%M:%S")

    # Find next Saturday from created_at date
    # Python weekday: Mon=0 ... Sat=5 ... Sun=6
    created_weekday = team_created_at.weekday()
    days_to_saturday = (5 - created_weekday) % 7
    if days_to_saturday == 0:
        # If already Saturday, deadline is same day 11:59 PM
        first_saturday = team_created_at
    else:
        first_saturday = team_created_at + timedelta(days=days_to_saturday)

    # Set time to 23:59:00
    first_deadline = first_saturday.replace(hour=23, minute=59, second=0, microsecond=0)

    # Week 2 = +7 days, Week 3 = +14 days...
    deadline = first_deadline + timedelta(days=(week_no - 1) * 7)
    return deadline


def compute_late_status(submitted_at, deadline):
    if isinstance(submitted_at, str):
        try:
            submitted_at = datetime.fromisoformat(submitted_at)
        except:
            submitted_at = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S")

    late_seconds = (submitted_at - deadline).total_seconds()
    if late_seconds <= 0:
        return ("On Time", None)

    # Late duration
    late_days = int(late_seconds // 86400)
    late_hours = int((late_seconds % 86400) // 3600)

    if late_days > 0:
        return ("Late", f"{late_days} day(s) {late_hours} hour(s)")
    else:
        return ("Late", f"{late_hours} hour(s)")


from datetime import datetime


@app.route("/student/signup", methods=["GET", "POST"])
def student_signup():
    ensure_students_table()
    if request.method == "POST":
        usn = request.form["usn"].strip().upper()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not email.endswith("@rnsit.ac.in"):
            flash("Only RNSIT email IDs are allowed")
            return redirect(request.url)

        password_hash = generate_password_hash(password)

        con = db()
        cur = con.cursor()

        try:
            cur.execute(
                "INSERT INTO students (usn, email, password_hash) VALUES (?,?,?)",
                (usn, email, password_hash)
            )
            con.commit()
            con.close()
            flash("Account created successfully. Please login.")
            return redirect(url_for("student_login"))
        except:
            con.close()
            flash("USN or Email already registered")

    return render_template("student_signup.html")
@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    ensure_students_table()
    if request.method == "POST":
        usn = request.form["usn"].strip().upper()
        password = request.form["password"]

        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT email, password_hash FROM students WHERE usn=?",
            (usn,)
        )

        row = cur.fetchone()
        con.close()
        if not row:
            flash("User not found. Please sign up first.")
            return redirect(request.url)

        if not check_password_hash(row["password_hash"], password):
            flash("Invalid password")
            return redirect(request.url)

        session["student_usn"] = usn
        session["student_email"] = row["email"]
        return redirect(url_for("student_home"))

    return render_template("student_login.html")
@app.route("/student/logout")
def student_logout():
    session.pop("student_usn", None)
    session.pop("student_email", None)
    flash("Logged out successfully")
    return redirect(url_for("student_login"))

@app.route("/student/home")
def student_home():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, title, category, difficulty, max_teams
        FROM problems
    """)
    problems = cur.fetchall()

    data = []
    for p in problems:
        cur.execute(
            "SELECT COUNT(*) FROM teams WHERE problem_id=?",
            (p["id"],)
        )
        count = cur.fetchone()[0]
        data.append((p, count))

    con.close()

    return render_template("student_home.html", problems=data)

@app.route("/student/problems")
def student_problems():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT id, year, title, category, difficulty, max_teams,
               problem_description, problem_details, expected_outcome
        FROM problems
        ORDER BY year DESC
    """)
    probs = cur.fetchall()

    data = []
    for p in probs:
        cur.execute("SELECT COUNT(*) FROM teams WHERE problem_id=?", (p["id"],))
        registered_count = cur.fetchone()[0]
        data.append((p, registered_count))

    con.close()

    return render_template("student_problems.html", data=data)

@app.route("/student/my-registration")
def student_my_registration():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # 1️⃣ Check if student is TEAM LEADER
    cur.execute("""
        SELECT
            t.team_name,
            t.leader_usn,
            p.title AS problem_title
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.leader_usn = ?
    """, (usn,))
    row = cur.fetchone()

    # 2️⃣ If not leader, check TEAM MEMBERS
    if not row:
        cur.execute("""
            SELECT
                t.team_name,
                t.leader_usn,
                p.title AS problem_title
            FROM team_members m
            JOIN teams t ON m.team_id = t.id
            JOIN problems p ON t.problem_id = p.id
            WHERE m.usn = ?
        """, (usn,))
        row = cur.fetchone()

    con.close()

    return render_template(
        "student_my_registration.html",
        registration=row
    )

@app.route("/student/my-project")
def student_my_project():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # Find team where student is leader
    cur.execute("""
        SELECT t.*, p.title AS problem_title, p.year AS problem_year
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.leader_usn=?
    """, (usn,))
    team = cur.fetchone()
    # Fetch abstract/objectives from project_details table
    cur.execute("""
        SELECT abstract, objectives
        FROM project_details
        WHERE team_id=?
    """, (team["id"],))
    pd = cur.fetchone()

    # If not leader, check member
    if not team:
        cur.execute("""
            SELECT t.*, p.title AS problem_title, p.year AS problem_year
            FROM team_members m
            JOIN teams t ON m.team_id = t.id
            JOIN problems p ON t.problem_id = p.id
            WHERE m.usn=?
        """, (usn,))
        team = cur.fetchone()

    if not team:
        con.close()
        flash("You are not registered under any project yet.")
        return redirect(url_for("student_home"))
    # Fetch team members
    cur.execute("""
        SELECT member_name, usn, email, phone, department, section
        FROM team_members
        WHERE team_id=?
        ORDER BY id
    """, (team["id"],))
    members = cur.fetchall()

    # Get faculty assigned
    cur.execute("""
        SELECT f.name, f.email, f.department
        FROM team_faculty tf
        JOIN faculty f ON tf.faculty_id = f.id
        WHERE tf.team_id=?
    """, (team["id"],))
    faculty_row = cur.fetchone()

    # Weekly progress count
    cur.execute("SELECT COUNT(*) FROM weekly_progress WHERE team_id=?", (team["id"],))
    progress_count = cur.fetchone()[0]

    con.close()

    return render_template(
        "student_my_project.html",
        team=team,
        faculty=faculty_row,
        progress_count=progress_count,
        project_details=pd,
        members=members
    )


@app.route("/student/project-details", methods=["GET", "POST"])
def student_project_details():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # Get team_id (leader or member)
    cur.execute("""
        SELECT id FROM teams WHERE leader_usn=?
    """, (usn,))
    team = cur.fetchone()

    if not team:
        cur.execute("""
            SELECT t.id
            FROM team_members m
            JOIN teams t ON m.team_id = t.id
            WHERE m.usn=?
        """, (usn,))
        team = cur.fetchone()

    if not team:
        con.close()
        flash("You are not part of any registered team.")
        return redirect(url_for("student_home"))

    team_id = team["id"]

    # Fetch existing details
    cur.execute("""
        SELECT * FROM project_details WHERE team_id=?
    """, (team_id,))
    details = cur.fetchone()

    if request.method == "POST":
        abstract = request.form["abstract"]
        objectives = request.form["objectives"]

        if details:
            cur.execute("""
                UPDATE project_details
                SET abstract=?, objectives=?
                WHERE team_id=?
            """, (abstract, objectives, team_id))
        else:
            cur.execute("""
                INSERT INTO project_details(team_id, abstract, objectives)
                VALUES (?,?,?)
            """, (team_id, abstract, objectives))

        con.commit()
        con.close()
        flash("Project details saved successfully")
        return redirect(url_for("student_project_details"))

    con.close()
    return render_template(
        "student_project_details.html",
        details=details
    )

from datetime import datetime, timedelta, timezone

@app.route("/student/weekly-progress", methods=["GET", "POST"])
def student_weekly_progress():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # Find team_id
    cur.execute("SELECT id FROM teams WHERE leader_usn=?", (usn,))
    team = cur.fetchone()

    if not team:
        cur.execute("""
            SELECT t.id
            FROM team_members m
            JOIN teams t ON m.team_id = t.id
            WHERE m.usn=?
        """, (usn,))
        team = cur.fetchone()

    if not team:
        con.close()
        flash("You are not part of any registered team.")
        return redirect(url_for("student_home"))

    team_id = team["id"]

    # ---------------- AUTO WEEK CALCULATION ----------------
    IST = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(IST)

    # Change this date as per your project start date
    PROJECT_START_DATE = IST.localize(datetime(2026, 1, 1, 0, 0, 0))

    # Week number starts from 1
    auto_week_no = ((now_ist - PROJECT_START_DATE).days // 7) + 1
    if auto_week_no < 1:
        auto_week_no = 1

    # Deadline: Saturday 11:59 PM IST of current week
    # weekday(): Mon=0 ... Sat=5 ... Sun=6
    days_until_saturday = (5 - now_ist.weekday()) % 7
    saturday = (now_ist + timedelta(days=days_until_saturday)).replace(
        hour=23, minute=59, second=0, microsecond=0
    )
    deadline_dt = saturday

    # ---------------- FILTERS ----------------
    show = request.args.get("show", "all")  # all / late / reviewed / pending

    # ---------------- POST: SUBMIT ----------------
    if request.method == "POST":
        progress = request.form.get("progress", "").strip()

        if not progress:
            flash("Progress cannot be empty.")
            con.close()
            return redirect(request.url)

        # Prevent duplicate submission for same week
        cur.execute("""
            SELECT COUNT(*) FROM weekly_progress
            WHERE team_id=? AND week_no=?
        """, (team_id, auto_week_no))
        if cur.fetchone()[0] > 0:
            flash(f"Week {auto_week_no} progress already submitted.")
            con.close()
            return redirect(url_for("student_weekly_progress"))

        cur.execute("""
            INSERT INTO weekly_progress(team_id, week_no, progress)
            VALUES (?,?,?)
        """, (team_id, auto_week_no, progress))

        con.commit()
        flash(f"Weekly progress submitted for Week {auto_week_no} ✅")
        con.close()
        return redirect(url_for("student_weekly_progress"))

    # ---------------- FETCH LIST ----------------
    cur.execute("""
        SELECT * FROM weekly_progress
        WHERE team_id=?
        ORDER BY week_no DESC
    """, (team_id,))
    rows = cur.fetchall()
    con.close()

    progress_list = []
    for r in rows:
        # submitted_at from DB (string)
        submitted_raw = r["submitted_at"]
        submitted_dt = None

        try:
            submitted_dt = datetime.fromisoformat(submitted_raw)
        except:
            try:
                submitted_dt = datetime.strptime(submitted_raw, "%Y-%m-%d %H:%M:%S")
            except:
                submitted_dt = None

        if submitted_dt:
            # assume stored as local time; convert to IST safe
            if submitted_dt.tzinfo is None:
                submitted_dt = IST.localize(submitted_dt)
            submitted_at_ist = submitted_dt.strftime("%d-%m-%Y %I:%M %p (IST)")
        else:
            submitted_at_ist = submitted_raw

        # Deadline for that week number
        week_start = PROJECT_START_DATE + timedelta(days=(r["week_no"] - 1) * 7)
        week_deadline = (week_start + timedelta(days=5)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )

        is_late = False
        if submitted_dt:
            is_late = submitted_dt > week_deadline

        deadline_at = week_deadline.strftime("%d-%m-%Y %I:%M %p (IST)")

        progress_list.append({
            "id": r["id"],
            "week_no": r["week_no"],
            "progress": r["progress"],
            "submitted_at_ist": submitted_at_ist,
            "deadline_at": deadline_at,
            "is_late": is_late,
            "faculty_remark": r["faculty_remark"],
            "status": r["status"]
        })

    # Apply filter
    if show == "late":
        progress_list = [p for p in progress_list if p["is_late"]]
    elif show == "reviewed":
        progress_list = [p for p in progress_list if p["status"] in ["Reviewed", "Approved"]]
    elif show == "pending":
        progress_list = [p for p in progress_list if p["status"] == "Pending"]

    return render_template(
        "student_weekly_progress.html",
        progress_list=progress_list,
        auto_week_no=auto_week_no,
        deadline_dt=deadline_dt.strftime("%d-%m-%Y %I:%M %p (IST)"),
        show=show
    )


@app.route("/faculty/login", methods=["GET", "POST"])
def faculty_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM faculty WHERE email=?",
            (email,)
        )
        faculty = cur.fetchone()
        con.close()

        if not faculty:
            flash("Faculty not found")
            return redirect(request.url)

        if not check_password_hash(faculty["password_hash"], password):
            flash("Invalid password")
            return redirect(request.url)

        session["faculty_id"] = faculty["id"]
        session["faculty_name"] = faculty["name"]

        return redirect(url_for("faculty_dashboard"))

    return render_template("faculty_login.html")

@app.route("/faculty/dashboard")
def faculty_dashboard():
    if not session.get("faculty_id"):
        return redirect(url_for("faculty_login"))

    faculty_id = session["faculty_id"]

    search = request.args.get("search", "").strip().lower()
    status_filter = request.args.get("status", "").strip()

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT
            t.id AS team_id,
            t.team_name,
            t.leader_name,
            t.leader_usn,
            p.title AS problem_title,
            p.year AS problem_year
        FROM team_faculty tf
        JOIN teams t ON tf.team_id = t.id
        JOIN problems p ON t.problem_id = p.id
        WHERE tf.faculty_id = ?
        ORDER BY p.title
    """, (faculty_id,))
    assigned_teams = cur.fetchall()

    # Pending review count
    cur.execute("""
        SELECT COUNT(*)
        FROM weekly_progress wp
        JOIN team_faculty tf ON wp.team_id = tf.team_id
        WHERE tf.faculty_id=? AND wp.status='Pending'
    """, (faculty_id,))
    pending_count = cur.fetchone()[0]

    con.close()

    # Apply search/filter in python (simple)
    filtered = []
    for t in assigned_teams:
        text = f"{t['team_name']} {t['leader_usn']} {t['problem_title']}".lower()
        if search and search not in text:
            continue
        filtered.append(t)

    return render_template(
        "faculty_dashboard.html",
        assigned_teams=filtered,
        pending_count=pending_count,
        search=search,
        status_filter=status_filter
    )


@app.route("/faculty/team/<int:team_id>")
def faculty_team_details(team_id):
    if not session.get("faculty_id"):
        return redirect(url_for("faculty_login"))

    faculty_id = session["faculty_id"]

    con = db()
    cur = con.cursor()

    # Security check: faculty can only access assigned team
    cur.execute("""
        SELECT COUNT(*)
        FROM team_faculty
        WHERE team_id=? AND faculty_id=?
    """, (team_id, faculty_id))

    if cur.fetchone()[0] == 0:
        con.close()
        flash("Access denied")
        return redirect(url_for("faculty_dashboard"))

    # Team + Problem info
    cur.execute("""
        SELECT
            t.team_name,
            t.leader_name,
            t.leader_usn,
            t.leader_email,
            t.leader_phone,
            p.title AS problem_title,
            p.problem_description,
            p.problem_details,
            p.expected_outcome
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.id=?
    """, (team_id,))

    team = cur.fetchone()
    # Fetch abstract/objectives from project_details
    cur.execute("""
        SELECT abstract, objectives
        FROM project_details
        WHERE team_id=?
    """, (team_id,))
    project_details = cur.fetchone()

    # Weekly progress
    cur.execute("""
        SELECT *
        FROM weekly_progress
        WHERE team_id=?
        ORDER BY week_no DESC
    """, (team_id,))
    progress_list = cur.fetchall()

    con.close()

    return render_template(
        "faculty_team_details.html",
        team=team,
        progress_list=progress_list,
        project_details=project_details
    )


@app.route("/faculty/logout")
def faculty_logout():
    session.pop("faculty_id", None)
    session.pop("faculty_name", None)
    flash("Logged out successfully")
    return redirect(url_for("faculty_login"))

@app.route("/admin/assign-faculty", methods=["GET", "POST"])
def admin_assign_faculty():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    # Fetch teams
    cur.execute("SELECT id, team_name, leader_usn FROM teams")
    teams = cur.fetchall()

    # Fetch faculty
    cur.execute("SELECT id, name, department FROM faculty")
    faculty = cur.fetchall()

    if request.method == "POST":
        team_id = request.form["team_id"]
        faculty_id = request.form["faculty_id"]

        # Insert or update mapping
        cur.execute("""
            INSERT INTO team_faculty(team_id, faculty_id)
            VALUES (?, ?)
            ON CONFLICT(team_id) DO UPDATE SET faculty_id=excluded.faculty_id
        """, (team_id, faculty_id))

        con.commit()
        flash("Faculty assigned successfully")

    con.close()

    return render_template(
        "admin_assign_faculty.html",
        teams=teams,
        faculty=faculty
    )

@app.route("/admin/add-faculty", methods=["GET", "POST"])
def admin_add_faculty():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].strip().lower()
        department = request.form["department"]
        password = request.form["password"]

        password_hash = generate_password_hash(password)

        con = db()
        cur = con.cursor()
        try:
            cur.execute("""
                INSERT INTO faculty(name, email, password_hash, department)
                VALUES (?,?,?,?)
            """, (name, email, password_hash, department))
            con.commit()
            flash("Faculty created successfully")
        except:
            flash("Faculty email already exists")
        con.close()

    return render_template("admin_add_faculty.html")

@app.route("/admin/faculty")
def admin_faculty_list():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, name, email, department FROM faculty ORDER BY name")
    faculty = cur.fetchall()
    con.close()

    return render_template("admin_faculty_list.html", faculty=faculty)

@app.route("/admin/faculty/delete/<int:fid>")
def admin_delete_faculty(fid):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    # Remove assignments first
    cur.execute("DELETE FROM team_faculty WHERE faculty_id=?", (fid,))
    # Delete faculty
    cur.execute("DELETE FROM faculty WHERE id=?", (fid,))

    con.commit()
    con.close()

    flash("Faculty deleted successfully")
    return redirect(url_for("admin_faculty_list"))

@app.route("/admin/deadline", methods=["GET", "POST"])
def admin_deadline():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    con = db()
    cur = con.cursor()

    if request.method == "POST":
        deadline = request.form["deadline"]
        cur.execute(
            "REPLACE INTO settings(key,value) VALUES (?,?)",
            ("registration_deadline", deadline)
        )
        con.commit()
        con.close()
        flash("Registration deadline updated successfully")
        return redirect(url_for("admin_deadline"))

    cur.execute(
        "SELECT value FROM settings WHERE key='registration_deadline'"
    )
    row = cur.fetchone()
    con.close()

    return render_template(
        "admin_deadline.html",active_page="deadline",
        deadline=row[0] if row else ""
    )

@app.route("/faculty/review-progress/<int:progress_id>", methods=["POST"])
def faculty_review_progress(progress_id):
    if not session.get("faculty_id"):
        return redirect(url_for("faculty_login"))

    faculty_id = session["faculty_id"]

    remark = request.form.get("faculty_remark", "").strip()
    status = request.form.get("status", "Reviewed").strip()

    con = db()
    cur = con.cursor()

    # Security check: faculty can only review progress of assigned teams
    cur.execute("""
        SELECT wp.team_id
        FROM weekly_progress wp
        JOIN team_faculty tf ON wp.team_id = tf.team_id
        WHERE wp.id=? AND tf.faculty_id=?
    """, (progress_id, faculty_id))

    row = cur.fetchone()
    if not row:
        con.close()
        flash("Access denied")
        return redirect(url_for("faculty_dashboard"))

    team_id = row["team_id"]

    # Update progress review
    cur.execute("""
        UPDATE weekly_progress
        SET faculty_remark=?, status=?
        WHERE id=?
    """, (remark, status, progress_id))

    con.commit()
    con.close()

    flash("Review updated successfully")
    return redirect(url_for("faculty_team_details", team_id=team_id))

"""@app.route("/")
def index():
   con=db(); cur=con.cursor()
    cur.execute(""" """
    SELECT id, year, title, category, difficulty, max_teams,
           problem_description, problem_details, expected_outcome
    FROM problems
"""""")

    probs=cur.fetchall()
    data=[]
    for p in probs:
        cur.execute("SELECT COUNT(*) FROM teams WHERE problem_id=?", (p[0],))
        data.append((p, cur.fetchone()[0]))
    con.close()
    from datetime import datetime

    # Check registration deadline
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key='registration_deadline'")
    row = cur.fetchone()
    con.close()

    registration_closed = False
    if row:
        deadline = datetime.fromisoformat(row[0])
        if datetime.now() > deadline:
            registration_closed = True

    return render_template(
    "index.html",
    data=data,
    registration_closed=registration_closed
)"""
@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/register/<int:pid>", methods=["GET", "POST"])
def register(pid):

    from datetime import datetime

    # ✅ Student must be logged in
    if not session.get("student_usn"):
        flash("Please login as student to register a team.")
        return redirect(url_for("student_login"))

    # --- REGISTRATION DEADLINE CHECK ---
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key='registration_deadline'")
    row = cur.fetchone()
    con.close()

    if row and row[0]:
        try:
            deadline = datetime.fromisoformat(row[0])
            if datetime.now() > deadline:
                flash("Registration closed. Deadline has passed.")
                try:
                    return redirect(url_for("student_problems"))
                except:
                    return redirect(url_for("index"))
        except:
            pass
    # --- END DEADLINE CHECK ---

    con = db()
    cur = con.cursor()

    # Get problem title + max_teams
    cur.execute("SELECT title, max_teams FROM problems WHERE id=?", (pid,))
    prob = cur.fetchone()
    if not prob:
        con.close()
        flash("Invalid problem selected.")
        return redirect(url_for("index"))

    problem_title = prob[0]
    max_teams = prob[1] if prob[1] else 5

    # ✅ Check team count for this problem
    cur.execute("SELECT COUNT(*) FROM teams WHERE problem_id=?", (pid,))
    already_registered = cur.fetchone()[0]

    # ⚠️ If you want STRICT 1 team per problem, keep this block ON
    # If you want max_teams teams per problem, comment this block
    if already_registered >= 1:
        con.close()
        flash("Registration closed for this project (1 team already registered).")
        try:
            return redirect(url_for("student_problems"))
        except:
            return redirect(url_for("index"))

    # ✅ If you want to allow multiple teams up to max_teams, use this instead:
    # if already_registered >= max_teams:
    #     con.close()
    #     flash(f"Registration closed for this project (Team limit reached: {max_teams}).")
    #     try:
    #         return redirect(url_for("student_problems"))
    #     except:
    #         return redirect(url_for("index"))

    # ---------------- POST: Submit Registration ----------------
    if request.method == "POST":

        # Team basic details
        team_name = request.form.get("team_name", "").strip()

        # Leader details
        leader_name = request.form.get("leader_name", "").strip()
        leader_usn = request.form.get("leader_usn", "").strip().upper()
        leader_email = request.form.get("leader_email", "").strip().lower()
        leader_phone = request.form.get("leader_phone", "").strip()
        leader_department = request.form.get("leader_department", "").strip().upper()
        leader_section = request.form.get("leader_section", "").strip().upper()

        # Basic validations
        if not team_name or not leader_name or not leader_usn or not leader_email:
            con.close()
            flash("Please fill all required Team Leader details.")
            return redirect(request.url)

        # Collect team members (max 5 members)
        members = []
        for i in range(1, 6):
            name = request.form.get(f"member{i}_name", "").strip()
            usn = request.form.get(f"member{i}_usn", "").strip().upper()
            email = request.form.get(f"member{i}_email", "").strip().lower()
            phone = request.form.get(f"member{i}_phone", "").strip()
            dept = request.form.get(f"member{i}_department", "").strip().upper()
            sec = request.form.get(f"member{i}_section", "").strip().upper()

            if usn:  # consider row only if USN entered
                members.append((name, usn, email, phone, dept, sec))

        # ✅ Rule-2: Team size 4–6 including leader
        team_size = 1 + len(members)
        if team_size < 4 or team_size > 6:
            con.close()
            flash("Team size must be between 4 and 6 members (including Team Leader).")
            return redirect(request.url)

        # ✅ Rule-3: At least 1 member from ECE/EEE/ME/CIVIL
        core_branches = ["ECE", "EEE", "ME", "CV", "CIVIL"]
        all_departments = [leader_department] + [m[4] for m in members]

        if not any(d in core_branches for d in all_departments):
            con.close()
            flash("At least 1 member must be from ECE / EEE / ME / Civil branch.")
            return redirect(request.url)

        # ---------------- UNIQUE CHECKS ----------------

        # ✅ Leader USN cannot already be a leader
        cur.execute("SELECT COUNT(*) FROM teams WHERE leader_usn=?", (leader_usn,))
        if cur.fetchone()[0] > 0:
            con.close()
            flash("Team Leader USN already registered in another team.")
            return redirect(request.url)

        # ✅ Leader USN cannot already be a member
        cur.execute("SELECT COUNT(*) FROM team_members WHERE usn=?", (leader_usn,))
        if cur.fetchone()[0] > 0:
            con.close()
            flash("This USN is already registered as a team member in another team.")
            return redirect(request.url)

        # ✅ Leader email cannot already exist (case-insensitive)
        cur.execute("SELECT COUNT(*) FROM teams WHERE LOWER(leader_email)=LOWER(?)", (leader_email,))
        if cur.fetchone()[0] > 0:
            con.close()
            flash("This email is already registered as a Team Leader in another team.")
            return redirect(request.url)

        cur.execute("SELECT COUNT(*) FROM team_members WHERE LOWER(email)=LOWER(?)", (leader_email,))
        if cur.fetchone()[0] > 0:
            con.close()
            flash("This email is already registered as a Team Member in another team.")
            return redirect(request.url)

        # ✅ Check duplicates inside same form (USN/email repeated in team)
        used_usns = set([leader_usn])
        used_emails = set([leader_email])

        for name, usn, email, phone, dept, sec in members:
            if usn in used_usns:
                con.close()
                flash(f"Duplicate USN found in team: {usn}")
                return redirect(request.url)
            used_usns.add(usn)

            if email:
                if email in used_emails:
                    con.close()
                    flash(f"Duplicate Email found in team: {email}")
                    return redirect(request.url)
                used_emails.add(email)

        # ✅ Member USN/email cannot already exist in DB anywhere
        for name, usn, email, phone, dept, sec in members:

            cur.execute("SELECT COUNT(*) FROM team_members WHERE usn=?", (usn,))
            if cur.fetchone()[0] > 0:
                con.close()
                flash(f"Member USN {usn} already registered in another team.")
                return redirect(request.url)

            cur.execute("SELECT COUNT(*) FROM teams WHERE leader_usn=?", (usn,))
            if cur.fetchone()[0] > 0:
                con.close()
                flash(f"Member USN {usn} is already a Team Leader in another team.")
                return redirect(request.url)

            if email:
                cur.execute("SELECT COUNT(*) FROM team_members WHERE LOWER(email)=LOWER(?)", (email,))
                if cur.fetchone()[0] > 0:
                    con.close()
                    flash(f"Member email {email} already registered in another team.")
                    return redirect(request.url)

                cur.execute("SELECT COUNT(*) FROM teams WHERE LOWER(leader_email)=LOWER(?)", (email,))
                if cur.fetchone()[0] > 0:
                    con.close()
                    flash(f"Member email {email} is already registered as a Team Leader in another team.")
                    return redirect(request.url)

        # ---------------- INSERT TEAM ----------------
        cur.execute("""
            INSERT INTO teams(
                team_name,
                leader_name,
                leader_usn,
                leader_email,
                leader_phone,
                leader_department,
                leader_section,
                problem_id,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            team_name,
            leader_name,
            leader_usn,
            leader_email,
            leader_phone,
            leader_department,
            leader_section,
            pid,
            datetime.now()
        ))
    

        team_id = cur.lastrowid

        # Insert members
        for name, usn, email, phone, dept, sec in members:
            cur.execute("""
                INSERT INTO team_members(
                    team_id,
                    member_name,
                    usn,
                    email,
                    phone,
                    department,
                    section
                ) VALUES (?,?,?,?,?,?,?)
            """, (team_id, name, usn, email, phone, dept, sec))

        con.commit()
        con.close()

        flash("Team registered successfully ✅")

        # ✅ Best redirect after registration
        try:
            return redirect(url_for("student_my_project"))
        except:
            return redirect(url_for("student_home"))

    # ---------------- GET: Show registration form ----------------
    con.close()
    return render_template("register.html", title=problem_title)


@app.route("/admin/home")
def admin_home():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM teams")
    teams = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM problems")
    problems = cur.fetchone()[0]

    con.close()

    return render_template(
        "admin_home.html",
        teams=teams,
        problems=problems,
        active_page="home"
    )

@app.route("/admin", methods=["GET","POST"])
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form["u"] == ADMIN_USER and request.form["p"] == ADMIN_PASS:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_home"))
        else:
            flash("Invalid credentials")
    return render_template("admin.html")



@app.route("/admin/upload", methods=["GET","POST"])
def admin_upload():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    if request.method=="POST":
        file=request.files["file"]
        df=pd.read_excel(file)
        con=db(); cur=con.cursor()
        cur.execute("DELETE FROM problems")
        for _,r in df.iterrows():
            cur.execute(
    """INSERT INTO problems(
        year, title, category, difficulty, max_teams,
        problem_description, problem_details, expected_outcome
    ) VALUES (?,?,?,?,5,?,?,?)""",
    (
        r["Year"],
        r["Problem Statement"],
        r["Type"],
        r["Difficulty"],
        r["Problem Description"],
        r["Problem Details"],
        r["Expected Outcome"]
    )
)

        con.commit(); con.close()
        flash("Projects imported successfully")
    return render_template("admin_upload.html",active_page="upload")
@app.route("/admin/teams")
def admin_teams():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    con = db()
    df = pd.read_sql("""
        SELECT
            t.team_name,
            t.department,
            t.section,
            p.title AS problem,
            t.leader_name,
            t.leader_usn,
            t.leader_phone
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        ORDER BY p.title
    """, con)
    con.close()

    return render_template(
        "admin_teams.html",
        tables=df.to_dict(orient="records"), active_page="teams"
    )

@app.route("/dashboard")
def dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    con = db()
    cur = con.cursor()

    # Total teams
    cur.execute("SELECT COUNT(*) FROM teams")
    total_teams = cur.fetchone()[0]

    # Total problems
    cur.execute("SELECT COUNT(*) FROM problems")
    total_problems = cur.fetchone()[0]

    # Teams per department
    cur.execute("""
        SELECT department, COUNT(*) 
        FROM teams 
        GROUP BY department
    """)
    dept_data = cur.fetchall()

    # Hardware vs Software
    cur.execute("""
        SELECT p.category, COUNT(*) 
        FROM teams t 
        JOIN problems p ON t.problem_id = p.id
        GROUP BY p.category
    """)
    type_data = cur.fetchall()

    # Difficulty distribution
    cur.execute("""
        SELECT p.difficulty, COUNT(*) 
        FROM teams t 
        JOIN problems p ON t.problem_id = p.id
        GROUP BY p.difficulty
    """)
    diff_data = cur.fetchall()

    con.close()

    return render_template(
        "dashboard.html",
        total_teams=total_teams,
        total_problems=total_problems,
        dept_data=dept_data,
        type_data=type_data,
        diff_data=diff_data, active_page="dashboard"
    )

@app.route("/export")
@app.route("/export")
def export():
    con = db()
    query = """
    SELECT
        t.team_name,
        t.department,
        t.section,

        t.leader_name,
        t.leader_usn,
        t.leader_email,
        t.leader_phone,

        p.title AS problem_title,
        p.year AS problem_year,

        m.member_name,
        m.usn AS member_usn,
        m.email AS member_email,
        m.phone AS member_phone

    FROM teams t
    JOIN problems p ON t.problem_id = p.id
    LEFT JOIN team_members m ON t.id = m.team_id

    ORDER BY p.title, t.team_name
    """
    df = pd.read_sql(query, con)
    con.close()

    file_name = "rnsit_multidisciplinary_project_registrations.xlsx"
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out successfully")
    return redirect(url_for("admin"))

@app.route("/admin/assignments", methods=["GET", "POST"])
def admin_assignments():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    # ---------------- SAVE MULTIPLE ASSIGNMENTS ----------------
    if request.method == "POST":
        team_ids = request.form.getlist("team_id")  # selected rows
        updated = 0

        for team_id in team_ids:
            faculty_id = request.form.get(f"faculty_{team_id}")
            if faculty_id and faculty_id.strip() != "":
                cur.execute("""
                    INSERT OR REPLACE INTO team_faculty(team_id, faculty_id)
                    VALUES (?, ?)
                """, (team_id, faculty_id))
                updated += 1

        con.commit()
        flash(f"{updated} assignment(s) saved successfully ✅")

    # ---------------- FILTERS (GET) ----------------
    search = request.args.get("search", "").strip().lower()
    dept_filter = request.args.get("dept", "").strip()
    faculty_filter = request.args.get("faculty", "").strip()
    problem_filter = request.args.get("problem", "").strip()

    # Pagination
    page = int(request.args.get("page", 1))
    per_page = 25  # you can change to 50 if needed
    offset = (page - 1) * per_page

    # ---------------- FACULTY LIST ----------------
    cur.execute("SELECT id, name, email, department FROM faculty ORDER BY name")
    faculty_list = cur.fetchall()

    # ---------------- PROBLEM LIST (for dropdown filter) ----------------
    cur.execute("SELECT DISTINCT title FROM problems ORDER BY title")
    problems_list = [r["title"] for r in cur.fetchall()]

    # ---------------- DEPARTMENT LIST ----------------
    departments_list = ["CSE", "CSE-AIML", "CSE-DS", "CSE-CY", "ECE", "EEE", "CV", "ME"]

    # ---------------- BUILD WHERE CLAUSE ----------------
    where = []
    params = []

    if dept_filter:
        where.append("t.leader_department = ?")
        params.append(dept_filter)

    if faculty_filter:
        # Special filter for not assigned
        if faculty_filter == "NOT_ASSIGNED":
            where.append("tf.faculty_id IS NULL")
        else:
            where.append("tf.faculty_id = ?")
            params.append(faculty_filter)

    if problem_filter:
        where.append("p.title = ?")
        params.append(problem_filter)

    if search:
        where.append("""
            (
              LOWER(t.team_name) LIKE ?
              OR LOWER(t.leader_usn) LIKE ?
              OR LOWER(p.title) LIKE ?
            )
        """)
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_sql = " WHERE " + " AND ".join(where) if where else ""

    # ---------------- TOTAL COUNT (for pagination) ----------------
    cur.execute(f"""
        SELECT COUNT(*)
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        LEFT JOIN team_faculty tf ON t.id = tf.team_id
        {where_sql}
    """, params)
    total_rows = cur.fetchone()[0]
    total_pages = max(1, (total_rows + per_page - 1) // per_page)

    # ---------------- GET PAGINATED DATA ----------------
    cur.execute(f"""
        SELECT
            t.id AS team_id,
            t.team_name,
            t.leader_usn,
            t.leader_name,
            t.leader_department,
            p.title AS problem_title,
            p.year AS problem_year,
            tf.faculty_id AS assigned_faculty_id
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        LEFT JOIN team_faculty tf ON t.id = tf.team_id
        {where_sql}
        ORDER BY p.title, t.team_name
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    teams = cur.fetchall()
    con.close()

    return render_template(
        "admin_assignments.html",
        teams=teams,
        faculty_list=faculty_list,
        problems_list=problems_list,
        departments_list=departments_list,
        active_page="assignments",
        # filters for keeping values in UI
        search=search,
        dept_filter=dept_filter,
        faculty_filter=faculty_filter,
        problem_filter=problem_filter,
        # pagination info
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_rows=total_rows,
        rows=rows,
        q=q,
        department=department,
        faculty_id=faculty_id,
        problem_id=problem_id,
    )

@app.route("/admin/export-assignments")
def export_assignments():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    # Read filters from query params (same as assignment page)
    q = request.args.get("q", "").strip()
    department = request.args.get("department", "").strip()
    faculty_id = request.args.get("faculty_id", "").strip()
    problem_id = request.args.get("problem_id", "").strip()
    only_unassigned = request.args.get("only_unassigned", "").strip()  # "1" means only unassigned

    con = db()
    cur = con.cursor()

    base_query = """
    SELECT
        t.id AS team_id,
        t.team_name,
        t.leader_name,
        t.leader_usn,
        t.leader_email,
        t.leader_phone,
        t.leader_department,
        t.leader_section,

        p.title AS problem_title,
        p.year AS problem_year,

        f.name AS faculty_name,
        f.email AS faculty_email,
        f.department AS faculty_department,

        CASE
            WHEN tf.faculty_id IS NULL THEN 'Not Assigned'
            ELSE 'Assigned'
        END AS assignment_status

    FROM teams t
    JOIN problems p ON t.problem_id = p.id
    LEFT JOIN team_faculty tf ON tf.team_id = t.id
    LEFT JOIN faculty f ON f.id = tf.faculty_id
    WHERE 1=1
    """

    params = []

    # Search filter
    if q:
        base_query += """
        AND (
            LOWER(t.team_name) LIKE ?
            OR LOWER(t.leader_name) LIKE ?
            OR LOWER(t.leader_usn) LIKE ?
            OR LOWER(p.title) LIKE ?
        )
        """
        like_q = f"%{q.lower()}%"
        params.extend([like_q, like_q, like_q, like_q])

    # Department filter (leader department)
    if department:
        base_query += " AND t.leader_department = ? "
        params.append(department)

    # Faculty filter
    if faculty_id:
        base_query += " AND tf.faculty_id = ? "
        params.append(faculty_id)

    # Problem filter
    if problem_id:
        base_query += " AND t.problem_id = ? "
        params.append(problem_id)

    # Only unassigned filter
    if only_unassigned == "1":
        base_query += " AND tf.faculty_id IS NULL "

    base_query += """
    ORDER BY assignment_status DESC, faculty_name, p.title, t.team_name
    """

    df = pd.read_sql(base_query, con, params=params)
    con.close()

    # File name based on export type
    if only_unassigned == "1":
        file_name = "faculty_assignments_not_assigned.xlsx"
    else:
        file_name = "faculty_assignments_filtered.xlsx"

    df.to_excel(file_name, index=False)
    return send_file(file_name, as_attachment=True)



if __name__ == "__main__":
    con = db()
    cur = con.cursor()

    # Ensure tables exist
    cur.execute("""
    CREATE TABLE IF NOT EXISTS problems(
        id INTEGER PRIMARY KEY,
        year TEXT,
        title TEXT,
        category TEXT,
        difficulty TEXT,
        max_teams INT,
        problem_description TEXT,
        problem_details TEXT,
        expected_outcome TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS teams(
        id INTEGER PRIMARY KEY,
        team_name TEXT,
        leader_name TEXT,
        leader_usn TEXT UNIQUE,
        leader_email TEXT,
        leader_phone TEXT,
        leader_department TEXT,
        leader_section TEXT,
        problem_id INT
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_members(
        id INTEGER PRIMARY KEY,
        team_id INT,
        member_name TEXT,
        usn TEXT UNIQUE,
        email TEXT,
        phone TEXT,
        department TEXT,
        section TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usn TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # -------- Project Details (Abstract & Objectives) --------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER UNIQUE,
        abstract TEXT,
        objectives TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    """)

    # -------- Weekly Progress --------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        week_no INTEGER,
        progress TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        faculty_remark TEXT,
        status TEXT DEFAULT 'Pending',
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    """)
    # -------- Faculty Table --------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS faculty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        department TEXT
    )
    """)
    # -------- Team – Faculty Mapping --------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_faculty (
        team_id INTEGER UNIQUE,
        faculty_id INTEGER,
        FOREIGN KEY(team_id) REFERENCES teams(id),
        FOREIGN KEY(faculty_id) REFERENCES faculty(id)
    )
    """)
    #add_column_if_not_exists("teams", "abstract", "TEXT")
    #add_column_if_not_exists("teams", "objectives", "TEXT")

    # 🔥 GUARANTEED MIGRATION (THIS IS THE FIX)
    try:
        cur.execute("ALTER TABLE teams ADD COLUMN leader_department TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE teams ADD COLUMN leader_section TEXT")
    except:
        pass
    try:
        cur.execute("ALTER TABLE teams ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except:
        pass

    con.commit()
    con.close()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

