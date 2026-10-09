import sqlite3

def init_db():
    conn = sqlite3.connect("lifesync.db")
    cursor = conn.cursor()

    # 1. Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            total_balance REAL DEFAULT 90000.0
        )
    """)

    # 2. Money Buckets table (Purpose-driven money)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS money_buckets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bucket_name TEXT NOT NULL,
            allocated_amount REAL NOT NULL,
            is_locked BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # 3. Expenses table linked to buckets
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            bucket_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (bucket_id) REFERENCES money_buckets (id)
        )
    """)

    # 4. Tasks table (Smart Task & Routine Triage)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'Medium',
            due_date TEXT,
            is_completed BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # 5. Shared Expenses / Bill Splitter table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shared_splits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            friend_name TEXT NOT NULL,
            amount_owed REAL NOT NULL,
            description TEXT NOT NULL,
            is_settled BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Insert default user and buckets if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (name, total_balance) VALUES ('Alex', 90000.0)")
        user_id = cursor.lastrowid
        
        default_buckets = [
            (user_id, "Education / Fees", 40000.0, 1),
            (user_id, "Emergency Fund", 25000.0, 1),
            (user_id, "Future Purchase / Down-payment", 15000.0, 1),
            (user_id, "Spendable", 10000.0, 0)
        ]
        cursor.executemany("INSERT INTO money_buckets (user_id, bucket_name, allocated_amount, is_locked) VALUES (?, ?, ?, ?)", default_buckets)

        # Default task
        cursor.execute("INSERT INTO tasks (user_id, title, priority, due_date) VALUES (?, ?, ?, ?)", 
                       (user_id, "Finish DBMS project report", "High", "Thursday"))

        # Default shared split
        cursor.execute("INSERT INTO shared_splits (user_id, friend_name, amount_owed, description) VALUES (?, ?, ?, ?)", 
                       (user_id, "Kabir", 500.0, "Dinner split"))

    conn.commit()
    conn.close()
    print("Database fully upgraded with Tasks and Bill Splitter tables!")

if __name__ == "__main__":
    init_db()