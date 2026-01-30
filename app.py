from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime, timedelta
import pytz

import sqlite3, pandas as pd, os

import os
import io
import pandas as pd
import random, string
from flask import send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash



app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False

DEFAULT_STUDENT_PASSWORD = "RNSIT@2026"
DEFAULT_FACULTY_PASSWORD = "RNSIT@2026"

#app.secret_key = "rnsit_admin_secret_2025"

app.secret_key = "rnsit-multidisciplinary-project-2025-26"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "rnsit_multidisciplinary_project_2025_26_v3.db")


ADMIN_USER = "rnsit_admin"
ADMIN_PASS = "RNSIT@2025"

#def db():
 #   con = sqlite3.connect(DB)
  #  con.row_factory = sqlite3.Row
   # return con

def db():
    con = sqlite3.connect("database.db", check_same_thread=False)
    con.row_factory = sqlite3.Row

    # ✅ Prevent "database is locked"
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA busy_timeout=5000;")

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

@app.route("/debug/team-faculty")
def debug_team_faculty():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM team_faculty")
    rows = cur.fetchall()
    con.close()
    return str([dict(r) for r in rows])


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
    if request.method == "POST":
        usn = request.form["usn"].strip().upper()
        password = request.form["password"]

        con = db()
        cur = con.cursor()

        cur.execute("SELECT * FROM students WHERE usn=?", (usn,))
        student = cur.fetchone()
        con.close()

        if not student:
            flash("Student not found")
            return redirect(request.url)

        if not check_password_hash(student["password_hash"], password):
            flash("Invalid password")
            return redirect(request.url)

        session["student_usn"] = student["usn"]
        session["student_id"] = student["id"]

        # 🔥 Force reset on first login
        if student["must_reset_password"] == 1:
            return redirect(url_for("student_change_password"))

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
        SELECT id, title, category, domain_theme, max_teams
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

    student_usn = session.get("student_usn")

    con = db()
    cur = con.cursor()

    # ---------------- DEADLINE CHECK ----------------
    registration_closed = False
    cur.execute("SELECT value FROM settings WHERE key='registration_deadline'")
    row = cur.fetchone()

    if row and row["value"]:
        try:
            deadline = datetime.fromisoformat(row["value"])
            if datetime.now() > deadline:
                registration_closed = True
        except:
            registration_closed = False

    # ---------------- CHECK IF STUDENT ALREADY IN ANY TEAM ----------------
    already_in_team = False

    # If student is leader in any team
    cur.execute("SELECT COUNT(*) AS cnt FROM teams WHERE leader_usn=?", (student_usn,))
    if cur.fetchone()["cnt"] > 0:
        already_in_team = True
    else:
        # If student is member in any team
        cur.execute("SELECT COUNT(*) AS cnt FROM team_members WHERE usn=?", (student_usn,))
        if cur.fetchone()["cnt"] > 0:
            already_in_team = True

    # ---------------- FETCH PROBLEMS ----------------
    cur.execute("""
        SELECT id, year, title, category, domain_theme, max_teams,
               problem_description, problem_details, expected_outcome
        FROM problems
        ORDER BY year DESC
    """)
    probs = cur.fetchall()

    # ---------------- BUILD DATA (problem + registered_count) ----------------
    data = []
    for p in probs:
        cur.execute("SELECT COUNT(*) AS cnt FROM teams WHERE problem_id=?", (p["id"],))
        registered_count = cur.fetchone()["cnt"]
        data.append((p, registered_count))

    con.close()

    return render_template(
        "student_problems.html",
        data=data,
        registration_closed=registration_closed,
        already_in_team=already_in_team
    )

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

    # 1) First check if student is a leader
    cur.execute("""
        SELECT t.*, p.title AS problem_title, p.year AS problem_year
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.leader_usn=?
    """, (usn,))
    team = cur.fetchone()

    # 2) If not leader, check if student is a member
    if not team:
        cur.execute("""
            SELECT t.*, p.title AS problem_title, p.year AS problem_year
            FROM team_members m
            JOIN teams t ON m.team_id = t.id
            JOIN problems p ON t.problem_id = p.id
            WHERE m.usn=?
        """, (usn,))
        team = cur.fetchone()

    # 3) If still no team found
    if not team:
        con.close()
        flash("You are not registered under any project yet.")
        return redirect(url_for("student_home"))

    team_id = team["id"]

    # 4) Fetch abstract/objectives from project_details table
    cur.execute("""
        SELECT abstract, objectives, tech_stack, methodology, modules, expected_output, project_references
        FROM project_details
        WHERE team_id=?
    """, (team_id,))
    pd = cur.fetchone()

    # 5) Fetch team members
    cur.execute("""
        SELECT member_name, usn, email, phone, department, section
        FROM team_members
        WHERE team_id=?
        ORDER BY id
    """, (team_id,))
    members = cur.fetchall()

    # 6) Get faculty assigned
    cur.execute("""
        SELECT f.name, f.email, f.department
        FROM team_faculty tf
        JOIN faculty f ON tf.faculty_id = f.id
        WHERE tf.team_id=?
    """, (team_id,))
    faculty_row = cur.fetchone()

    # 7) Weekly progress count
    cur.execute("SELECT COUNT(*) FROM weekly_progress WHERE team_id=?", (team_id,))
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

    # Fetch existing details
    cur.execute("SELECT * FROM project_details WHERE team_id=?", (team_id,))
    details = cur.fetchone()

    if request.method == "POST":
        abstract = request.form.get("abstract", "").strip()
        objectives = request.form.get("objectives", "").strip()
        tech_stack = request.form.get("tech_stack", "").strip()
        methodology = request.form.get("methodology", "").strip()
        modules = request.form.get("modules", "").strip()
        expected_output = request.form.get("expected_output", "").strip()
        project_references = request.form.get("project_references", "").strip()

        if details:
            cur.execute("""
                UPDATE project_details
                SET abstract=?, objectives=?, tech_stack=?, methodology=?, modules=?, expected_output=?, project_references=?
                WHERE team_id=?
            """, (
                abstract, objectives, tech_stack, methodology, modules, expected_output, project_references,
                team_id
            ))
        else:
            cur.execute("""
                INSERT INTO project_details(
                    team_id, abstract, objectives, tech_stack, methodology, modules, expected_output, project_references
                )
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                team_id, abstract, objectives, tech_stack, methodology, modules, expected_output, project_references
            ))

        con.commit()
        con.close()
        flash("Project details saved successfully ✅")
        return redirect(url_for("student_project_details"))

    con.close()
    return render_template("student_project_details.html", details=details)
from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io


from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import os
from datetime import datetime

@app.route("/student/synopsis-pdf")
def student_synopsis_pdf():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # -------- Get team (leader/member) --------
    cur.execute("""
        SELECT t.*, 
               p.title AS problem_title,
               p.year AS problem_year,
               p.category AS problem_category,
               p.domain_theme AS domain_theme
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.leader_usn=?
    """, (usn,))
    team = cur.fetchone()

    if not team:
        cur.execute("""
            SELECT t.*, 
                   p.title AS problem_title,
                   p.year AS problem_year,
                   p.category AS problem_category,
                   p.domain_theme AS domain_theme
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

    team_id = team["id"]

    # -------- Members --------
    cur.execute("""
        SELECT member_name, usn, email, phone, department, section
        FROM team_members
        WHERE team_id=?
        ORDER BY id
    """, (team_id,))
    members = cur.fetchall()

    # -------- Faculty --------
    cur.execute("""
        SELECT f.name, f.email, f.department
        FROM team_faculty tf
        JOIN faculty f ON tf.faculty_id = f.id
        WHERE tf.team_id=?
    """, (team_id,))
    faculty = cur.fetchone()

    # -------- Project Details --------
    cur.execute("""
        SELECT abstract, objectives, tech_stack, methodology, modules, dataset_or_inputs, expected_output, project_references
        FROM project_details
        WHERE team_id=?
    """, (team_id,))
    pd = cur.fetchone()

    con.close()

    # -------- Safe getters (sqlite3.Row doesn't support .get) --------
    def safe(row, key, default="-"):
        try:
            val = row[key]
            if val is None or str(val).strip() == "":
                return default
            return str(val)
        except:
            return default

    # -------- PDF Output Path --------
    out_path = f"/tmp/Synopsis_{team_id}.pdf"

    # -------- Styles --------
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=16,
        leading=20,
        alignment=1,
        spaceAfter=10
    )

    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        alignment=1,
        textColor=colors.grey,
        spaceAfter=12
    )

    h_style = ParagraphStyle(
        "HeadingStyle",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=10,
        spaceAfter=6
    )

    normal_style = ParagraphStyle(
        "NormalWrap",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=14
    )

    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=12,
        textColor=colors.grey
    )

    # -------- Document --------
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    story = []

    # ✅ College Header
    story.append(Paragraph("RNS Institute of Technology, Bengaluru", title_style))
    story.append(Paragraph("Department of Computer Science & Engineering", subtitle_style))

    story.append(Paragraph("<b>PROJECT SYNOPSIS</b>", ParagraphStyle(
        "SynTitle",
        parent=styles["Heading1"],
        alignment=1,
        fontSize=14,
        spaceAfter=12
    )))

    # -------- Project Summary Table (wrap title) --------
    project_table_data = [
        ["Team Name", safe(team, "team_name")],
        ["Problem Title", Paragraph(safe(team, "problem_title"), normal_style)],
        ["Year", safe(team, "problem_year")],
        ["Category", safe(team, "problem_category")],
        ["Domain/Theme", safe(team, "domain_theme", "NA")],
    ]

    project_table = Table(project_table_data, colWidths=[120, 360])
    project_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    story.append(project_table)
    story.append(Spacer(1, 12))

    # -------- Team Leader Block --------
    story.append(Paragraph("Team Leader", h_style))
    leader_line = f"""
    <b>{safe(team,'leader_name')}</b> ({safe(team,'leader_usn')})<br/>
    Email: {safe(team,'leader_email')} &nbsp;&nbsp; | &nbsp;&nbsp; Phone: {safe(team,'leader_phone')}<br/>
    Dept: {safe(team,'leader_department')} &nbsp;&nbsp; | &nbsp;&nbsp; Section: {safe(team,'leader_section')}
    """
    story.append(Paragraph(leader_line, normal_style))
    story.append(Spacer(1, 10))

    # -------- Members Table --------
    story.append(Paragraph("Team Members", h_style))

    members_table_data = [["Name", "USN", "Email", "Phone", "Dept", "Section"]]

    # Add leader as first row
    members_table_data.append([
        f"{safe(team,'leader_name')} (Leader)",
        safe(team, "leader_usn"),
        safe(team, "leader_email"),
        safe(team, "leader_phone"),
        safe(team, "leader_department"),
        safe(team, "leader_section"),
    ])

    for m in members:
        members_table_data.append([
            safe(m, "member_name"),
            safe(m, "usn"),
            safe(m, "email"),
            safe(m, "phone"),
            safe(m, "department"),
            safe(m, "section"),
        ])

    members_table = Table(members_table_data, colWidths=[90, 75, 130, 85, 55, 45])
    members_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.black),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(members_table)
    story.append(Spacer(1, 12))

    # -------- Faculty --------
    story.append(Paragraph("Faculty Guide", h_style))
    if faculty:
        story.append(Paragraph(
            f"<b>{safe(faculty,'name')}</b> ({safe(faculty,'department')})<br/>Email: {safe(faculty,'email')}",
            normal_style
        ))
    else:
        story.append(Paragraph("Not assigned yet.", normal_style))

    story.append(Spacer(1, 12))

    # -------- Project Details Sections --------
    def add_section(title, text):
        story.append(Paragraph(title, h_style))
        story.append(Paragraph(text if text.strip() else "Not submitted yet.", normal_style))
        story.append(Spacer(1, 8))

    abstract = safe(pd, "abstract", "")
    objectives = safe(pd, "objectives", "")
    tech_stack = safe(pd, "tech_stack", "")
    methodology = safe(pd, "methodology", "")
    modules = safe(pd, "modules", "")
    #dataset = safe(pd, "dataset_or_inputs", "")
    expected_output = safe(pd, "expected_output", "")
    project_references = safe(pd, "project_references", "")

    add_section("Abstract", abstract)
    add_section("Objectives", objectives)
    add_section("Tech Stack (Software + Hardware)", tech_stack)
    add_section("Methodology / Approach", methodology)
    add_section("Modules / Work Breakdown", modules)
    #add_section("Dataset / Inputs", dataset)
    add_section("Expected Output", expected_output)
    add_section("References", project_references)

    # Footer timestamp
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generated on: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}",
        small_style
    ))

    doc.build(story)

    return send_file(out_path, as_attachment=True)


