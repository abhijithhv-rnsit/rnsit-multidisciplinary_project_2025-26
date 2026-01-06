from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask import session

import sqlite3, pandas as pd, os



app = Flask(__name__)
app.secret_key = "rnsit_admin_secret_2025"

app.secret_key = "rnsit-multidisciplinary-project-2025-26"

DB = "rnsit_multidisciplinary_project_2025_26_v3.db"

ADMIN_USER = "rnsit_admin"
ADMIN_PASS = "RNSIT@2025"

def db():
    return sqlite3.connect(DB)

from datetime import datetime
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

        # Team details
        team_name = request.form["team_name"]
        department = request.form["department"]
        section = request.form["section"]

        # Leader details
        leader_name = request.form["leader_name"]
        leader_usn = request.form["leader_usn"]
        leader_email = request.form["leader_email"]
        leader_phone = request.form["leader_phone"]

        # Collect team members
        members = []
        for i in range(1, 6):
            name = request.form.get(f"member{i}_name")
            usn = request.form.get(f"member{i}_usn")
            email = request.form.get(f"member{i}_email")
            phone = request.form.get(f"member{i}_phone")

            if usn:
                members.append((name, usn, email, phone))

        # Minimum team size check (leader + 2 members)
        if len(members) < 2:
            flash("Minimum 3 members required including Team Leader")
            return redirect(request.url)

        # Check USN uniqueness (leader + members)
        cur.execute("SELECT COUNT(*) FROM teams WHERE leader_usn=?", (leader_usn,))
        if cur.fetchone()[0] > 0:
            flash("Team Leader USN already registered")
            return redirect(request.url)

        for _, usn, _, _ in members:
            cur.execute("SELECT COUNT(*) FROM team_members WHERE usn=?", (usn,))
            if cur.fetchone()[0] > 0:
                flash(f"Member USN {usn} already registered")
                return redirect(request.url)

        # Insert team
        cur.execute("""
            INSERT INTO teams(
                team_name, department, section,
                leader_name, leader_usn, leader_email, leader_phone,
                problem_id
            ) VALUES (?,?,?,?,?,?,?,?)
        """, (
            team_name, department, section,
            leader_name, leader_usn, leader_email, leader_phone,
            pid
        ))

        team_id = cur.lastrowid

        # Insert team members
        for name, usn, email, phone in members:
            cur.execute("""
                INSERT INTO team_members(
                    team_id, member_name, usn, email, phone
                ) VALUES (?,?,?,?,?)
            """, (team_id, name, usn, email, phone))

        con.commit()
        con.close()

        flash("Team registered successfully")
        return redirect(url_for("index"))

        tid=cur.lastrowid

        for u in members:
            cur.execute("INSERT INTO team_members(team_id,usn) VALUES (?,?)",(tid,u))

        con.commit(); con.close()
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
        problems=problems
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


if __name__=="__main__":
    con=db(); cur=con.cursor()
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
    phone TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

con.commit(); con.close()

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
