from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from functools import wraps
import sqlite3, hashlib, os, calendar
from datetime import datetime, date, timedelta
from database import init_db, get_db

app = Flask(__name__)
# SECRET KEY: environment variable se lo, warna random generate karo
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
CORS(app)
init_db()
# ─────────────────────────────────────────────
# PASSWORD HASHING  (MD5 hatao, SHA-256 use karo)
# ─────────────────────────────────────────────
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ─────────────────────────────────────────────
# AUTH DECORATORS
# ─────────────────────────────────────────────
def require_login(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'ok': False, 'msg': 'Login karein pehle'}), 401
        return f(*args, **kwargs)
    return dec

def require_owner(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'ok': False, 'msg': 'Login karein pehle'}), 401
        if session.get('role') != 'owner':
            return jsonify({'ok': False, 'msg': 'Sirf Owner ye kar sakta hai'}), 403
        return f(*args, **kwargs)
    return dec

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    role = data.get('role', 'owner')
    pw_hash = hash_password(password)
    db = get_db()
    try:
        # SHA-256 se try karo pehle, phir MD5 fallback (purane passwords ke liye)
        user = db.execute(
            "SELECT * FROM users WHERE LOWER(username)=? AND password=? AND role=?",
            (username, pw_hash, role)
        ).fetchone()
        if not user:
            # MD5 fallback — purane password ke liye (pehli baar login pe upgrade ho jaayega)
            old_hash = hashlib.md5(password.encode()).hexdigest()
            user = db.execute(
                "SELECT * FROM users WHERE LOWER(username)=? AND password=? AND role=?",
                (username, old_hash, role)
            ).fetchone()
            if user:
                # Password ko SHA-256 mein upgrade karo
                db.execute("UPDATE users SET password=? WHERE id=?", (pw_hash, user['id']))
                db.commit()
    finally:
        db.close()
    if user:
        session['user_id'] = user['id']
        session['role']    = user['role']
        session['name']    = user['name']
        return jsonify({'ok': True, 'user': {'id': user['id'], 'name': user['name'], 'role': user['role']}})
    return jsonify({'ok': False, 'msg': 'Username ya password galat hai!'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/me')
def me():
    if 'user_id' not in session:
        return jsonify({'ok': False})
    return jsonify({'ok': True, 'user': {
        'id': session['user_id'],
        'name': session['name'],
        'role': session['role']
    }})

# ─────────────────────────────────────────────
# OWNER: PASSWORD CHANGE
# ─────────────────────────────────────────────
@app.route('/api/change_password', methods=['POST'])
@require_login
def change_password():
    d = request.json
    current_pw  = d.get('current_password', '').strip()
    new_pw      = d.get('new_password', '').strip()
    if not current_pw or not new_pw:
        return jsonify({'ok': False, 'msg': 'Purana aur naya password dono chahiye!'})
    if len(new_pw) < 4:
        return jsonify({'ok': False, 'msg': 'Naya password kam se kam 4 characters ka hona chahiye!'})
    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        # SHA-256 ya MD5 dono check karo
        if user['password'] not in (hash_password(current_pw), hashlib.md5(current_pw.encode()).hexdigest()):
            return jsonify({'ok': False, 'msg': 'Purana password galat hai!'})
        db.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_pw), session['user_id']))
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': 'Password badal gaya!'})

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
MONTH_NAMES = ['','January','February','March','April','May','June',
               'July','August','September','October','November','December']

def month_display(ym):
    y, m = ym.split('-')
    return f"{MONTH_NAMES[int(m)]} {y}"

def get_working_days(ym, holiday_dates):
    y, m = map(int, ym.split('-'))
    count = 0
    for d in range(1, calendar.monthrange(y, m)[1]+1):
        ds = f"{ym}-{str(d).zfill(2)}"
        if datetime(y, m, d).weekday() != 6 and ds not in holiday_dates:
            count += 1
    return count

def get_sundays_count(ym):
    y, m = map(int, ym.split('-'))
    return sum(1 for d in range(1, calendar.monthrange(y,m)[1]+1)
               if datetime(y,m,d).weekday() == 6)

def get_company(db):
    r = db.execute("SELECT value FROM settings WHERE key='company_name'").fetchone()
    return r['value'] if r else 'My Office'