from datetime import datetime, timedelta, timezone

@app.route("/student/weekly-progress", methods=["GET", "POST"])
def student_weekly_progress():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # ---------------- FIND TEAM ID (leader or member) ----------------
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

    # ---------------- IST TIMEZONE ----------------
    IST = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(IST)

    # ---------------- GET PROJECT START DATE FROM DB ----------------
    cur.execute("SELECT value FROM settings WHERE key='project_start_date'")
    row = cur.fetchone()

    if row and row["value"]:
        try:
            # expected format: YYYY-MM-DD
            start_date = datetime.strptime(row["value"], "%Y-%m-%d")
            PROJECT_START_DATE = IST.localize(datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0))
        except:
            # fallback if format wrong
            PROJECT_START_DATE = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # fallback if admin didn't set
        PROJECT_START_DATE = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)

    # ---------------- AUTO WEEK CALCULATION (Week 1..16) ----------------
    days_since_start = (now_ist.date() - PROJECT_START_DATE.date()).days
    auto_week_no = (days_since_start // 7) + 1

    if auto_week_no < 1:
        auto_week_no = 1

    TOTAL_WEEKS = 16
    if auto_week_no > TOTAL_WEEKS:
        auto_week_no = TOTAL_WEEKS

    # ---------------- CURRENT WEEK DEADLINE (Saturday 11:59 PM IST) ----------------
    # Each week starts from PROJECT_START_DATE + (week_no-1)*7 days
    current_week_start = PROJECT_START_DATE + timedelta(days=(auto_week_no - 1) * 7)

    # Saturday = week_start + 5 days
    deadline_dt = (current_week_start + timedelta(days=5)).replace(
        hour=23, minute=59, second=0, microsecond=0
    )

    # ---------------- FILTERS ----------------
    show = request.args.get("show", "all")  # all / late / reviewed / pending

    # ---------------- POST: SUBMIT WEEKLY PROGRESS ----------------
    if request.method == "POST":
        progress = request.form.get("progress", "").strip()

        if not progress:
            flash("Progress cannot be empty.")
            con.close()
            return redirect(request.url)

        # Prevent duplicate submission for same week
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM weekly_progress
            WHERE team_id=? AND week_no=?
        """, (team_id, auto_week_no))
        if cur.fetchone()["cnt"] > 0:
            flash(f"Week {auto_week_no} progress already submitted.")
            con.close()
            return redirect(url_for("student_weekly_progress"))

        cur.execute("""
            INSERT INTO weekly_progress(team_id, week_no, progress, submitted_at, status)
            VALUES (?,?,?,?,?)
        """, (team_id, auto_week_no, progress, now_ist.strftime("%Y-%m-%d %H:%M:%S"), "Pending"))

        con.commit()
        flash(f"Weekly progress submitted for Week {auto_week_no} ✅")
        con.close()
        return redirect(url_for("student_weekly_progress"))

    # ---------------- FETCH ALL PROGRESS ----------------
    cur.execute("""
        SELECT *
        FROM weekly_progress
        WHERE team_id=?
        ORDER BY week_no DESC
    """, (team_id,))
    rows = cur.fetchall()
    con.close()

    progress_list = []

    for r in rows:
        submitted_raw = r["submitted_at"]
        submitted_dt = None

        # parse datetime safely
        try:
            submitted_dt = datetime.strptime(submitted_raw, "%Y-%m-%d %H:%M:%S")
            submitted_dt = IST.localize(submitted_dt)
        except:
            submitted_dt = None

        submitted_at_ist = submitted_raw
        if submitted_dt:
            submitted_at_ist = submitted_dt.strftime("%d-%m-%Y %I:%M %p (IST)")

        # deadline for that specific week
        week_start = PROJECT_START_DATE + timedelta(days=(r["week_no"] - 1) * 7)
        week_deadline = (week_start + timedelta(days=5)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        deadline_at = week_deadline.strftime("%d-%m-%Y %I:%M %p (IST)")

        is_late = False
        if submitted_dt:
            is_late = submitted_dt > week_deadline

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

    # ---------------- APPLY FILTERS ----------------
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


@app.route("/student/weekly-progress/edit/<int:progress_id>", methods=["GET", "POST"])
def student_edit_weekly_progress(progress_id):
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # Find student's team_id (leader OR member)
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

    # Fetch progress entry
    cur.execute("""
        SELECT * FROM weekly_progress
        WHERE id=? AND team_id=?
    """, (progress_id, team_id))
    progress_row = cur.fetchone()

    if not progress_row:
        con.close()
        flash("Progress record not found.")
        return redirect(url_for("student_weekly_progress"))

    # Only allow edit if Pending
    if progress_row["status"] != "Pending":
        con.close()
        flash("You cannot edit this progress after faculty review.")
        return redirect(url_for("student_weekly_progress"))

    # POST update
    if request.method == "POST":
        new_progress = request.form.get("progress", "").strip()

        if not new_progress:
            flash("Progress cannot be empty.")
            con.close()
            return redirect(request.url)

        cur.execute("""
            UPDATE weekly_progress
            SET progress=?, submitted_at=CURRENT_TIMESTAMP
            WHERE id=? AND team_id=?
        """, (new_progress, progress_id, team_id))

        con.commit()
        con.close()

        flash("Weekly progress updated successfully ✅")
        return redirect(url_for("student_weekly_progress"))

    con.close()
    return render_template("student_edit_weekly_progress.html", p=progress_row)


@app.route("/faculty/login", methods=["GET", "POST"])
def faculty_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        con = db()
        cur = con.cursor()
        cur.execute("SELECT * FROM faculty WHERE email=?", (email,))
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

        # ✅ Mandatory reset on first login
        try:
            if faculty["must_reset_password"] == 1:
                return redirect(url_for("faculty_change_password"))
        except:
            # If column not present for some reason, allow dashboard
            pass

        return redirect(url_for("faculty_dashboard"))

    return render_template("faculty_login.html")
@app.route("/faculty/change-password", methods=["GET", "POST"])
def faculty_change_password():
    if not session.get("faculty_id"):
        return redirect(url_for("faculty_login"))

    faculty_id = session["faculty_id"]

    if request.method == "POST":
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password or len(new_password) < 6:
            flash("New password must be at least 6 characters.")
            return redirect(request.url)

        if new_password != confirm_password:
            flash("New password and confirm password do not match.")
            return redirect(request.url)

        con = db()
        cur = con.cursor()

        cur.execute("SELECT * FROM faculty WHERE id=?", (faculty_id,))
        faculty = cur.fetchone()

        if not faculty:
            con.close()
            flash("Faculty not found.")
            return redirect(url_for("faculty_login"))

        if not check_password_hash(faculty["password_hash"], current_password):
            con.close()
            flash("Current password is incorrect.")
            return redirect(request.url)

        new_hash = generate_password_hash(new_password)

        cur.execute("""
            UPDATE faculty
            SET password_hash=?, must_reset_password=0, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (new_hash, faculty_id))

        con.commit()
        con.close()

        flash("Password updated successfully ✅")
        return redirect(url_for("faculty_dashboard"))

    return render_template("faculty_change_password.html")


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

    # 🔐 Security check: faculty can only access assigned team
    cur.execute("""
        SELECT COUNT(*)
        FROM team_faculty
        WHERE team_id=? AND faculty_id=?
    """, (team_id, faculty_id))

    if cur.fetchone()[0] == 0:
        con.close()
        flash("Access denied")
        return redirect(url_for("faculty_dashboard"))

    # ---------------- TEAM + PROBLEM INFO ----------------
    cur.execute("""
        SELECT
            t.id,
            t.team_name,
            t.leader_name,
            t.leader_usn,
            t.leader_email,
            t.leader_phone,
            t.leader_department,
            t.leader_section,
            p.title AS problem_title,
            p.year AS problem_year,
            p.problem_description,
            p.problem_details,
            p.expected_outcome
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.id=?
    """, (team_id,))
    team = cur.fetchone()

    # ---------------- TEAM MEMBERS ----------------
    cur.execute("""
        SELECT member_name, usn, email, phone, department, section
        FROM team_members
        WHERE team_id=?
        ORDER BY id
    """, (team_id,))
    members = cur.fetchall()

    # ---------------- PROJECT DETAILS ----------------
    cur.execute("""
        SELECT abstract, objectives, tech_stack, methodology, modules,
               dataset_or_inputs, expected_output
        FROM project_details
        WHERE team_id=?
    """, (team_id,))
    project_details = cur.fetchone()

    # ---------------- WEEKLY PROGRESS ----------------
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
        members=members,
        project_details=project_details,
        progress_list=progress_list
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

