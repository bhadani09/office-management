import hashlib
import os
import psycopg2
import psycopg2.extras

# Supabase se jo CONNECTION STRING mili hai woh .env ya Railway environment variable mein daal dena
# DATABASE_URL = "postgresql://postgres:[PASSWORD]@db.xxxx.supabase.co:5432/postgres"

def get_db():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.cursor_factory = psycopg2.extras.RealDictCursor  # sqlite3.Row jaisa kaam karta hai
    return conn

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    db = get_db()
    cur = db.cursor()

    # Tables banana
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'manager',
            dept TEXT DEFAULT 'General'
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            dept TEXT DEFAULT '',
            designation TEXT DEFAULT '',
            salary INTEGER DEFAULT 0,
            join_date TEXT DEFAULT '',
            phone TEXT DEFAULT ''
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            emp_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'absent',
            UNIQUE(emp_id, date)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id SERIAL PRIMARY KEY,
            date TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Holiday'
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaves (
            id SERIAL PRIMARY KEY,
            emp_id INTEGER NOT NULL,
            leave_type TEXT DEFAULT 'Casual Leave',
            from_date TEXT NOT NULL,
            to_date TEXT NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'pending'
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS salary_cuts (
            id SERIAL PRIMARY KEY,
            emp_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            cut_active INTEGER DEFAULT 0,
            UNIQUE(emp_id, month)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
    """)

    # Default accounts
    owner_pw = hash_password('owner123')
    mgr_pw   = hash_password('mgr123')

    cur.execute("""
        INSERT INTO users (name, username, password, role, dept)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (username) DO NOTHING
    """, ('Owner Sahab', 'owner', owner_pw, 'owner', 'Management'))

    cur.execute("""
        INSERT INTO users (name, username, password, role, dept)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (username) DO NOTHING
    """, ('Manager Ji', 'manager', mgr_pw, 'manager', 'HR'))

    # Default settings
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                ('company_name', 'My Office'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                ('annual_leaves', '12'))

    # Sample employees
    for e in [
        ('Amit Kumar',   'Sales',    'Executive',       25000, '2023-01-10', '9876543210'),
        ('Sunita Devi',  'Accounts', 'Accountant',      22000, '2023-03-15', '9876543211'),
        ('Ravi Verma',   'IT',       'Developer',       30000, '2022-11-01', '9876543212'),
        ('Pooja Yadav',  'HR',       'HR Executive',    20000, '2024-01-05', '9876543213'),
        ('Deepak Jha',   'Sales',    'Sr. Executive',   23000, '2023-06-20', '9876543214'),
        ('Kavita Mishra','Admin',    'Admin Assistant', 18000, '2023-09-12', '9876543215'),
    ]:
        cur.execute("""
            INSERT INTO employees (name, dept, designation, salary, join_date, phone)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, e)

    db.commit()
    cur.close()
    db.close()
    print("Database ready!")
