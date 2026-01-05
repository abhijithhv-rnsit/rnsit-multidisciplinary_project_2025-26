
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3, pandas as pd, os

app = Flask(__name__)
app.secret_key = "rnsit-multidisciplinary-project-2025-26"

DB = "rnsit_multidisciplinary_project_2025_26_v3.db"



ADMIN_USER = "rnsit_admin"
ADMIN_PASS = "RNSIT@2025"

def db():
    return sqlite3.connect(DB)

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
    return render_template("index.html", data=data)

@app.route("/register/<int:pid>", methods=["GET","POST"])
def register(pid):
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

@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method=="POST":
        if request.form["u"]==ADMIN_USER and request.form["p"]==ADMIN_PASS:
            return redirect(url_for("upload"))
        flash("Invalid admin credentials")
    return render_template("admin.html")

@app.route("/upload", methods=["GET","POST"])
def upload():
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
    return render_template("upload.html")

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
con.commit(); con.close()

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