@app.route("/admin/faculty/template")
def admin_faculty_template():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    df = pd.DataFrame(columns=["Name", "Email", "Department"])
    file_name = "faculty_bulk_upload_template.xlsx"
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)

import random
import string



def generate_random_password(length=8):
    chars = string.ascii_letters + string.digits + "@#"
    return "".join(random.choice(chars) for _ in range(length))


@app.route("/admin/faculty-management", methods=["GET", "POST"])
def admin_faculty_management():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    # ---------------- GET PARAMS ----------------
    search = request.args.get("search", "").strip().lower()
    dept_filter = request.args.get("dept", "").strip()

    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    departments_list = ["CSE", "CSE-AIML", "CSE-DS", "CSE-CY", "ECE", "EEE", "CV", "ME"]

    # ---------------- DOWNLOAD TEMPLATE ----------------
    if request.args.get("download") == "template":
        template_df = pd.DataFrame(columns=["Name", "Email", "Department"])
        file_path = "faculty_upload_template.xlsx"
        template_df.to_excel(file_path, index=False)
        con.close()
        return send_file(file_path, as_attachment=True)

    # ---------------- EXPORT FACULTY LIST (FILTERED) ----------------
    if request.args.get("export") == "excel":
        where = []
        params = []

        if dept_filter:
            where.append("department=?")
            params.append(dept_filter)

        if search:
            where.append("(LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(department) LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where_sql = " WHERE " + " AND ".join(where) if where else ""

        cur.execute(f"""
            SELECT id, name, email, department
            FROM faculty
            {where_sql}
            ORDER BY name
        """, params)
        rows = cur.fetchall()

        df = pd.DataFrame(rows, columns=["id", "name", "email", "department"])
        file_path = "faculty_list_export.xlsx"
        df.to_excel(file_path, index=False)

        con.close()
        return send_file(file_path, as_attachment=True)

    # ---------------- POST ACTIONS ----------------
    if request.method == "POST":
        action = request.form.get("action", "").strip()

        # ---------- BULK UPLOAD ----------
        if action == "bulk_upload":
            file = request.files.get("file")
            if not file:
                flash("Please upload an Excel file.")
                con.close()
                return redirect(request.url)

            try:
                df = pd.read_excel(file)
            except:
                flash("Invalid file. Please upload a valid Excel file.")
                con.close()
                return redirect(request.url)

            required_cols = ["Name", "Email", "Department"]
            for col in required_cols:
                if col not in df.columns:
                    flash(f"Missing column: {col}")
                    con.close()
                    return redirect(request.url)

            created = []
            skipped = []

            for _, r in df.iterrows():
                name = str(r["Name"]).strip()
                email = str(r["Email"]).strip().lower()
                dept = str(r["Department"]).strip()

                if not name or not email or not dept:
                    skipped.append((name, email, dept, "Missing data"))
                    continue

                cur.execute("SELECT COUNT(*) FROM faculty WHERE email=?", (email,))
                if cur.fetchone()[0] > 0:
                    skipped.append((name, email, dept, "Already exists"))
                    continue

                raw_password = DEFAULT_FACULTY_PASSWORD
                password_hash = generate_password_hash(raw_password)

                cur.execute("""
                    INSERT INTO faculty(name, email, password_hash, department, must_reset_password)
                    VALUES (?,?,?,?,1)
                """, (name, email, password_hash, dept))


                created.append((name, email, dept, raw_password))

            con.commit()

            if created:
                out_df = pd.DataFrame(created, columns=["Name", "Email", "Department", "Generated Password"])
                out_file = "faculty_generated_passwords.xlsx"
                out_df.to_excel(out_file, index=False)

                flash(f"Bulk upload completed ✅ Created: {len(created)}, Skipped: {len(skipped)}")
                con.close()
                return send_file(out_file, as_attachment=True)

            flash("No new faculty created. All were skipped.")
            con.close()
            return redirect(url_for("admin_faculty_management"))

        # ---------- MANUAL ADD ----------
        if action == "manual_add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            department = request.form.get("department", "").strip()
            password = request.form.get("password", "").strip()

            if not name or not email or not department:
                flash("Please fill Name, Email and Department.")
                con.close()
                return redirect(url_for("admin_faculty_management"))
            
            
            if not password:
                password = DEFAULT_FACULTY_PASSWORD

            password_hash = generate_password_hash(password)

            try:
                cur.execute("""
                    INSERT INTO faculty(name, email, password_hash, department, must_reset_password)
                    VALUES (?,?,?,?,1)
                """, (name, email, password_hash, department))
                con.commit()
                flash(f"Faculty created successfully ✅ Password: {password}")
            except:
                flash("Faculty email already exists ❌")

            con.close()
            return redirect(url_for("admin_faculty_management"))

        # ---------- RESET PASSWORD (SINGLE) ----------
        if action == "reset_password":
            fid = request.form.get("fid", "").strip()
            if not fid:
                flash("Invalid faculty selection.")
                con.close()
                return redirect(url_for("admin_faculty_management"))

            #raw_password = generate_random_password(10)
            password_hash = generate_password_hash(DEFAULT_FACULTY_PASSWORD)

            cur.execute("""
                UPDATE faculty
                SET password_hash=?, must_reset_password=1, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (password_hash, fid))

            con.commit()
            flash("Password reset to default (RNSIT@2026) ✅")
            con.close()
            return redirect(url_for("admin_faculty_management"))
        
        # ---------- EDIT FACULTY ----------
        if action == "edit_faculty":
            fid = request.form.get("fid", "").strip()
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            department = request.form.get("department", "").strip()

            if not fid or not name or not email or not department:
                flash("All fields are required to update faculty.")
                con.close()
                return redirect(url_for("admin_faculty_management"))

            # check duplicate email (but allow same faculty's email)
            cur.execute("SELECT id FROM faculty WHERE email=?", (email,))
            row = cur.fetchone()
            if row and str(row["id"]) != str(fid):
                flash("This email is already used by another faculty ❌")
                con.close()
                return redirect(url_for("admin_faculty_management"))

            cur.execute("""
                UPDATE faculty
                SET name=?, email=?, department=?
                WHERE id=?
            """, (name, email, department, fid))

            con.commit()
            flash("Faculty updated successfully ✅")
            con.close()
            return redirect(url_for("admin_faculty_management"))

        # ---------- BULK RESET PASSWORD (VISIBLE FILTERED) ----------
        if action == "bulk_reset_password":
            faculty_ids = request.form.getlist("faculty_id")
            if not faculty_ids:
                flash("Please select at least 1 faculty to reset password.")
                con.close()
                return redirect(url_for("admin_faculty_management"))

            reset_list = []
            for fid in faculty_ids:
                raw_password = generate_random_password(10)
                password_hash = generate_password_hash(raw_password)

                cur.execute("SELECT name, email, department FROM faculty WHERE id=?", (fid,))
                f = cur.fetchone()
                if not f:
                    continue

                cur.execute("UPDATE faculty SET password_hash=? WHERE id=?", (password_hash, fid))
                reset_list.append((f["name"], f["email"], f["department"], raw_password))

            con.commit()

            if reset_list:
                out_df = pd.DataFrame(reset_list, columns=["Name", "Email", "Department", "New Password"])
                out_file = "faculty_reset_passwords.xlsx"
                out_df.to_excel(out_file, index=False)

                flash(f"Bulk password reset completed ✅ Total: {len(reset_list)}")
                con.close()
                return send_file(out_file, as_attachment=True)

            flash("No passwords were reset.")
            con.close()
            return redirect(url_for("admin_faculty_management"))

    # ---------------- FACULTY LIST (FILTER + PAGINATION) ----------------
    where = []
    params = []

    if dept_filter:
        where.append("department=?")
        params.append(dept_filter)

    if search:
        where.append("(LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(department) LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_sql = " WHERE " + " AND ".join(where) if where else ""

    cur.execute(f"SELECT COUNT(*) FROM faculty {where_sql}", params)
    total_rows = cur.fetchone()[0]
    total_pages = max(1, (total_rows + per_page - 1) // per_page)

    cur.execute(f"""
        SELECT id, name, email, department
        FROM faculty
        {where_sql}
        ORDER BY name
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    faculty = cur.fetchall()

    con.close()

    return render_template(
        "admin_faculty_management.html",
        faculty=faculty,
        active_page="faculty",
        departments_list=departments_list,
        search=search,
        dept_filter=dept_filter,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_rows=total_rows
    )

@app.route("/admin/faculty/bulk-upload", methods=["GET", "POST"])
def admin_faculty_bulk_upload():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            flash("Please upload an Excel file.")
            return redirect(request.url)

        try:
            df = pd.read_excel(file)
        except:
            flash("Invalid file. Please upload a valid Excel file.")
            return redirect(request.url)

        required_cols = ["Name", "Email", "Department"]
        for col in required_cols:
            if col not in df.columns:
                flash(f"Missing column: {col}")
                return redirect(request.url)

        con = db()
        cur = con.cursor()

        created = []
        skipped = []

        for _, r in df.iterrows():
            name = str(r["Name"]).strip()
            email = str(r["Email"]).strip().lower()
            dept = str(r["Department"]).strip()

            if not name or not email or not dept:
                skipped.append((name, email, dept, "Missing data"))
                continue

            # check duplicate
            cur.execute("SELECT COUNT(*) FROM faculty WHERE email=?", (email,))
            if cur.fetchone()[0] > 0:
                skipped.append((name, email, dept, "Already exists"))
                continue

            # generate password
            raw_password = generate_random_password(10)
            password_hash = generate_password_hash(raw_password)

            cur.execute("""
                INSERT INTO faculty(name, email, password_hash, department)
                VALUES (?,?,?,?)
            """, (name, email, password_hash, dept))

            created.append((name, email, dept, raw_password))

        con.commit()
        con.close()

        # Save generated passwords to Excel for admin download
        if created:
            out_df = pd.DataFrame(created, columns=["Name", "Email", "Department", "Generated Password"])
            out_file = "faculty_generated_passwords.xlsx"
            out_df.to_excel(out_file, index=False)

            flash(f"Bulk upload completed ✅ Created: {len(created)}, Skipped: {len(skipped)}")
            return send_file(out_file, as_attachment=True)

        flash("No new faculty created. All were skipped.")
        return redirect(request.url)

    return render_template("admin_faculty_bulk_upload.html", active_page="faculty")

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

    cur.execute("DELETE FROM team_faculty WHERE faculty_id=?", (fid,))
    cur.execute("DELETE FROM faculty WHERE id=?", (fid,))

    con.commit()
    con.close()

    flash("Faculty deleted successfully ✅")
    return redirect(url_for("admin_faculty_management"))

@app.route("/admin/students", methods=["GET", "POST"])
def admin_students():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    departments_list = ["CSE", "CSE-AIML", "CSE-DS", "CSE-CY", "ECE", "EEE", "CV", "ME"]

    # ---------------- TEMPLATE DOWNLOAD ----------------
    if request.method == "GET" and request.args.get("download") == "template":
        template_df = pd.DataFrame(columns=["USN", "Email", "Name", "Department", "Section"])
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            template_df.to_excel(writer, index=False, sheet_name="Students")
        out.seek(0)

        return send_file(
            out,
            as_attachment=True,
            download_name="student_upload_template.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # ---------------- EXPORT EXCEL ----------------
    if request.method == "GET" and request.args.get("export") == "excel":
        search = request.args.get("search", "").strip().lower()
        dept_filter = request.args.get("dept", "").strip()

        where = []
        params = []

        if dept_filter:
            where.append("department=?")
            params.append(dept_filter)

        if search:
            where.append("""
                (
                  LOWER(usn) LIKE ?
                  OR LOWER(email) LIKE ?
                  OR LOWER(COALESCE(name,'')) LIKE ?
                )
            """)
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where_sql = " WHERE " + " AND ".join(where) if where else ""

        cur.execute(f"""
            SELECT id, usn, email, name, department, section, must_reset_password, created_at
            FROM students
            {where_sql}
            ORDER BY created_at DESC
        """, params)
        rows = cur.fetchall()

        export_data = []
        for r in rows:
            export_data.append({
                "USN": r["usn"],
                "Email": r["email"],
                "Name": r["name"] or "",
                "Department": r["department"] or "",
                "Section": r["section"] or "",
                "Must Reset Password": "YES" if r["must_reset_password"] == 1 else "NO",
                "Created At": r["created_at"]
            })

        df = pd.DataFrame(export_data)
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Students")
        out.seek(0)

        con.close()
        return send_file(
            out,
            as_attachment=True,
            download_name="students_export.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # ---------------- POST ACTIONS ----------------
    if request.method == "POST":
        action = request.form.get("action")

        # ---- BULK UPLOAD ----
        if action == "bulk_upload":
            file = request.files.get("file")
            if not file:
                flash("Please upload an Excel file.")
                con.close()
                return redirect(request.url)

            try:
                df = pd.read_excel(file)
            except:
                flash("Invalid file. Please upload a valid Excel file.")
                con.close()
                return redirect(request.url)

            required_cols = ["USN", "Email", "Name", "Department", "Section"]
            for col in required_cols:
                if col not in df.columns:
                    flash(f"Missing column: {col}")
                    con.close()
                    return redirect(request.url)

            created = 0
            skipped = 0

            for _, r in df.iterrows():
                usn = str(r["USN"]).strip().upper()
                email = str(r["Email"]).strip().lower()
                name = str(r["Name"]).strip()
                dept = str(r["Department"]).strip()
                sec = str(r["Section"]).strip()

                if not usn or not email:
                    skipped += 1
                    continue

                # prevent duplicates
                cur.execute("SELECT COUNT(*) AS cnt FROM students WHERE usn=? OR email=?", (usn, email))
                if cur.fetchone()["cnt"] > 0:
                    skipped += 1
                    continue

                password_hash = generate_password_hash(DEFAULT_STUDENT_PASSWORD)

                cur.execute("""
                    INSERT INTO students(usn, email, password_hash, name, department, section, must_reset_password)
                    VALUES (?,?,?,?,?,?,1)
                """, (usn, email, password_hash, name, dept, sec))

                created += 1

            con.commit()
            flash(f"Bulk upload done ✅ Created: {created}, Skipped: {skipped}")

        # ---- MANUAL ADD ----
        elif action == "manual_add":
            usn = request.form.get("usn", "").strip().upper()
            email = request.form.get("email", "").strip().lower()
            name = request.form.get("name", "").strip()
            dept = request.form.get("department", "").strip()
            sec = request.form.get("section", "").strip()

            if not usn or not email:
                flash("USN and Email are required.")
                con.close()
                return redirect(request.url)

            cur.execute("SELECT COUNT(*) AS cnt FROM students WHERE usn=? OR email=?", (usn, email))
            if cur.fetchone()["cnt"] > 0:
                flash("Student already exists (USN/Email duplicate).")
                con.close()
                return redirect(request.url)

            password_hash = generate_password_hash(DEFAULT_STUDENT_PASSWORD)

            cur.execute("""
                INSERT INTO students(usn, email, password_hash, name, department, section, must_reset_password)
                VALUES (?,?,?,?,?,?,1)
            """, (usn, email, password_hash, name, dept, sec))

            con.commit()
            flash("Student created successfully ✅")

        # ---- RESET PASSWORD SINGLE ----
        elif action == "reset_password":
            sid = request.form.get("sid")
            if sid:
                password_hash = generate_password_hash(DEFAULT_STUDENT_PASSWORD)
                cur.execute("""
                    UPDATE students
                    SET password_hash=?, must_reset_password=1, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                """, (password_hash, sid))
                con.commit()
                flash("Password reset to default (RNSIT@2026) ✅")

        # ---- BULK RESET PASSWORD ----
        elif action == "bulk_reset_password":
            ids = request.form.getlist("student_id")
            if not ids:
                flash("Please select at least 1 student.")
            else:
                password_hash = generate_password_hash(DEFAULT_STUDENT_PASSWORD)
                for sid in ids:
                    cur.execute("""
                        UPDATE students
                        SET password_hash=?, must_reset_password=1, updated_at=CURRENT_TIMESTAMP
                        WHERE id=?
                    """, (password_hash, sid))
                con.commit()
                flash(f"Reset password for {len(ids)} student(s) ✅")

        # ---- DELETE STUDENT ----
        elif action == "delete_student":
            sid = request.form.get("sid")
            if sid:
                cur.execute("DELETE FROM students WHERE id=?", (sid,))
                con.commit()
                flash("Student deleted successfully ✅")

        con.close()
        return redirect(url_for("admin_students"))

    # ---------------- FILTERS (GET LIST) ----------------
    search = request.args.get("search", "").strip().lower()
    dept_filter = request.args.get("dept", "").strip()

    page = int(request.args.get("page", 1))
    per_page = 25
    offset = (page - 1) * per_page

    where = []
    params = []

    if dept_filter:
        where.append("department=?")
        params.append(dept_filter)

    if search:
        where.append("""
            (
              LOWER(usn) LIKE ?
              OR LOWER(email) LIKE ?
              OR LOWER(COALESCE(name,'')) LIKE ?
            )
        """)
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_sql = " WHERE " + " AND ".join(where) if where else ""

    # total count
    cur.execute(f"SELECT COUNT(*) AS cnt FROM students {where_sql}", params)
    total_rows = cur.fetchone()["cnt"]
    total_pages = max(1, (total_rows + per_page - 1) // per_page)

    cur.execute(f"""
        SELECT id, usn, email, name, department, section, must_reset_password, created_at
        FROM students
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    students = cur.fetchall()
    con.close()

    return render_template(
        "admin_students.html",
        students=students,
        departments_list=departments_list,
        search=search,
        dept_filter=dept_filter,
        page=page,
        total_pages=total_pages,
        total_rows=total_rows,
        active_page="students"
    )



@app.route("/student/change-password", methods=["GET", "POST"])
def student_change_password():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not new_password or len(new_password) < 6:
            flash("New password must be at least 6 characters.")
            return redirect(request.url)

        if new_password != confirm_password:
            flash("New password and confirm password do not match.")
            return redirect(request.url)

        con = db()
        cur = con.cursor()

        cur.execute("SELECT * FROM students WHERE usn=?", (usn,))
        student = cur.fetchone()

        if not student:
            con.close()
            flash("Student not found.")
            return redirect(url_for("student_login"))

        if not check_password_hash(student["password_hash"], current_password):
            con.close()
            flash("Current password is incorrect.")
            return redirect(request.url)

        new_hash = generate_password_hash(new_password)

        cur.execute("""
            UPDATE students
            SET password_hash=?, must_reset_password=0, updated_at=CURRENT_TIMESTAMP
            WHERE usn=?
        """, (new_hash, usn))

        con.commit()
        con.close()

        flash("Password updated successfully ✅")
        return redirect(url_for("student_home"))

    return render_template("student_change_password.html")

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

@app.route("/admin/project-settings", methods=["GET", "POST"])
def admin_project_settings():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    if request.method == "POST":
        project_start_date = request.form.get("project_start_date", "").strip()
        registration_deadline = request.form.get("registration_deadline", "").strip()
        total_weeks = request.form.get("total_weeks", "16").strip()

        # Save values into settings table
        if project_start_date:
            cur.execute("""
                INSERT OR REPLACE INTO settings(key, value)
                VALUES (?, ?)
            """, ("project_start_date", project_start_date))

        if registration_deadline:
            cur.execute("""
                INSERT OR REPLACE INTO settings(key, value)
                VALUES (?, ?)
            """, ("registration_deadline", registration_deadline))

        if total_weeks:
            cur.execute("""
                INSERT OR REPLACE INTO settings(key, value)
                VALUES (?, ?)
            """, ("total_weeks", total_weeks))

        con.commit()
        flash("Project settings saved successfully ✅")
        return redirect(url_for("admin_project_settings"))

    # Fetch existing values
    def get_setting(key, default=""):
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row and row["value"] else default

    project_start_date = get_setting("project_start_date", "")
    registration_deadline = get_setting("registration_deadline", "")
    total_weeks = get_setting("total_weeks", "16")

    con.close()

    return render_template(
        "admin_project_settings.html",
        active_page="project_settings",
        project_start_date=project_start_date,
        registration_deadline=registration_deadline,
        total_weeks=total_weeks
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
    SELECT id, year, title, category, domain_theme, max_teams,
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

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        email = request.form["u"].strip().lower()
        password = request.form["p"]

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT * FROM admins WHERE email=?
        """, (email,))
        admin = cur.fetchone()
        con.close()

        if not admin:
            flash("Invalid credentials")
            return redirect(request.url)

        if not check_password_hash(admin["password_hash"], password):
            flash("Invalid credentials")
            return redirect(request.url)

        # ✅ SESSION SETUP
        session["admin_logged_in"] = True
        session["admin_id"] = admin["id"]
        session["admin_role"] = admin["role"]              # super_admin / admin
        session["admin_department"] = admin["department"]  # None or dept

        # Force password reset if needed
        if admin["must_reset_password"]:
            return redirect(url_for("admin_change_password"))

        return redirect(url_for("admin_home"))

    return render_template("admin.html")
@app.route("/admin/admin-management", methods=["GET", "POST"])
def admin_management():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    # 🔐 Only super admin allowed
    if session.get("admin_role") != "super_admin":
        flash("Access denied")
        return redirect(url_for("admin_home"))

    con = db()
    cur = con.cursor()

    departments_list = ["CSE", "CSE-AIML", "CSE-DS", "CSE-CY", "ECE", "EEE", "ME", "CV"]

    # ---------------- CREATE ADMIN ----------------
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "").strip()
        role = request.form.get("role", "").strip()

        if not name or not email or not role:
            flash("All fields are required")
            con.close()
            return redirect(request.url)

        if role == "admin" and not department:
            flash("Department is required for Department Admin")
            con.close()
            return redirect(request.url)

        password = "RNSIT@2026"
        password_hash = generate_password_hash(password)

        try:
            cur.execute("""
                INSERT INTO admins
                (name, email, password_hash, role, department, must_reset_password)
                VALUES (?,?,?,?,?,1)
            """, (name, email, password_hash, role, department if role=="admin" else None))

            con.commit()
            flash(f"Admin created successfully ✅ Default password: {password}")
        except:
            flash("Email already exists ❌")

        con.close()
        return redirect(request.url)

    # ---------------- LIST ADMINS ----------------
    cur.execute("""
        SELECT id, name, email, role, department, created_at
        FROM admins
        ORDER BY role DESC, department, name
    """)
    admins = cur.fetchall()

    con.close()

    return render_template(
        "admin_management.html",
        admins=admins,
        departments_list=departments_list,
        active_page="admins"
    )


@app.route("/admin/upload", methods=["GET", "POST"])
def admin_upload():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            flash("Please upload an Excel file.")
            return redirect(request.url)

        try:
            df = pd.read_excel(file)
        except:
            flash("Invalid file. Please upload a valid Excel file.")
            return redirect(request.url)

        # ✅ Required columns in your NEW excel
        required_cols = [
            "Year",
            "Problem Statement",
            "Type",
            "Domain/Theme",
            "Problem Description",
            "Problem Details",
            "Expected Outcome"
        ]

        for col in required_cols:
            if col not in df.columns:
                flash(f"Missing column in Excel: {col}")
                return redirect(request.url)

        con = db()
        cur = con.cursor()

        # ⚠️ If you want to replace everything each time upload happens
        cur.execute("DELETE FROM problems")

        for _, r in df.iterrows():
            year = str(r["Year"]).strip()
            title = str(r["Problem Statement"]).strip()
            category = str(r["Type"]).strip()
            domain_theme = str(r["Domain/Theme"]).strip()

            problem_description = str(r["Problem Description"]).strip()
            problem_details = str(r["Problem Details"]).strip()
            expected_outcome = str(r["Expected Outcome"]).strip()

            # Insert into DB
            cur.execute("""
                INSERT INTO problems(
                    year, title, category, domain_theme, max_teams,
                    problem_description, problem_details, expected_outcome
                )
                VALUES (?,?,?,?,1,?,?,?)
            """, (
                year,
                title,
                category,
                domain_theme,
                problem_description,
                problem_details,
                expected_outcome
            ))

        con.commit()
        con.close()

        flash("Projects imported successfully ✅ (Domain/Theme included)")
        return redirect(url_for("admin_upload"))

    return render_template("admin_upload.html", active_page="upload")

@app.route("/admin/teams")
def admin_teams():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    # ---------------- FETCH TEAMS + PROBLEM + FACULTY ----------------
    cur.execute("""
        SELECT
            t.id AS team_id,
            t.team_name,
            t.leader_department,
            t.leader_section,
            p.title AS problem_title,
            t.leader_name,
            t.leader_usn,
            t.leader_phone,

            f.name AS faculty_name,
            f.email AS faculty_email,
            f.department AS faculty_department
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        LEFT JOIN team_faculty tf ON t.id = tf.team_id
        LEFT JOIN faculty f ON tf.faculty_id = f.id
        ORDER BY p.title, t.team_name
    """)
    teams = cur.fetchall()

    # ---------------- FETCH MEMBERS FOR ALL TEAMS ----------------
    cur.execute("""
        SELECT team_id, member_name, usn, department
        FROM team_members
        ORDER BY team_id, id
    """)
    members_rows = cur.fetchall()

    con.close()

    # Build mapping team_id -> list of members
    members_map = {}
    for m in members_rows:
        tid = m["team_id"]
        members_map.setdefault(tid, []).append({
            "member_name": m["member_name"],
            "usn": m["usn"],
            "department": m["department"]
        })

    # Final rows for UI + Excel
    rows = []
    for t in teams:
        tid = t["team_id"]

        # Format members as single string (for table + excel)
        member_list = members_map.get(tid, [])
        if member_list:
            members_text = " | ".join([
                f"{x['member_name']} ({x['usn']}, {x['department']})"
                for x in member_list
            ])
        else:
            members_text = "-"

        # Faculty details
        if t["faculty_name"]:
            faculty_text = f"{t['faculty_name']} ({t['faculty_department']}) - {t['faculty_email']}"
        else:
            faculty_text = "Not Assigned"

        rows.append({
            "team_id": tid,
            "team_name": t["team_name"],
            "leader_department": t["leader_department"],
            "leader_section": t["leader_section"],
            "problem_title": t["problem_title"],
            "leader_name": t["leader_name"],
            "leader_usn": t["leader_usn"],
            "leader_phone": t["leader_phone"],
            "members_text": members_text,
            "faculty_text": faculty_text
        })

    return render_template(
        "admin_teams.html",
        rows=rows,
        active_page="teams"
    )
@app.route("/admin/export-teams")
def admin_export_teams():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT
            t.id AS team_id,
            t.team_name,
            t.leader_department,
            t.leader_section,
            p.title AS problem_title,
            t.leader_name,
            t.leader_usn,
            t.leader_phone,

            f.name AS faculty_name,
            f.email AS faculty_email,
            f.department AS faculty_department
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        LEFT JOIN team_faculty tf ON t.id = tf.team_id
        LEFT JOIN faculty f ON tf.faculty_id = f.id
        ORDER BY p.title, t.team_name
    """)
    teams = cur.fetchall()

    cur.execute("""
        SELECT team_id, member_name, usn, department
        FROM team_members
        ORDER BY team_id, id
    """)
    members_rows = cur.fetchall()

    con.close()

    members_map = {}
    for m in members_rows:
        tid = m["team_id"]
        members_map.setdefault(tid, []).append(
            f"{m['member_name']} ({m['usn']}, {m['department']})"
        )

    export_rows = []
    for t in teams:
        tid = t["team_id"]

        members_text = " | ".join(members_map.get(tid, [])) if members_map.get(tid) else "-"

        faculty_text = "Not Assigned"
        if t["faculty_name"]:
            faculty_text = f"{t['faculty_name']} ({t['faculty_department']}) - {t['faculty_email']}"

        export_rows.append({
            "Team Name": t["team_name"],
            "Department": t["leader_department"],
            "Section": t["leader_section"],
            "Problem Title": t["problem_title"],
            "Leader Name": t["leader_name"],
            "Leader USN": t["leader_usn"],
            "Leader Phone": t["leader_phone"],
            "Team Members": members_text,
            "Faculty Guide": faculty_text
        })

    df = pd.DataFrame(export_rows)

    out_file = "Guide_Allocation_Report.xlsx"
    df.to_excel(out_file, index=False)

    return send_file(out_file, as_attachment=True)


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

    # Teams per department (leader_department)
    cur.execute("""
        SELECT leader_department, COUNT(*)
        FROM teams
        GROUP BY leader_department
        ORDER BY COUNT(*) DESC
    """)
    dept_data = cur.fetchall()

    # Hardware vs Software (Category)
    cur.execute("""
        SELECT p.category, COUNT(*)
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        GROUP BY p.category
        ORDER BY COUNT(*) DESC
    """)
    type_data = cur.fetchall()

    # ✅ Domain/Theme distribution (replaces difficulty)
    cur.execute("""
        SELECT p.domain_theme, COUNT(*)
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        GROUP BY p.domain_theme
        ORDER BY COUNT(*) DESC
    """)
    domain_data = cur.fetchall()

    # Not assigned teams count
    cur.execute("""
        SELECT COUNT(*)
        FROM teams t
        LEFT JOIN team_faculty tf ON t.id = tf.team_id
        WHERE tf.faculty_id IS NULL
    """)
    not_assigned_count = cur.fetchone()[0]

    # Pending weekly progress count
    cur.execute("""
        SELECT COUNT(*)
        FROM weekly_progress
        WHERE status='Pending'
    """)
    pending_progress_count = cur.fetchone()[0]

    # Faculty wise team assignments
    cur.execute("""
        SELECT f.name, COUNT(tf.team_id)
        FROM faculty f
        LEFT JOIN team_faculty tf ON f.id = tf.faculty_id
        GROUP BY f.id
        ORDER BY COUNT(tf.team_id) DESC
    """)
    faculty_data = cur.fetchall()

    con.close()

    return render_template(
        "dashboard.html",
        total_teams=total_teams,
        total_problems=total_problems,
        dept_data=dept_data,
        type_data=type_data,
        domain_data=domain_data,  # ✅ new
        not_assigned_count=not_assigned_count,
        pending_progress_count=pending_progress_count,
        faculty_data=faculty_data,
        active_page="dashboard"
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
    per_page = 25
    offset = (page - 1) * per_page

    # ---------------- FACULTY LIST ----------------
    cur.execute("SELECT id, name, email, department FROM faculty ORDER BY name")
    faculty_list = cur.fetchall()

    # ---------------- PROBLEM LIST ----------------
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
        # keep filters in UI
        search=search,
        dept_filter=dept_filter,
        faculty_filter=faculty_filter,
        problem_filter=problem_filter,
        # pagination
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_rows=total_rows
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

@app.route("/student/chat", methods=["GET", "POST"])
def student_chat():
    if not session.get("student_usn"):
        return redirect(url_for("student_login"))

    usn = session["student_usn"]

    con = db()
    cur = con.cursor()

    # Find team_id (leader or member)
    cur.execute("SELECT id, team_name, leader_name FROM teams WHERE leader_usn=?", (usn,))
    team = cur.fetchone()

    if not team:
        cur.execute("""
            SELECT t.id, t.team_name, t.leader_name
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

    # Check faculty assigned
    cur.execute("""
        SELECT f.name, f.email, f.department
        FROM team_faculty tf
        JOIN faculty f ON tf.faculty_id = f.id
        WHERE tf.team_id=?
    """, (team_id,))
    faculty = cur.fetchone()

    if not faculty:
        con.close()
        flash("Faculty guide not assigned yet. Chat will be available after assignment.")
        return redirect(url_for("student_my_project"))

    # Send message
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg:
            cur.execute("""
                INSERT INTO chat_messages(team_id, sender_role, sender_name, message)
                VALUES (?,?,?,?)
            """, (team_id, "student", usn, msg))
            con.commit()
        return redirect(url_for("student_chat"))

    # Fetch chat history
    cur.execute("""
        SELECT * FROM chat_messages
        WHERE team_id=?
        ORDER BY sent_at ASC
    """, (team_id,))
    messages = cur.fetchall()

    con.close()

    return render_template(
        "student_chat.html",
        team=team,
        faculty=faculty,
        messages=messages
    )
@app.route("/faculty/chat/<int:team_id>", methods=["GET", "POST"])
def faculty_chat(team_id):
    if not session.get("faculty_id"):
        return redirect(url_for("faculty_login"))

    faculty_id = session["faculty_id"]

    con = db()
    cur = con.cursor()

    # Ensure this team belongs to this faculty
    cur.execute("""
        SELECT t.id, t.team_name, t.leader_name, t.leader_usn
        FROM team_faculty tf
        JOIN teams t ON tf.team_id = t.id
        WHERE tf.faculty_id=? AND tf.team_id=?
    """, (faculty_id, team_id))
    team = cur.fetchone()

    if not team:
        con.close()
        flash("Unauthorized access.")
        return redirect(url_for("faculty_dashboard"))

    # Send message
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg:
            cur.execute("""
                INSERT INTO chat_messages(team_id, sender_role, sender_name, message)
                VALUES (?,?,?,?)
            """, (team_id, "faculty", session.get("faculty_name", "Faculty"), msg))
            con.commit()
        return redirect(url_for("faculty_chat", team_id=team_id))

    # Fetch chat history
    cur.execute("""
        SELECT * FROM chat_messages
        WHERE team_id=?
        ORDER BY sent_at ASC
    """, (team_id,))
    messages = cur.fetchall()

    con.close()

    return render_template(
        "faculty_chat.html",
        team=team,
        messages=messages
    )



if __name__ == "__main__":
    con = db()
    cur = con.cursor()

    # ---------------- CREATE TABLES ----------------

    cur.execute("""
    CREATE TABLE IF NOT EXISTS problems(
        id INTEGER PRIMARY KEY,
        year TEXT,
        title TEXT,
        category TEXT,
        domain_theme TEXT,
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
        problem_id INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER UNIQUE,
        abstract TEXT,
        objectives TEXT,
        tech_stack TEXT,
        methodology TEXT,
        modules TEXT,
        dataset_or_inputs TEXT,
        expected_output TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    """)

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS faculty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        department TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_faculty (
        team_id INTEGER UNIQUE,
        faculty_id INTEGER,
        FOREIGN KEY(team_id) REFERENCES teams(id),
        FOREIGN KEY(faculty_id) REFERENCES faculty(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        sender_role TEXT NOT NULL,
        sender_name TEXT,
        message TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT CHECK(role IN ('super_admin','admin')) NOT NULL,
        department TEXT,
        must_reset_password INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)


    # ---------------- SAFE MIGRATIONS ----------------
    # If old DB exists, these columns might be missing

    def add_column_if_not_exists(table, column, col_type):
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if column not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    # Problems
    add_column_if_not_exists("problems", "domain_theme", "TEXT")

    # Teams
    add_column_if_not_exists("teams", "leader_department", "TEXT")
    add_column_if_not_exists("teams", "leader_section", "TEXT")
    add_column_if_not_exists("teams", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # Project Details
    add_column_if_not_exists("project_details", "tech_stack", "TEXT")
    add_column_if_not_exists("project_details", "methodology", "TEXT")
    add_column_if_not_exists("project_details", "modules", "TEXT")
    add_column_if_not_exists("project_details", "dataset_or_inputs", "TEXT")
    add_column_if_not_exists("project_details", "expected_output", "TEXT")
    add_column_if_not_exists("project_details", "project_references", "TEXT")

    # -------- Students extra columns (safe migration) --------
    add_column_if_not_exists("students", "name", "TEXT")
    add_column_if_not_exists("students", "department", "TEXT")
    add_column_if_not_exists("students", "section", "TEXT")
    add_column_if_not_exists("students", "must_reset_password", "INTEGER DEFAULT 1")
    add_column_if_not_exists("students", "updated_at", "TIMESTAMP")

    add_column_if_not_exists("faculty", "must_reset_password", "INTEGER DEFAULT 1")
    add_column_if_not_exists("faculty", "updated_at", "TIMESTAMP")

    # ---------------- DEFAULT SETTINGS ----------------
    cur.execute("""
        INSERT OR IGNORE INTO settings(key,value)
        VALUES ('project_start_date','2026-02-02')
    """)

    from werkzeug.security import generate_password_hash

    cur.execute("""
        INSERT OR IGNORE INTO admins (name,email,password_hash,role,must_reset_password)
        VALUES (?,?,?,?,0)
    """, (
        "Super Admin",
        ADMIN_USER,
        generate_password_hash(ADMIN_PASS),
        "super_admin"
    ))


    con.commit()
    con.close()

    print("✅ Database initialized / migrated successfully.")


    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