def get_leave_allotment(db):
    """Leave allotment settings se lo (default 12)"""
    r = db.execute("SELECT value FROM settings WHERE key='annual_leaves'").fetchone()
    try:
        return int(r['value']) if r else 12
    except (ValueError, TypeError):
        return 12

def compute_salary(ym):
    db = get_db()
    try:
        emps         = db.execute("SELECT * FROM employees ORDER BY name").fetchall()
        hols         = db.execute("SELECT date, name FROM holidays WHERE date LIKE ?", (f"{ym}%",)).fetchall()
        holiday_dates= [h['date'] for h in hols]
        wdays        = get_working_days(ym, holiday_dates)
        sundays      = get_sundays_count(ym)
        y, m         = map(int, ym.split('-'))
        total_days   = calendar.monthrange(y, m)[1]
        result       = []
        for emp in emps:
            att_rows = db.execute(
                "SELECT date, status FROM attendance WHERE emp_id=? AND date LIKE ?",
                (emp['id'], f"{ym}%")
            ).fetchall()
            att_map = {r['date']: r['status'] for r in att_rows}
            present = absent = halfday = leave = hol_count = 0
            for d in range(1, total_days+1):
                ds = f"{ym}-{str(d).zfill(2)}"
                if datetime(y, m, d).weekday() == 6:
                    continue
                if ds in holiday_dates:
                    hol_count += 1
                    continue
                s = att_map.get(ds, 'absent')
                if   s == 'present':  present  += 1
                elif s == 'halfday':  halfday  += 1
                elif s == 'leave':    leave    += 1
                else:                 absent   += 1
            cut_row = db.execute(
                "SELECT cut_active FROM salary_cuts WHERE emp_id=? AND month=?",
                (emp['id'], ym)
            ).fetchone()
            is_cut        = bool(cut_row and cut_row['cut_active'])
            per_day       = round(emp['salary'] / wdays, 2) if wdays > 0 else 0
            hd_deduct     = round(per_day * 0.5 * halfday) if is_cut else 0
            absent_deduct = round(per_day * absent)
            total_deduct  = hd_deduct + absent_deduct
            net           = max(0, emp['salary'] - total_deduct)
            paid_days     = present + leave + (halfday * (0.5 if is_cut else 1.0))
            result.append({
                'emp_id': emp['id'], 'name': emp['name'], 'dept': emp['dept'],
                'designation': emp['designation'] or '', 'join_date': emp['join_date'] or '',
                'phone': emp['phone'] or '', 'basic': emp['salary'], 'net': net,
                'total_deduct': total_deduct, 'hd_deduct': hd_deduct,
                'absent_deduct': absent_deduct, 'per_day': round(per_day),
                'working_days': wdays, 'sundays': sundays, 'holidays_count': hol_count,
                'present': present, 'halfday': halfday, 'leave': leave, 'absent': absent,
                'is_cut': is_cut, 'paid_days': round(paid_days, 1)
            })
    finally:
        db.close()
    return result, wdays

# ─────────────────────────────────────────────
# EMPLOYEES
# ─────────────────────────────────────────────
@app.route('/api/employees', methods=['GET'])
@require_login
def get_employees():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM employees ORDER BY name").fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/employees', methods=['POST'])
@require_login
@require_owner
def add_employee():
    d = request.json
    db = get_db()
    try:
        db.execute(
            "INSERT INTO employees (name,dept,designation,salary,join_date,phone) VALUES (?,?,?,?,?,?)",
            (d['name'], d.get('dept',''), d.get('designation',''), d.get('salary',0),
             d.get('join_date', str(date.today())), d.get('phone',''))
        )
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': f"{d['name']} add ho gaye!"})

@app.route('/api/employees/<int:eid>', methods=['PUT'])
@require_login
@require_owner
def update_employee(eid):
    d = request.json
    db = get_db()
    try:
        db.execute(
            "UPDATE employees SET name=?,dept=?,designation=?,salary=?,phone=? WHERE id=?",
            (d['name'], d.get('dept',''), d.get('designation',''), d.get('salary',0), d.get('phone',''), eid)
        )
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': 'Employee update ho gaya!'})

