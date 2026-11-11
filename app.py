"""
AI-Based Exam Seating Arrangement System
Flask backend - run:  python app.py   then open http://127.0.0.1:5000
"""
import csv
import io
import os
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, flash,
                   session, send_file, jsonify)
from werkzeug.security import check_password_hash

from database import get_db, init_db, DB_PATH
from algorithm import backtracking_allocation, AllocationError

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

DEPT_COLORS = ["#2563eb", "#16a34a", "#dc2626", "#d97706", "#7c3aed",
               "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5"]


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "admin" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def dept_color_map(conn):
    depts = [r[0] for r in conn.execute("SELECT DISTINCT department FROM students ORDER BY department")]
    return {d: DEPT_COLORS[i % len(DEPT_COLORS)] for i, d in enumerate(depts)}


def sessions_list(conn):
    return conn.execute("SELECT DISTINCT exam_date, session FROM exams ORDER BY exam_date, session").fetchall()


# ---------------------------------------------------------------- auth
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get("username", "").strip(), request.form.get("password", "")
        conn = get_db()
        row = conn.execute("SELECT * FROM admin WHERE username=?", (u,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], p):
            session["admin"] = u
            return redirect(url_for("dashboard"))
        flash("Invalid username or password", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    q = lambda s: conn.execute(s).fetchone()[0]
    total_seats = q("SELECT COALESCE(SUM(capacity),0) FROM examination_halls")
    latest = conn.execute("SELECT exam_date, session FROM seat_allocations ORDER BY id DESC LIMIT 1").fetchone()
    allocated = 0
    if latest:
        allocated = conn.execute("SELECT COUNT(*) FROM seat_allocations WHERE exam_date=? AND session=?",
                                 (latest[0], latest[1])).fetchone()[0]
    stats = dict(students=q("SELECT COUNT(*) FROM students"), halls=q("SELECT COUNT(*) FROM examination_halls"),
                 exams=q("SELECT COUNT(*) FROM exams"), seats=total_seats, allocated=allocated,
                 available=total_seats - allocated)
    dept = conn.execute("SELECT department, COUNT(*) c FROM students GROUP BY department").fetchall()
    halls = conn.execute("""SELECT h.hall_name, h.capacity,
        (SELECT COUNT(*) FROM seat_allocations a WHERE a.hall_id=h.id AND a.exam_date=? AND a.session=?) used
        FROM examination_halls h""", (latest[0] if latest else "", latest[1] if latest else "")).fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats, latest=latest,
                           dept_labels=[d[0] for d in dept], dept_counts=[d[1] for d in dept],
                           hall_labels=[h[0] for h in halls], hall_used=[h[2] for h in halls],
                           hall_free=[h[1] - h[2] for h in halls])


# ---------------------------------------------------------------- students
def validate_student(f):
    errs = []
    for k in ("student_id", "name", "department", "year", "subject", "register_no"):
        if not str(f.get(k, "")).strip():
            errs.append(f"{k.replace('_', ' ').title()} is required")
    try:
        y = int(f.get("year", 0))
        if not 1 <= y <= 5:
            errs.append("Year must be between 1 and 5")
    except ValueError:
        errs.append("Year must be a number")
    return errs


@app.route("/students")
@login_required
def students():
    conn = get_db()
    search = request.args.get("q", "").strip()
    if search:
        like = f"%{search}%"
        rows = conn.execute("""SELECT * FROM students WHERE name LIKE ? OR register_no LIKE ? OR department LIKE ?
                               OR subject LIKE ? ORDER BY register_no""", (like,) * 4).fetchall()
    else:
        rows = conn.execute("SELECT * FROM students ORDER BY register_no").fetchall()
    colors = dept_color_map(conn)
    conn.close()
    return render_template("students.html", students=rows, q=search, colors=colors)


@app.route("/students/add", methods=["GET", "POST"])
@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def student_form(sid=None):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone() if sid else None
    if request.method == "POST":
        f = request.form
        errs = validate_student(f)
        if errs:
            for e in errs:
                flash(e, "danger")
        else:
            vals = (f["student_id"].strip(), f["name"].strip(), f["department"].strip().upper(),
                    int(f["year"]), f["subject"].strip(), f["register_no"].strip())
            try:
                if sid:
                    conn.execute("""UPDATE students SET student_id=?,name=?,department=?,year=?,subject=?,register_no=?
                                    WHERE id=?""", (*vals, sid))
                else:
                    conn.execute("""INSERT INTO students (student_id,name,department,year,subject,register_no)
                                    VALUES (?,?,?,?,?,?)""", vals)
                conn.commit()
                flash("Student saved", "success")
                conn.close()
                return redirect(url_for("students"))
            except Exception:
                flash("Student ID or Register Number already exists", "danger")
        student = f
    conn.close()
    return render_template("student_form.html", student=student, sid=sid)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required
