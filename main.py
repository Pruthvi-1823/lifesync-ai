from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import sqlite3
import re
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LifeSync AI Complete Backend", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_connection():
    conn = sqlite3.connect("lifesync.db")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    """Adds necessary columns if they don't exist yet (safe to run every start)."""
    conn = sqlite3.connect("lifesync.db")
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  
    
    try:
        conn.execute("ALTER TABLE shared_splits ADD COLUMN is_settled INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


ensure_schema()


class ChatRequest(BaseModel):
    user_id: int
    message: str


@app.get("/")
def home():
    return {"message": "Welcome to LifeSync AI Backend! Full Feature Set Online."}


@app.get("/buckets/{user_id}")
def get_user_buckets(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute("SELECT * FROM money_buckets WHERE user_id = ?", (user_id,))
    buckets = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM tasks WHERE user_id = ? AND is_completed = 0", (user_id,))
    tasks = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM shared_splits WHERE user_id = ? AND is_settled = 0", (user_id,))
    splits = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {"user": dict(user), "buckets": buckets, "active_tasks": tasks, "pending_splits": splits}


@app.post("/aura-chat")
def aura_chat(req: ChatRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    msg = req.message.lower()

    if "briefing" in msg or "day looking" in msg or "summary" in msg:
        cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE user_id = ? AND is_completed = 0", (req.user_id,))
        task_count = cursor.fetchone()["count"]

        cursor.execute("SELECT friend_name, amount_owed FROM shared_splits WHERE user_id = ? AND is_settled = 0", (req.user_id,))
        pending_debts = cursor.fetchall()

        debt_text = ", ".join([f"{d['friend_name']} owes you ₹{d['amount_owed']}" for d in pending_debts]) if pending_debts else "No pending shared expenses."

        conn.close()
        return {
            "aura_response": f"☀ Morning Briefing: You have {task_count} pending tasks on your schedule. Financial overview: {debt_text}. All your savings buckets are securely locked and protected!"
        }

    if "remind" in msg or "task" in msg or "todo" in msg:
        task_title = req.message.replace("remind me to", "").replace("add task", "").strip()
        priority = "High" if "urgent" in msg or "project" in msg else "Medium"

        cursor.execute("INSERT INTO tasks (user_id, title, priority) VALUES (?, ?, ?)", (req.user_id, task_title, priority))
        conn.commit()
        conn.close()
        return {
            "aura_response": f"📝 Task Added: Successfully logged '{task_title}' with {priority} Priority to your task list."
        }

    if "can i" in msg or "afford" in msg or "should i buy" in msg:
        match_amt = re.search(r'(\d+)', msg)
        amount = float(match_amt.group(1)) if match_amt else 0.0

        cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name = 'Spendable'", (req.user_id,))
        spendable_bucket = cursor.fetchone()

        if spendable_bucket:
            current_spendable = spendable_bucket["allocated_amount"]
            conn.close()
            if amount <= current_spendable:
                return {
                    "aura_response": f"🟢 Green Light, Alex! Your Spendable balance is ₹{current_spendable:,.0f}. Spending ₹{amount:,.0f} is completely safe and won't affect your locked savings."
                }
            else:
                shortfall = amount - current_spendable
                conn.close()
                return {
                    "aura_response": f"⚠️ Guardrail Warning: You want to spend ₹{amount:,.0f}, but your Spendable balance is only ₹{current_spendable:,.0f}. This purchase exceeds your available funds by ₹{shortfall:,.0f}. It's best to skip this purchase!"
                }

    if "split" in msg or "with" in msg and ("paid" in msg or "spent" in msg):
        match_amt = re.search(r'(?:paid|spent)\s*(\d+)', msg)
        amount = float(match_amt.group(1)) if match_amt else 0.0

        friend_name = "Friend"
        with_match = re.search(r'with\s+([a-zA-Z]+)', req.message)
        if with_match:
            friend_name = with_match.group(1).capitalize()
        else:
            words = req.message.split()
            for word in words:
                clean_word = re.sub(r'[^a-zA-Z]', '', word)
                if clean_word and clean_word[0].isupper() and clean_word.lower() not in ['i', 'for', 'with', 'paid', 'spent', 'rs', 'in']:
                    friend_name = clean_word
                    break

        split_amount = amount / 2

        cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name = 'Spendable'", (req.user_id,))
        spendable_bucket = cursor.fetchone()

        if spendable_bucket:
            current_spendable = spendable_bucket["allocated_amount"]
            bucket_id = spendable_bucket["id"]
            new_spendable = current_spendable - amount
            cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE id = ?", (new_spendable, bucket_id))
            
            # Also deduct from user's total balance on split payments
            cursor.execute("UPDATE users SET total_balance = total_balance - ? WHERE id = ?", (amount, req.user_id))

        cursor.execute("INSERT INTO shared_splits (user_id, friend_name, amount_owed, description) VALUES (?, ?, ?, ?)",
                       (req.user_id, friend_name, split_amount, req.message))
        conn.commit()
        conn.close()

        return {
            "aura_response": f"🤝 Bill Split Logged: You paid ₹{amount:,.0f} (deducted from your Spendable balance). {friend_name} owes you ₹{split_amount:,.0f}—added to your shared ledger!"
        }

    if "balance" in msg or "income" in msg or "earned" in msg:
        match_str = re.search(r'([\d,]+)', msg)
        amount = float(match_str.group(1).replace(',', '')) if match_str else 0.0

        cursor.execute("UPDATE users SET total_balance = ? WHERE id = ?", (amount, req.user_id))

        spendable_amt = amount * 0.4
        locked_amt = amount * 0.6

        cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE user_id = ? AND bucket_name = 'Spendable'", (spendable_amt, req.user_id))
        cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE user_id = ? AND bucket_name != 'Spendable'", (locked_amt / 3, req.user_id))

        conn.commit()
        conn.close()
        return {
            "aura_response": f"🚀 Financial Reset Successful: Total balance updated to ₹{amount:,.0f}. Your Spendable budget has been updated to ₹{spendable_amt:,.0f} and savings buckets have been proportionally locked!"
        }

    if "create bucket" in msg or "add bucket" in msg:
        match_amt = re.search(r'(\d+)', msg)
        amount = float(match_amt.group(1)) if match_amt else 1000.0

        cleaned_msg = re.sub(r'(create|add|bucket|for|with|₹|\d+)', '', req.message, flags=re.IGNORECASE).strip()
        bucket_name = cleaned_msg.title() if cleaned_msg else "Custom Bucket"

        cursor.execute("INSERT INTO money_buckets (user_id, bucket_name, allocated_amount, is_locked) VALUES (?, ?, ?, 1)",
                       (req.user_id, bucket_name, amount))

        cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name = 'Spendable'", (req.user_id,))
        spendable_bucket = cursor.fetchone()
        if spendable_bucket:
            current_spendable = spendable_bucket["allocated_amount"]
            new_spendable = current_spendable - amount
            cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE id = ?", (new_spendable, spendable_bucket["id"]))

        conn.commit()
        conn.close()
        return {
            "aura_response": f"✨ Bucket Created & Funded: Added locked savings bucket '{bucket_name}' with ₹{amount:,.0f}. This amount was securely funded by deducting from your Spendable balance."
        }

    if "remove" in msg or "delete" in msg or "drop" in msg:
        cleaned_msg = re.sub(r'(remove|delete|drop|bucket|the)', '', req.message, flags=re.IGNORECASE).strip()

        if cleaned_msg:
            cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name LIKE ? AND LOWER(bucket_name) != 'spendable'", (req.user_id, f"%{cleaned_msg}%"))
            bucket = cursor.fetchone()

            if bucket:
                bucket_amount = bucket["allocated_amount"]
                bucket_name = bucket["bucket_name"]

                cursor.execute("DELETE FROM money_buckets WHERE id = ?", (bucket["id"],))

                cursor.execute("""
                    UPDATE money_buckets 
                    SET allocated_amount = allocated_amount + ? 
                    WHERE user_id = ? AND LOWER(bucket_name) = 'spendable'
                """, (bucket_amount, req.user_id))

                conn.commit()
                conn.close()
                return {
                    "aura_response": f"🗑️ Bucket Removed: Successfully deleted '{bucket_name}' and reallocated ₹{bucket_amount:,.0f} back to your Spendable balance."
                }
            else:
                conn.close()
                return {
                    "aura_response": f"⚠️ I couldn't find a removable savings bucket matching '{cleaned_msg}'."
                }

    if "reset" in msg or ("update" in msg and "bucket" in msg) or ("set" in msg and "bucket" in msg):
        match_amt = re.search(r'(\d+)', msg)
        new_amount = float(match_amt.group(1)) if match_amt else 0.0

        cleaned_msg = re.sub(r'(reset|update|set|bucket|to|for|₹|\d+)', '', req.message, flags=re.IGNORECASE).strip()

        if cleaned_msg:
            cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name LIKE ?", (req.user_id, f"%{cleaned_msg}%"))
            bucket = cursor.fetchone()

            if bucket:
                old_amount = bucket["allocated_amount"]
                diff = new_amount - old_amount

                cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE id = ?", (new_amount, bucket["id"]))

                cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name = 'Spendable'", (req.user_id,))
                spendable_bucket = cursor.fetchone()
                if spendable_bucket:
                    current_spendable = spendable_bucket["allocated_amount"]
                    new_spendable = current_spendable - diff
                    cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE id = ?", (new_spendable, spendable_bucket["id"]))

                conn.commit()
                conn.close()
                return {
                    "aura_response": f"🔄 Budget Balanced: Updated '{bucket['bucket_name']}' to ₹{new_amount:,.0f} and adjusted your Spendable balance accordingly."
                }
            else:
                conn.close()
                return {
                    "aura_response": f"⚠️ I couldn't find a bucket matching '{cleaned_msg}'. Please check your bucket names and try again."
                }
        else:
            conn.close()
            return {
                "aura_response": "⚠️ Please specify which bucket to update, for example: 'reset education bucket to 50000'."
            }

    match_exp = re.search(r'(?:spent|paid|cost)\s*(\d+)', msg)
    if match_exp:
        amount = float(match_exp.group(1))
        cursor.execute("SELECT * FROM money_buckets WHERE user_id = ? AND bucket_name = 'Spendable'", (req.user_id,))
        spendable_bucket = cursor.fetchone()

        if not spendable_bucket:
            conn.close()
            return {"aura_response": "Spendable bucket not found."}

        current_spendable = spendable_bucket["allocated_amount"]
        bucket_id = spendable_bucket["id"]

        if amount > current_spendable:
            shortfall = amount - current_spendable
            conn.close()
            return {
                "aura_response": f"⚠ Guardrail Alert: You're trying to spend ₹{amount:,.0f}, but your Spendable balance is only ₹{current_spendable:,.0f}. This transaction would dip ₹{shortfall:,.0f} into your locked savings!"
            }

        new_spendable = current_spendable - amount
        cursor.execute("UPDATE money_buckets SET allocated_amount = ? WHERE id = ?", (new_spendable, bucket_id))
        
        # 🌟 Deduct from Total Balance as well
        cursor.execute("UPDATE users SET total_balance = total_balance - ? WHERE id = ?", (amount, req.user_id))
        
        cursor.execute("INSERT INTO expenses (user_id, amount, description, bucket_id) VALUES (?, ?, ?, ?)", (req.user_id, amount, req.message, bucket_id))
        conn.commit()
        conn.close()
        return {
            "aura_response": f"✅ Expense Logged: Deducted ₹{amount:,.0f}. Remaining spendable balance: ₹{new_spendable:,.0f}."
        }

    conn.close()
    return {
        "aura_response": "I'm Aura! You can ask me for your 'morning briefing', say 'remind me to finish my project', or log expenses like 'I spent 5000 on shoes'."
    }


# ---------------- TASK ENDPOINTS ----------------

@app.post("/tasks/update/{task_id}")
async def update_task_status(task_id: int, payload: dict):
    is_completed = payload.get("is_completed", 1)
    completed_at = datetime.now().strftime("%d %b %Y, %I:%M %p") if is_completed else None
    conn = sqlite3.connect("lifesync.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET is_completed = ?, completed_at = ? WHERE id = ?",
        (is_completed, completed_at, task_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Task {task_id} updated."}


@app.delete("/tasks/delete/{task_id}")
async def delete_task(task_id: int):
    conn = sqlite3.connect("lifesync.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Task {task_id} deleted."}


@app.get("/tasks/history/{user_id}")
async def get_task_history(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, priority, completed_at FROM tasks "
        "WHERE user_id = ? AND is_completed = 1 ORDER BY id DESC",
        (user_id,)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"completed_tasks": rows}


# ---------------- SPLIT SETTLEMENT ENDPOINT ----------------

@app.post("/splits/settle/{split_id}")
async def settle_split(split_id: int):
    """Marks a shared split as settled and credits the amount back to Spendable and Total Balance."""
    conn = sqlite3.connect("lifesync.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM shared_splits WHERE id = ?", (split_id,))
    split = cursor.fetchone()
    
    if not split:
        conn.close()
        raise HTTPException(status_code=404, detail="Split not found")
        
    if split["is_settled"] == 1:
        conn.close()
        return {"status": "success", "message": "Split already settled."}
        
    user_id = split["user_id"]
    amount_owed = split["amount_owed"]
    
    # Mark split as settled
    cursor.execute("UPDATE shared_splits SET is_settled = 1 WHERE id = ?", (split_id,))
    
    # Credit the returned amount back to the user's Spendable balance
    cursor.execute("""
        UPDATE money_buckets 
        SET allocated_amount = allocated_amount + ? 
        WHERE user_id = ? AND LOWER(bucket_name) = 'spendable'
    """, (amount_owed, user_id))
    
    # 🌟 ADD THIS: Also increase the user's total balance
    cursor.execute("""
        UPDATE users 
        SET total_balance = total_balance + ? 
        WHERE id = ?
    """, (amount_owed, user_id))
    
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Split settled and ₹{amount_owed} returned to Spendable and Total Balance."}


@app.get("/app", response_class=HTMLResponse)
def get_frontend():
    html_path = Path("index.html")
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "index.html not found in project folder!"