@app.route('/api/employees/<int:eid>', methods=['DELETE'])
@require_login
@require_owner
def delete_employee(eid):
    db = get_db()
    try:
        db.execute("DELETE FROM employees WHERE id=?", (eid,))
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────────
@app.route('/api/attendance', methods=['GET'])
@require_login
def get_attendance():
    date_str = request.args.get('date', str(date.today()))
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM attendance WHERE date=?", (date_str,)).fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/attendance', methods=['POST'])
@require_login
def mark_attendance():
    """
    FIX: Pehle 'present' bulk mark hota hai, phir kisi ko 'absent' mark karte hain
         toh wo update nahi hota tha. Ab UPDATE sahi se kaam karega.
    """
    d  = request.json
    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM attendance WHERE emp_id=? AND date=?",
            (d['emp_id'], d['date'])
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE attendance SET status=? WHERE emp_id=? AND date=?",
                (d['status'], d['emp_id'], d['date'])
            )
        else:
            db.execute(
                "INSERT INTO attendance (emp_id,date,status) VALUES (?,?,?)",
                (d['emp_id'], d['date'], d['status'])
            )
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

@app.route('/api/attendance/bulk', methods=['POST'])
@require_login
def bulk_attendance():
    """
    FIX: Bulk mark ke waqt sabka record pehle fetch karo, phir ek ek update/insert karo.
         Yeh ensure karta hai koi bhi employee ka record miss na ho.
    """
    d  = request.json
    db = get_db()
    try:
        emps = db.execute("SELECT id FROM employees").fetchall()
        existing_ids = {
            row['emp_id']
            for row in db.execute(
                "SELECT emp_id FROM attendance WHERE date=?", (d['date'],)
            ).fetchall()
        }
        for emp in emps:
            if emp['id'] in existing_ids:
                db.execute(
                    "UPDATE attendance SET status=? WHERE emp_id=? AND date=?",
                    (d['status'], emp['id'], d['date'])
                )
            else:
                db.execute(
                    "INSERT INTO attendance (emp_id,date,status) VALUES (?,?,?)",
                    (emp['id'], d['date'], d['status'])
                )
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# HOLIDAYS
# ─────────────────────────────────────────────
@app.route('/api/holidays', methods=['GET'])
@require_login
def get_holidays():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM holidays ORDER BY date").fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/holidays', methods=['POST'])
@require_login
@require_owner
def add_holiday():
    d  = request.json
    db = get_db()
    try:
        if not db.execute("SELECT id FROM holidays WHERE date=?", (d['date'],)).fetchone():
            db.execute(
                "INSERT INTO holidays (date,name) VALUES (?,?)",
                (d['date'], d.get('name', 'Holiday'))
            )
            db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': f"{d.get('name','Holiday')} add ho gaya!"})

