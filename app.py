
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3, pandas as pd, os

app = Flask(__name__)
app.secret_key = "rnsit-multidisciplinary-project-2025-26"

DB = "rnsit_multidisciplinary_project_2025_26.db"

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

    if request.method=="POST":
        members=[request.form.get(f"usn{i}") for i in range(1,7) if request.form.get(f"usn{i}")]
        if len(members) < 3:
            flash("Minimum 3 team members required")
            return redirect(request.url)

        for u in members:
            cur.execute("SELECT COUNT(*) FROM team_members WHERE usn=?", (u,))
            if cur.fetchone()[0] > 0:
                flash(f"USN {u} already registered in another team")
                return redirect(request.url)

        cur.execute("INSERT INTO teams(team_name,problem_id) VALUES (?,?)",
                    (request.form["team"], pid))
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
                "INSERT INTO problems(year,title,category,difficulty,max_teams) VALUES (?,?,?,?,5)",
                (r["Year"], r["Problem Statement"], r["Type"], r["Difficulty"])
            )
        con.commit(); con.close()
        flash("Projects imported successfully")
    return render_template("upload.html")

@app.route("/export")
def export():
    con=db()
    df=pd.read_sql("SELECT * FROM teams", con)
    path="rnsit_project_registrations.xlsx"
    df.to_excel(path,index=False)
    return send_file(path, as_attachment=True)

if __name__=="__main__":
    con=db(); cur=con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS problems(id INTEGER PRIMARY KEY,year TEXT,title TEXT,category TEXT,difficulty TEXT,max_teams INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY,team_name TEXT,problem_id INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS team_members(id INTEGER PRIMARY KEY,team_id INT,usn TEXT UNIQUE)")
    con.commit(); con.close()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