def student_delete(sid):
    conn = get_db()
    conn.execute("DELETE FROM students WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    flash("Student deleted", "success")
    return redirect(url_for("students"))


@app.route("/students/upload", methods=["POST"])
@login_required
def student_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a CSV or Excel file", "danger")
        return redirect(url_for("students"))
    name = file.filename.lower()
    rows = []
    try:
        if name.endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(file.read().decode("utf-8-sig"))))
        elif name.endswith((".xlsx", ".xls")):
            from openpyxl import load_workbook
            ws = load_workbook(file, read_only=True).active
            data = list(ws.values)
            head = [str(h).strip() for h in data[0]]
            rows = [dict(zip(head, r)) for r in data[1:] if any(r)]
        else:
            flash("Unsupported file type. Use .csv or .xlsx", "danger")
            return redirect(url_for("students"))
    except Exception as e:
        flash(f"Could not read file: {e}", "danger")
        return redirect(url_for("students"))
    conn = get_db()
    added = skipped = 0
    for r in rows:
        r = {k.strip().lower(): ("" if v is None else str(v).strip()) for k, v in r.items() if k}
        if validate_student(r):
            skipped += 1
            continue
        cur = conn.execute("""INSERT OR IGNORE INTO students (student_id,name,department,year,subject,register_no)
                              VALUES (?,?,?,?,?,?)""",
                           (r["student_id"], r["name"], r["department"].upper(), int(r["year"]),
                            r["subject"], r["register_no"]))
        added += cur.rowcount
        skipped += 1 - cur.rowcount
    conn.commit()
    conn.close()
    flash(f"Imported {added} students ({skipped} skipped: invalid or duplicate)", "success")
    return redirect(url_for("students"))


# ---------------------------------------------------------------- exams
@app.route("/exams", methods=["GET", "POST"])
@login_required
def exams():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        eid = f.get("id")
        if not all(f.get(k, "").strip() for k in ("name", "subject", "exam_date", "session")) \
                or f["session"] not in ("Morning", "Afternoon"):
            flash("All exam fields are required", "danger")
        else:
            n = conn.execute("SELECT COUNT(*) FROM students WHERE subject=?", (f["subject"].strip(),)).fetchone()[0]
            vals = (f["name"].strip(), f["subject"].strip(), f["exam_date"], f["session"], n)
            if eid:
                conn.execute("UPDATE exams SET name=?,subject=?,exam_date=?,session=?,num_students=? WHERE id=?",
                             (*vals, eid))
            else:
                conn.execute("INSERT INTO exams (name,subject,exam_date,session,num_students) VALUES (?,?,?,?,?)", vals)
            conn.commit()
            flash("Exam saved", "success")
        return redirect(url_for("exams"))
    # refresh student counts
    conn.execute("UPDATE exams SET num_students=(SELECT COUNT(*) FROM students s WHERE s.subject=exams.subject)")
    conn.commit()
    rows = conn.execute("SELECT * FROM exams ORDER BY exam_date, session").fetchall()
    subjects = [r[0] for r in conn.execute("SELECT DISTINCT subject FROM students ORDER BY subject")]
    conn.close()
    return render_template("exams.html", exams=rows, subjects=subjects)