@app.route('/api/holidays/<string:hdate>', methods=['DELETE'])
@require_login
@require_owner
def delete_holiday(hdate):
    db = get_db()
    try:
        db.execute("DELETE FROM holidays WHERE date=?", (hdate,))
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# LEAVES
# ─────────────────────────────────────────────
@app.route('/api/leaves', methods=['GET'])
@require_login
def get_leaves():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT l.*, e.name as emp_name, e.dept
            FROM leaves l JOIN employees e ON l.emp_id=e.id
            ORDER BY l.id DESC
        """).fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/leaves', methods=['POST'])
@require_login
def apply_leave():
    d  = request.json
    db = get_db()
    try:
        db.execute(
            "INSERT INTO leaves (emp_id,leave_type,from_date,to_date,reason,status) VALUES (?,?,?,?,?,?)",
            (d['emp_id'], d.get('leave_type','Casual Leave'),
             d['from_date'], d['to_date'], d.get('reason',''), 'pending')
        )
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': 'Leave apply ho gayi! Approval pending.'})

@app.route('/api/leaves/<int:lid>', methods=['PUT'])
@require_login
@require_owner
def update_leave(lid):
    d  = request.json
    db = get_db()
    try:
        leave = db.execute("SELECT * FROM leaves WHERE id=?", (lid,)).fetchone()
        db.execute("UPDATE leaves SET status=? WHERE id=?", (d['status'], lid))
        if d['status'] == 'approved' and leave:
            cur = datetime.strptime(leave['from_date'], '%Y-%m-%d')
            end = datetime.strptime(leave['to_date'],   '%Y-%m-%d')
            while cur <= end:
                # FIX: Sunday skip karo leave attendance mein
                if cur.weekday() == 6:
                    cur += timedelta(days=1)
                    continue
                ds = cur.strftime('%Y-%m-%d')
                if db.execute(
                    "SELECT id FROM attendance WHERE emp_id=? AND date=?",
                    (leave['emp_id'], ds)
                ).fetchone():
                    db.execute(
                        "UPDATE attendance SET status='leave' WHERE emp_id=? AND date=?",
                        (leave['emp_id'], ds)
                    )
                else:
                    db.execute(
                        "INSERT INTO attendance (emp_id,date,status) VALUES (?,?,'leave')",
                        (leave['emp_id'], ds)
                    )
                cur += timedelta(days=1)
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': 'Updated!'})

@app.route('/api/leave_balance', methods=['GET'])
@require_login
def leave_balance():
    db = get_db()
    try:
        allotted = get_leave_allotment(db)
        emps     = db.execute("SELECT * FROM employees ORDER BY name").fetchall()
        result   = []
        for emp in emps:
            used = db.execute(
                "SELECT COUNT(*) as c FROM attendance WHERE emp_id=? AND status='leave'",
                (emp['id'],)
            ).fetchone()['c']
            result.append({
                'emp_id':    emp['id'],
                'name':      emp['name'],
                'dept':      emp['dept'],
                'allotted':  allotted,
                'used':      used,
                'remaining': max(0, allotted - used)
            })
    finally:
        db.close()
    return jsonify(result)

# ─────────────────────────────────────────────
# SALARY
# ─────────────────────────────────────────────
@app.route('/api/salary', methods=['GET'])
@require_login
def get_salary():
    ym = request.args.get('month', str(date.today())[:7])
    data, wdays = compute_salary(ym)
    return jsonify({'ok': True, 'data': data, 'working_days': wdays})

@app.route('/api/salary/cut', methods=['POST'])
@require_login
@require_owner
def toggle_salary_cut():
    d  = request.json
    db = get_db()
    try:
        if db.execute(
            "SELECT * FROM salary_cuts WHERE emp_id=? AND month=?",
            (d['emp_id'], d['month'])
        ).fetchone():
            db.execute(
                "UPDATE salary_cuts SET cut_active=? WHERE emp_id=? AND month=?",
                (d['cut_active'], d['emp_id'], d['month'])
            )
        else:
            db.execute(
                "INSERT INTO salary_cuts (emp_id,month,cut_active) VALUES (?,?,?)",
                (d['emp_id'], d['month'], d['cut_active'])
            )
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# SALARY SLIP
# ─────────────────────────────────────────────
@app.route('/api/salary_slip/<int:emp_id>')
@require_login
def salary_slip(emp_id):
    ym  = request.args.get('month', str(date.today())[:7])
    db  = get_db()
    try:
        emp     = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
        company = get_company(db)
    finally:
        db.close()
    if not emp:
        return "Employee not found", 404
    data, _ = compute_salary(ym)
    e = next((x for x in data if x['emp_id'] == emp_id), None)
    if not e:
        return "Data not found", 404
    mn        = month_display(ym)
    today_str = date.today().strftime('%d %B %Y')

    deduct_rows = ''
    if e['absent'] > 0:
        deduct_rows += (
            f"<tr><td class='lbl'>Absent Deduction ({e['absent']} din × Rs.{e['per_day']})</td>"
            f"<td class='val red'>- Rs. {e['absent_deduct']:,}</td></tr>"
        )
    if e['is_cut'] and e['halfday'] > 0:
        deduct_rows += (
            f"<tr><td class='lbl'>Half Day Deduction ({e['halfday']} din × Rs.{round(e['per_day']/2)})</td>"
            f"<td class='val red'>- Rs. {e['hd_deduct']:,}</td></tr>"
        )

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/>
<title>Salary Slip - {emp['name']} - {mn}</title>
<style>
@media print{{body{{margin:0}}.noprint{{display:none}}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;font-size:13px;color:#1e293b;background:#f0f2f7}}
.page{{background:#fff;max-width:720px;margin:20px auto;border-radius:10px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.12)}}
.hdr{{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:28px 32px}}
.hdr h1{{font-size:22px;font-weight:700}}.hdr p{{font-size:12px;opacity:.8;margin-top:3px}}
.badge{{display:inline-block;background:rgba(255,255,255,.2);padding:4px 14px;border-radius:20px;font-size:12px;font-weight:600;margin-top:8px}}
.body{{padding:28px 32px}}
.sec{{margin-bottom:22px}}
.sec-title{{font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #e2e6f0;padding-bottom:6px;margin-bottom:12px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:6px 20px}}
.row{{display:flex;justify-content:space-between;padding:4px 0}}
.lbl{{color:#64748b;font-size:12px}}.val{{font-weight:600;font-size:12px}}
.att-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.att-box{{background:#f7f8fc;border-radius:8px;padding:12px;text-align:center;border:1px solid #e2e6f0}}
.att-num{{font-size:22px;font-weight:700}}.att-lbl{{font-size:10px;color:#64748b;margin-top:2px;text-transform:uppercase;letter-spacing:.5px}}
.blue{{color:#2563eb}}.green{{color:#16a34a}}.orange{{color:#d97706}}.purple{{color:#7c3aed}}.red{{color:#dc2626}}.gray{{color:#64748b}}
.sal-table{{width:100%;border-collapse:collapse}}
.sal-table td{{padding:10px 14px;border-bottom:1px solid #e2e6f0;font-size:13px}}
.sal-table .val{{text-align:right;font-weight:600}}
.sal-table .red{{text-align:right;font-weight:600;color:#dc2626}}
.net-row td{{background:#1e3a8a;color:#fff!important;font-size:15px;font-weight:700}}
.net-row .val{{text-align:right;color:#fff!important}}
.note{{font-size:11px;color:#94a3b8;background:#f7f8fc;border-radius:6px;padding:8px 12px;margin-top:8px;border:1px solid #e2e6f0}}
.ftr{{border-top:1px solid #e2e6f0;padding:16px 32px;display:flex;justify-content:space-between;align-items:flex-end;background:#f7f8fc}}
.ftr-lft{{font-size:11px;color:#94a3b8}}
.sign{{text-align:center}}.sign-line{{width:160px;border-top:1.5px solid #1e293b;margin-bottom:4px}}
.sign-lbl{{font-size:11px;color:#64748b}}
.noprint{{text-align:center;margin:16px 0}}
.noprint button{{background:#2563eb;color:#fff;border:none;padding:10px 32px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:Arial,sans-serif}}
</style></head><body>
<div class="noprint"><button onclick="window.print()">📥 PDF Download / Print Karein</button></div>
<div class="page">
  <div class="hdr">
    <h1>{company}</h1><p>Employee Salary Slip</p>
    <div class="badge">{mn}</div>
  </div>
  <div class="body">
    <div class="sec">
      <div class="sec-title">Employee Details</div>
      <div class="grid2">
        <div class="row"><span class="lbl">Employee ID</span><span class="val">EMP-{str(emp_id).zfill(3)}</span></div>
        <div class="row"><span class="lbl">Naam</span><span class="val">{emp['name']}</span></div>
        <div class="row"><span class="lbl">Department</span><span class="val">{emp['dept'] or '—'}</span></div>
        <div class="row"><span class="lbl">Designation</span><span class="val">{emp['designation'] or '—'}</span></div>
        <div class="row"><span class="lbl">Joining Date</span><span class="val">{emp['join_date'] or '—'}</span></div>
        <div class="row"><span class="lbl">Phone</span><span class="val">{emp['phone'] or '—'}</span></div>
      </div>
    </div>
    <div class="sec">
      <div class="sec-title">Attendance Summary — {mn}</div>
      <div class="att-grid">
        <div class="att-box"><div class="att-num blue">{e['working_days']}</div><div class="att-lbl">Total Working Days</div></div>
        <div class="att-box"><div class="att-num green">{e['present']}</div><div class="att-lbl">Present Days</div></div>
        <div class="att-box"><div class="att-num orange">{e['halfday']}</div><div class="att-lbl">Half Days</div></div>
        <div class="att-box"><div class="att-num purple">{e['leave']}</div><div class="att-lbl">Leave Days</div></div>
        <div class="att-box"><div class="att-num red">{e['absent']}</div><div class="att-lbl">Absent Days</div></div>
        <div class="att-box"><div class="att-num gray">{e['holidays_count']}</div><div class="att-lbl">Holidays</div></div>
        <div class="att-box"><div class="att-num gray">{e['sundays']}</div><div class="att-lbl">Sundays (Off)</div></div>
        <div class="att-box"><div class="att-num blue">{e['paid_days']}</div><div class="att-lbl">Paid Days</div></div>
      </div>
    </div>
    <div class="sec">
      <div class="sec-title">Salary Details</div>
      <table class="sal-table">
        <tr><td class="lbl">Basic Salary (Monthly)</td><td class="val">Rs. {e['basic']:,}</td></tr>
        <tr><td class="lbl">Per Day Rate</td><td class="val">Rs. {e['per_day']:,}</td></tr>
        {deduct_rows}
        <tr class="net-row"><td>Net Payable Salary</td><td class="val">Rs. {e['net']:,}</td></tr>
      </table>
      <div class="note">{'Half day salary cut is active for this employee this month.' if e['is_cut'] else 'Half day salary cut is not applied this month.'}</div>
    </div>
  </div>
  <div class="ftr">
    <div class="ftr-lft"><div>Generated: {today_str}</div><div style="margin-top:2px">Computer generated salary slip.</div></div>
    <div class="sign"><div class="sign-line"></div><div class="sign-lbl">Authorized Signature</div></div>
  </div>
</div></body></html>"""

