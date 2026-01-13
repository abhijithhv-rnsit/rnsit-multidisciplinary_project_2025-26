from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash


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
        progress_count=progress_count
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

    if request.method == "POST":
        week_no = request.form["week_no"]
        progress = request.form["progress"]

        cur.execute("""
            INSERT INTO weekly_progress(team_id, week_no, progress)
            VALUES (?,?,?)
        """, (team_id, week_no, progress))

        con.commit()
        flash("Weekly progress submitted")

    # Fetch progress list
    cur.execute("""
        SELECT * FROM weekly_progress
        WHERE team_id=?
        ORDER BY week_no DESC
    """, (team_id,))
    progress_list = cur.fetchall()

    con.close()

    return render_template(
        "student_weekly_progress.html",
        progress_list=progress_list
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
            t.abstract,
            t.objectives,
            p.title AS problem_title,
            p.problem_description,
            p.problem_details,
            p.expected_outcome
        FROM teams t
        JOIN problems p ON t.problem_id = p.id
        WHERE t.id=?
    """, (team_id,))

    team = cur.fetchone()

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

@app.route("/")
def index():
    con=db(); cur=con.cursor()
    cur.execute("""
    SELECT id, year, title, category, difficulty, max_teams,
           problem_description, problem_details, expected_outcome
    FROM problems
""")

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
)


@app.route("/register/<int:pid>", methods=["GET","POST"])
def register(pid):
    
    from datetime import datetime

    # --- REGISTRATION DEADLINE CHECK ---
    con = db()
    cur = con.cursor()
    cur.execute(
        "SELECT value FROM settings WHERE key='registration_deadline'"
    )
    row = cur.fetchone()
    con.close()

    if row:
        deadline = datetime.fromisoformat(row[0])
        if datetime.now() > deadline:
            flash("Registration closed. Deadline has passed.")
            return redirect(url_for("index"))
    # --- END DEADLINE CHECK ---
    con=db(); cur=con.cursor()
    cur.execute("SELECT title,max_teams FROM problems WHERE id=?", (pid,))
    prob=cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM teams WHERE problem_id=?", (pid,))
    if cur.fetchone()[0] >= prob[1]:
        flash("Registration closed for this project")
        return redirect(url_for("index"))

    if request.method == "POST":

        # Team basic details
        team_name = request.form["team_name"]

        # Leader details
        leader_name = request.form["leader_name"]
        leader_usn = request.form["leader_usn"]
        leader_email = request.form["leader_email"]
        leader_phone = request.form["leader_phone"]
        leader_department = request.form["leader_department"]
        leader_section = request.form["leader_section"]

        # Collect team members
        members = []
        for i in range(1, 6):
            name = request.form.get(f"member{i}_name")
            usn = request.form.get(f"member{i}_usn")
            email = request.form.get(f"member{i}_email")
            phone = request.form.get(f"member{i}_phone")
            dept = request.form.get(f"member{i}_department")
            sec = request.form.get(f"member{i}_section")

            if usn:
                members.append((name, usn, email, phone, dept, sec))

        # Minimum team size check
        if len(members) < 2:
            flash("Minimum 3 members required including Team Leader")
            return redirect(request.url)

        con = db()
        cur = con.cursor()

        # Check leader USN uniqueness
        cur.execute("SELECT COUNT(*) FROM teams WHERE leader_usn=?", (leader_usn,))
        if cur.fetchone()[0] > 0:
            con.close()
            flash("Team Leader USN already registered")
            return redirect(request.url)

        # Check member USN uniqueness
        for _, usn, _, _, _, _ in members:
            cur.execute("SELECT COUNT(*) FROM team_members WHERE usn=?", (usn,))
            if cur.fetchone()[0] > 0:
                con.close()
                flash(f"Member USN {usn} already registered")
                return redirect(request.url)

        # Insert team
        cur.execute("""
            INSERT INTO teams(
                team_name,
                leader_name,
                leader_usn,
                leader_email,
                leader_phone,
                leader_department,
                leader_section,
                problem_id
            ) VALUES (?,?,?,?,?,?,?,?)
        """, (
            team_name,
            leader_name,
            leader_usn,
            leader_email,
            leader_phone,
            leader_department,
            leader_section,
            pid
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

        flash("Team registered successfully")
        return redirect(url_for("index"))


    con.close()
    return render_template("register.html", title=prob[0])

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
        department TEXT,
        section TEXT,
        leader_name TEXT,
        leader_usn TEXT UNIQUE,
        leader_email TEXT,
        leader_phone TEXT,
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
    add_column_if_not_exists("teams", "abstract", "TEXT")
    add_column_if_not_exists("teams", "objectives", "TEXT")

    # 🔥 GUARANTEED MIGRATION (THIS IS THE FIX)
    try:
        cur.execute("ALTER TABLE teams ADD COLUMN leader_department TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE teams ADD COLUMN leader_section TEXT")
    except:
        pass

    con.commit()
    con.close()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