@app.route("/exams/<int:eid>/delete", methods=["POST"])
@login_required
def exam_delete(eid):
    conn = get_db()
    conn.execute("DELETE FROM exams WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    flash("Exam deleted", "success")
    return redirect(url_for("exams"))


# ---------------------------------------------------------------- halls
@app.route("/halls", methods=["GET", "POST"])
@login_required
def halls():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        hid = f.get("id")
        try:
            r, c = int(f["rows"]), int(f["cols"])
            assert f["hall_name"].strip() and f["hall_number"].strip() and 1 <= r <= 50 and 1 <= c <= 50
            vals = (f["hall_name"].strip(), f["hall_number"].strip(), r, c, r * c)
            if hid:
                conn.execute("UPDATE examination_halls SET hall_name=?,hall_number=?,rows=?,cols=?,capacity=? WHERE id=?",
                             (*vals, hid))
            else:
                conn.execute("INSERT INTO examination_halls (hall_name,hall_number,rows,cols,capacity) VALUES (?,?,?,?,?)",
                             vals)
            conn.commit()
            flash("Hall saved", "success")
        except (ValueError, AssertionError, KeyError):
            flash("Enter a valid hall name, number and rows/columns between 1 and 50", "danger")
        except Exception:
            flash("Hall number already exists", "danger")
        return redirect(url_for("halls"))
    rows = conn.execute("""SELECT h.*, (SELECT COUNT(*) FROM seat_allocations a WHERE a.hall_id=h.id
                  AND a.exam_date || a.session = (SELECT exam_date || session FROM seat_allocations ORDER BY id DESC LIMIT 1)) used
                  FROM examination_halls h ORDER BY hall_number""").fetchall()
    conn.close()
    return render_template("halls.html", halls=rows)


@app.route("/halls/<int:hid>/delete", methods=["POST"])
@login_required
def hall_delete(hid):
    conn = get_db()
    conn.execute("DELETE FROM examination_halls WHERE id=?", (hid,))
    conn.commit()
    conn.close()
    flash("Hall deleted", "success")
    return redirect(url_for("halls"))


# ---------------------------------------------------------------- generation
@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    conn = get_db()
    sess = sessions_list(conn)
    all_halls = conn.execute("SELECT * FROM examination_halls ORDER BY hall_number").fetchall()
    if request.method == "POST":
        key = request.form.get("session_key", "")
        hall_ids = request.form.getlist("halls")
        rules = {"department": "rule_department" in request.form,
                 "subject": "rule_subject" in request.form,
                 "year": "rule_year" in request.form}
        if "|" not in key or not hall_ids:
            flash("Select an exam session and at least one hall", "danger")
            return redirect(url_for("generate"))
        date, sname = key.split("|", 1)
        exams_ = conn.execute("SELECT * FROM exams WHERE exam_date=? AND session=?", (date, sname)).fetchall()
        subj_exam = {e["subject"]: e["id"] for e in exams_}
        studs = conn.execute(f"SELECT * FROM students WHERE subject IN ({','.join('?' * len(subj_exam))})",
                             list(subj_exam)).fetchall() if subj_exam else []
        students_ = [dict(s) for s in studs]
        halls_ = [dict(id=h["id"], rows=h["rows"], cols=h["cols"])
                  for h in all_halls if str(h["id"]) in hall_ids]
        try:
            result = backtracking_allocation(students_, halls_, rules)
        except AllocationError as e:
            flash(str(e), "danger")
            return redirect(url_for("generate"))
        by_id = {s["id"]: s for s in students_}
        conn.execute("DELETE FROM seat_allocations WHERE exam_date=? AND session=?", (date, sname))
        for a in result:
            conn.execute("""INSERT INTO seat_allocations (exam_date,session,student_id,exam_id,hall_id,row_no,col_no,color)
                            VALUES (?,?,?,?,?,?,?,?)""",
                         (date, sname, a["student_id"], subj_exam[by_id[a["student_id"]]["subject"]],
                          a["hall_id"], a["row"], a["col"], a["color"]))
        conn.commit()
        conn.close()
        flash(f"Seating generated for {len(result)} students using Graph Coloring + Backtracking. "
              f"Validation passed - no adjacent conflicts.", "success")
        return redirect(url_for("seating", date=date, session_name=sname))
    conn.close()
    return render_template("generate.html", sessions=sess, halls=all_halls)


def load_allocation(conn, date, sname):
    return conn.execute("""SELECT a.*, s.name, s.register_no, s.department, s.subject, s.year, s.student_id sid,
                           h.hall_name, h.hall_number, h.rows, h.cols, e.name exam_name
                           FROM seat_allocations a JOIN students s ON s.id=a.student_id
                           JOIN examination_halls h ON h.id=a.hall_id LEFT JOIN exams e ON e.id=a.exam_id
                           WHERE a.exam_date=? AND a.session=?
                           ORDER BY h.hall_number, a.row_no, a.col_no""", (date, sname)).fetchall()


@app.route("/seating")
@login_required
def seating():
    conn = get_db()
    allocated = conn.execute("SELECT DISTINCT exam_date, session FROM seat_allocations ORDER BY exam_date").fetchall()
    date = request.args.get("date") or (allocated[0][0] if allocated else None)
    sname = request.args.get("session_name") or (allocated[0][1] if allocated else None)
    rows = load_allocation(conn, date, sname) if date else []
    halls_ = {}
    for r in rows:
        h = halls_.setdefault(r["hall_id"], {"name": r["hall_name"], "number": r["hall_number"],
                                             "rows": r["rows"], "cols": r["cols"], "grid": {}})
        h["grid"][(r["row_no"], r["col_no"])] = r
    colors = dept_color_map(conn)
    conn.close()
    return render_template("seating.html", halls=halls_.values(), allocated=allocated, date=date,
                           sname=sname, colors=colors, total=len(rows))


@app.route("/find", methods=["GET"])
@login_required
def find_seat():
    reg = request.args.get("reg", "").strip()
    conn = get_db()
    rows = conn.execute("""SELECT a.exam_date, a.session, a.row_no, a.col_no, h.hall_name, s.name, s.register_no
        FROM seat_allocations a JOIN students s ON s.id=a.student_id JOIN examination_halls h ON h.id=a.hall_id
        WHERE s.register_no=?""", (reg,)).fetchall() if reg else []
    conn.close()
    return render_template("find.html", rows=rows, reg=reg)


# ---------------------------------------------------------------- reports
@app.route("/reports")
@login_required
def reports():
    conn = get_db()
    allocated = conn.execute("SELECT DISTINCT exam_date, session FROM seat_allocations ORDER BY exam_date").fetchall()
    conn.close()
    return render_template("reports.html", allocated=allocated)


@app.route("/reports/<kind>/<fmt>")
@login_required
def report_download(kind, fmt):
    date, sname = request.args.get("date"), request.args.get("session_name")
    conn = get_db()
    rows = load_allocation(conn, date, sname)
    conn.close()
    if not rows:
        flash("No allocation found for that session", "danger")
        return redirect(url_for("reports"))

    if kind == "hall":
        title = "Hall-wise Seating Report"
        head = ["Hall", "Row", "Column", "Register No", "Name", "Department", "Subject"]
        data = [[r["hall_name"], r["row_no"], r["col_no"], r["register_no"], r["name"], r["department"], r["subject"]]
                for r in rows]
    elif kind == "student":
        title = "Student-wise Seat Allocation"
        head = ["Register No", "Name", "Department", "Subject", "Hall", "Seat (R-C)"]
        data = sorted([[r["register_no"], r["name"], r["department"], r["subject"], r["hall_name"],
                        f"R{r['row_no']}-C{r['col_no']}"] for r in rows])
    elif kind == "attendance":
        title = "Examination Attendance Sheet"
        head = ["S.No", "Hall", "Seat", "Register No", "Name", "Subject", "Signature"]
        data = [[i + 1, r["hall_name"], f"R{r['row_no']}-C{r['col_no']}", r["register_no"], r["name"],
                 r["subject"], ""] for i, r in enumerate(rows)]
    else:
        return "Unknown report", 404

    subtitle = f"Date: {date}    Session: {sname}    Total: {len(rows)}"
    fname = f"{kind}_report_{date}_{sname}"

    if fmt == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow([title]); w.writerow([subtitle]); w.writerow([]); w.writerow(head); w.writerows(data)
        return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")), mimetype="text/csv",
                         as_attachment=True, download_name=fname + ".csv")
    if fmt == "excel":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook(); ws = wb.active; ws.title = "Report"
        ws.append([title]); ws["A1"].font = Font(bold=True, size=14)
        ws.append([subtitle]); ws.append([]); ws.append(head)
        for c in ws[4]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1E3A8A")
        for d in data:
            ws.append(d)
        for col in ws.columns:
            ws.column_dimensions[col[3].column_letter].width = max(12, max(len(str(c.value or "")) for c in col[3:]) + 2)
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=fname + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if fmt == "pdf":
        from reportlab.lib import colors as rc
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
        st = getSampleStyleSheet()
        t = Table([head] + [[str(x) for x in d] for d in data], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rc.HexColor("#1e3a8a")), ("TEXTCOLOR", (0, 0), (-1, 0), rc.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, rc.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rc.white, rc.HexColor("#f1f5f9")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if kind == "attendance" else 3)]))
        doc.build([Paragraph(title, st["Title"]), Paragraph(subtitle, st["Normal"]), Spacer(1, 12), t])
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=fname + ".pdf", mimetype="application/pdf")
    return "Unknown format", 404


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, msg="Something went wrong"), 500


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    else:
        init_db(with_sample=False)
    print("Open http://127.0.0.1:5000  (login: admin / admin123)")
    app.run(debug=True)