# ─────────────────────────────────────────────
# MONTHLY REPORT
# ─────────────────────────────────────────────
@app.route('/api/monthly_report')
@require_login
def monthly_report():
    ym  = request.args.get('month', str(date.today())[:7])
    db  = get_db()
    try:
        company = get_company(db)
    finally:
        db.close()
    data, wdays  = compute_salary(ym)
    mn           = month_display(ym)
    today_str    = date.today().strftime('%d %B %Y')
    total_net    = sum(d['net'] for d in data)

    rows = ''.join(f"""<tr>
      <td>{i+1}</td>
      <td><strong>{e['name']}</strong><br><span style="color:#64748b;font-size:11px">{e['dept']}</span></td>
      <td style="text-align:center">{wdays}</td>
      <td style="text-align:center;color:#16a34a;font-weight:600">{e['present']}</td>
      <td style="text-align:center;color:#d97706;font-weight:600">{e['halfday']}</td>
      <td style="text-align:center;color:#7c3aed;font-weight:600">{e['leave']}</td>
      <td style="text-align:center;color:#dc2626;font-weight:600">{e['absent']}</td>
      <td style="text-align:right">Rs. {e['basic']:,}</td>
      <td style="text-align:right;color:#dc2626">{'- Rs. '+str(e['total_deduct']) if e['total_deduct']>0 else '—'}</td>
      <td style="text-align:right;color:#16a34a;font-weight:700">Rs. {e['net']:,}</td>
    </tr>""" for i, e in enumerate(data))

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/>
<title>Monthly Report - {mn}</title>
<style>
@media print{{body{{margin:0}}.noprint{{display:none}}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;font-size:12px;color:#1e293b;background:#f0f2f7}}
.page{{background:#fff;max-width:980px;margin:20px auto;border-radius:10px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.12)}}
.hdr{{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:22px 32px;display:flex;justify-content:space-between;align-items:center}}
.hdr h1{{font-size:20px;font-weight:700}}.hdr p{{font-size:12px;opacity:.8;margin-top:3px}}
.badge{{background:rgba(255,255,255,.2);padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e2e6f0}}
.sbox{{padding:16px 20px;border-right:1px solid #e2e6f0}}.sbox:last-child{{border-right:none}}
.slbl{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.5px}}
.snum{{font-size:20px;font-weight:700;margin-top:4px}}
.body{{padding:20px 24px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#1e293b;color:#fff;padding:10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.4px;text-align:left}}
td{{padding:10px;border-bottom:1px solid #e2e6f0;vertical-align:middle}}
tr:hover td{{background:#f8faff}}tr:last-child td{{border-bottom:none}}
.total-row td{{background:#f0f9ff;font-weight:700;border-top:2px solid #2563eb}}
.ftr{{padding:14px 24px;display:flex;justify-content:space-between;background:#f7f8fc;border-top:1px solid #e2e6f0;font-size:11px;color:#94a3b8}}
.noprint{{text-align:center;margin:16px 0}}
.noprint button{{background:#2563eb;color:#fff;border:none;padding:10px 32px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}}
</style></head><body>
<div class="noprint"><button onclick="window.print()">📥 PDF Download / Print Karein</button></div>
<div class="page">
  <div class="hdr">
    <div><h1>{company}</h1><p>Monthly Attendance &amp; Salary Report</p></div>
    <div class="badge">{mn}</div>
  </div>
  <div class="summary">
    <div class="sbox"><div class="slbl">Total Employees</div><div class="snum" style="color:#2563eb">{len(data)}</div></div>
    <div class="sbox"><div class="slbl">Working Days</div><div class="snum">{wdays}</div></div>
    <div class="sbox"><div class="slbl">Total Payable</div><div class="snum" style="color:#16a34a">Rs. {total_net:,}</div></div>
    <div class="sbox"><div class="slbl">Generated On</div><div class="snum" style="font-size:13px;color:#64748b">{today_str}</div></div>
  </div>
  <div class="body">
    <table>
      <tr><th>#</th><th>Employee</th><th style="text-align:center">Working Days</th>
      <th style="text-align:center">Present</th><th style="text-align:center">Half Day</th>
      <th style="text-align:center">Leave</th><th style="text-align:center">Absent</th>
      <th style="text-align:right">Basic</th><th style="text-align:right">Deduction</th>
      <th style="text-align:right">Net Salary</th></tr>
      {rows}
      <tr class="total-row">
        <td colspan="9" style="text-align:right;padding-right:10px">Total Payable:</td>
        <td style="text-align:right;color:#16a34a;font-size:14px">Rs. {total_net:,}</td>
      </tr>
    </table>
  </div>
  <div class="ftr">
    <span>Generated: {today_str} | {company}</span>
    <span>Confidential — For Internal Use Only</span>
  </div>
</div></body></html>"""

# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────
@app.route('/api/settings', methods=['GET'])
@require_login
def get_settings():
    db = get_db()
    try:
        rows = db.execute("SELECT key, value FROM settings").fetchall()
    finally:
        db.close()
    return jsonify({r['key']: r['value'] for r in rows})

@app.route('/api/settings', methods=['POST'])
@require_login
@require_owner
def save_settings():
    d  = request.json
    db = get_db()
    try:
        for key, value in d.items():
            if db.execute("SELECT key FROM settings WHERE key=?", (key,)).fetchone():
                db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
            else:
                db.execute("INSERT INTO settings (key,value) VALUES (?,?)", (key, value))
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': 'Settings save ho gayi!'})

# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@require_login
@require_owner
def get_users():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT id,name,username,role,dept FROM users ORDER BY role"
        ).fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/users', methods=['POST'])
@require_login
@require_owner
def add_user():
    d       = request.json
    pw_hash = hash_password(d['password'])
    db      = get_db()
    try:
        db.execute(
            "INSERT INTO users (name,username,password,role,dept) VALUES (?,?,?,?,?)",
            (d['name'], d['username'].lower(), pw_hash,
             d.get('role','manager'), d.get('dept','General'))
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({'ok': False, 'msg': 'Username already exists!'})
    finally:
        db.close()
    return jsonify({'ok': True, 'msg': f"{d['name']} add ho gaye!"})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@require_login
@require_owner
def delete_user(uid):
    if uid == session['user_id']:
        return jsonify({'ok': False, 'msg': 'Aap khud ko delete nahi kar sakte!'})
    db = get_db()
    try:
        db.execute("DELETE FROM users WHERE id=?", (uid,))
        db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '127.0.0.1'
    print(f"\n{'='*52}")
    print(f"  Office HR System CHAL RAHA HAI!")
    print(f"{'='*52}")
    print(f"  Is PC par:            http://localhost:5000")
    print(f"  Doosre PC/Mobile par: http://{local_ip}:5000")
    print(f"  (Same WiFi/LAN par honge tabhi)")
    print(f"{'='*52}\n")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
