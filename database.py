import sqlite3, hashlib, os

DB_PATH = os.path.join(os.path.dirname(__file__), 'office_hr.db')

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'manager',
            dept TEXT DEFAULT 'General'
        );
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dept TEXT DEFAULT '',
            designation TEXT DEFAULT '',
            salary INTEGER DEFAULT 0,
            join_date TEXT DEFAULT '',
            phone TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'absent',
            UNIQUE(emp_id, date)
        );
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Holiday'
        );
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id INTEGER NOT NULL,
            leave_type TEXT DEFAULT 'Casual Leave',
            from_date TEXT NOT NULL,
            to_date TEXT NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS salary_cuts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            cut_active INTEGER DEFAULT 0,
            UNIQUE(emp_id, month)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
    """)

    # Default accounts — SHA-256 hashing
    owner_pw = hash_password('owner123')
    mgr_pw   = hash_password('mgr123')
    db.execute("INSERT OR IGNORE INTO users (name,username,password,role,dept) VALUES (?,?,?,?,?)",
               ('Owner Sahab', 'owner', owner_pw, 'owner', 'Management'))
    db.execute("INSERT OR IGNORE INTO users (name,username,password,role,dept) VALUES (?,?,?,?,?)",
               ('Manager Ji', 'manager', mgr_pw, 'manager', 'HR'))

    # Default settings
    db.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('company_name','My Office')")
    db.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('annual_leaves','12')")

    # Sample employees
    for e in [
        ('Amit Kumar',   'Sales',    'Executive',       25000, '2023-01-10', '9876543210'),
        ('Sunita Devi',  'Accounts', 'Accountant',      22000, '2023-03-15', '9876543211'),
        ('Ravi Verma',   'IT',       'Developer',       30000, '2022-11-01', '9876543212'),
        ('Pooja Yadav',  'HR',       'HR Executive',    20000, '2024-01-05', '9876543213'),
        ('Deepak Jha',   'Sales',    'Sr. Executive',   23000, '2023-06-20', '9876543214'),
        ('Kavita Mishra','Admin',    'Admin Assistant', 18000, '2023-09-12', '9876543215'),
    ]:
        db.execute(
            "INSERT OR IGNORE INTO employees (name,dept,designation,salary,join_date,phone) VALUES (?,?,?,?,?,?)", e
        )

    db.commit()
    db.close()
    print("Database ready!")
