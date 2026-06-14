from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3

from fpdf import FPDF   # for generating PDFs
import io               # for in-memory PDF file
from flask import send_file
from datetime import datetime, timedelta  # for date filters

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for sessions & flash messages

# ===== Database connection =====
def get_db():
    conn = sqlite3.connect("bank.db")
    conn.row_factory = sqlite3.Row
    return conn

# ===== Initialize DB =====
@app.route("/init-db")
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        first_name TEXT,
        last_name TEXT,
        id_number TEXT,
        account_number TEXT UNIQUE,
        account_type TEXT,
        balance INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user',
        status TEXT DEFAULT 'active'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_number TEXT,
        type TEXT,
        amount INTEGER,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        from_account TEXT,
        to_account TEXT                
    )
    """)
    cur.execute("""
   CREATE TABLE IF NOT EXISTS fraud_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        account_number TEXT,
        reason TEXT,
        amount REAL,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        action TEXT DEFAULT NULL,
        from_account TEXT DEFAULT NULL,
        to_account TEXT DEFAULT NULL,
        type TEXT DEFAULT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()
    return "Database initialized!"

# ===== Fraud Detection =====
def check_fraud(cur, account_number, amount, tx_type=None, from_acc=None, to_acc=None):
    # Fetch user id
    cur.execute("SELECT id FROM users WHERE account_number = ?", (account_number,))
    user_row = cur.fetchone()
    if not user_row:
        return False  # Account doesn't exist

    user_id = user_row['id']

    # Rule 1: Large transaction
    if amount > 100000:
        cur.execute("UPDATE users SET status='suspended' WHERE account_number=?", (account_number,))
        cur.execute(
            "INSERT INTO fraud_alerts (user_id, account_number, reason, amount, status, type, from_account, to_account) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, account_number, "Large transaction detected", amount, 'pending', tx_type, from_acc, to_acc)
        )
        return True

    # Rule 2: 3 transactions within 5 minutes
    cur.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE account_number = ?
        AND datetime(date) >= datetime('now','-5 minutes')
    """, (account_number,))
    count = cur.fetchone()[0]

    if count >= 3:
        cur.execute("UPDATE users SET status='suspended' WHERE account_number=?", (account_number,))
        cur.execute(
            "INSERT INTO fraud_alerts (user_id, account_number, reason, amount, status, type, from_account, to_account) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, account_number, "Multiple rapid transactions", amount, 'pending', tx_type, from_acc, to_acc)
        )
        return True

    return False


# ===== Home / Login page =====
@app.route('/')
def home():
    return render_template('login.html')

# ===== Login =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cur.fetchone()
        conn.close()

        if user:
            session['username'] = username

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard', username=username))
        else:
            return render_template(
                'login.html',
                message="Invalid username or password!"
            )

    return render_template('login.html')


# ===== User Dashboard =====
@app.route('/dashboard')
def dashboard():
    username = session.get('username')
    if not username:
        return redirect(url_for('home'))

    conn = get_db()
    cur = conn.cursor()

    # 1️⃣ Get logged-in user
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return redirect(url_for('home'))

    # 2️⃣ Get user's transaction history
    cur.execute("""
        SELECT type, amount, date, from_account, to_account
        FROM transactions
        WHERE account_number = ?
        ORDER BY date DESC
    """, (user['account_number'],))
    transactions = cur.fetchall()

    # 3️⃣ Get user's fraud alerts (most recent first)
    cur.execute("""
        SELECT id, reason, amount, date, status, action
        FROM fraud_alerts
        WHERE account_number = ?
        ORDER BY date DESC
    """, (user['account_number'],))
    alerts = cur.fetchall()

    conn.close()

    # 4️⃣ Render template
    return render_template(
        'dashboard.html',
        user=user,
        transactions=transactions,
        alerts=alerts  # pass alerts to HTML
    )

# ===== User appeals a fraud alert =====
@app.route('/appeal_alert', methods=['POST'])
def appeal_alert():
    username = session.get('username')
    if not username:
        return redirect(url_for('home'))

    alert_id = request.form.get('alert_id')
    if not alert_id:
        flash("Invalid alert.")
        return redirect(url_for('dashboard'))

    conn = get_db()
    cur = conn.cursor()

    # Get user's account number
    cur.execute("SELECT account_number FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    if not user:
        conn.close()
        flash("User not found.")
        return redirect(url_for('home'))

    account_number = user['account_number']

    # Get current alert details
    cur.execute("SELECT status, action FROM fraud_alerts WHERE id = ? AND account_number = ?", (alert_id, account_number))
    alert = cur.fetchone()
    if not alert:
        conn.close()
        flash("Alert not found.")
        return redirect(url_for('dashboard'))

    current_action = alert['action']

    # Only allow appeal if action allows it
    if current_action not in [None, 'investigating', 'frozen']:
        conn.close()
        flash("You cannot appeal this alert.")
        return redirect(url_for('dashboard'))

    # ✅ Record the appeal
    cur.execute("""
        UPDATE fraud_alerts
        SET action='appealed'
        WHERE id=? AND account_number=?
    """, (alert_id, account_number))

    conn.commit()
    conn.close()

    flash("Your appeal has been submitted. Admin will review it shortly.")
    return redirect(url_for('dashboard'))

# ===== Admin Dashboard =====
from collections import defaultdict
from datetime import datetime
from flask import flash

@app.route('/admin')
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()

    # ===== Fetch all users =====
    cur.execute("SELECT * FROM users")
    all_users = cur.fetchall()

   # ===== Fraud alerts =====
    # Fetch alerts for display
    cur.execute("SELECT * FROM fraud_alerts ORDER BY date DESC")
    fraud_alerts = cur.fetchall()

    # Count unread alerts for notification badge
    cur.execute("SELECT COUNT(*) FROM fraud_alerts WHERE status='pending' OR action='appealed'")
    alert_count = cur.fetchone()[0]

    # Fetch unread alerts for dropdown
    cur.execute("""
        SELECT f.*, u.username
        FROM fraud_alerts f
        JOIN users u ON f.account_number = u.account_number
        WHERE f.status='pending' OR f.action='appealed'
        ORDER BY f.date DESC
    """)
    new_alerts = cur.fetchall()

    # ===== KPIs =====
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM transactions")
    total_transactions = cur.fetchone()[0]

    cur.execute("SELECT SUM(amount) FROM transactions WHERE type='deposit'")
    total_deposits = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(amount) FROM transactions WHERE type='withdraw'")
    total_withdrawals = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(amount) FROM transactions WHERE type IN ('transfer_out','transfer_in')")
    total_transfers = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(balance) FROM users")
    total_bank_balance = cur.fetchone()[0] or 0

    # ===== Transactions by Date =====
    cur.execute("SELECT type, amount, date FROM transactions ORDER BY date ASC")
    transactions = cur.fetchall()

    deposits_by_date = defaultdict(int)
    withdrawals_by_date = defaultdict(int)
    transfers_by_date = defaultdict(int)
    total_by_date = defaultdict(int)

    for t in transactions:
        date_str = t[2][:10] if isinstance(t[2], str) else t[2].date().isoformat()
        if t[0] == 'deposit':
            deposits_by_date[date_str] += t[1]
        elif t[0] == 'withdraw':
            withdrawals_by_date[date_str] += t[1]
        elif t[0] in ('transfer_out', 'transfer_in'):
            transfers_by_date[date_str] += t[1]
        total_by_date[date_str] += t[1]

    sorted_dates = sorted(total_by_date.keys())
    transaction_dates = sorted_dates
    transaction_counts = [total_by_date[d] for d in sorted_dates]
    deposit_counts = [deposits_by_date[d] for d in sorted_dates]
    withdrawal_counts = [withdrawals_by_date[d] for d in sorted_dates]
    transfer_counts = [transfers_by_date[d] for d in sorted_dates]

    # ===== Bank balance cumulative =====
    balance_values = []
    cumulative_balance = 0
    for d in sorted_dates:
        cumulative_balance += total_by_date[d]
        balance_values.append(cumulative_balance)

    # ===== Account type distribution =====
    cur.execute("SELECT account_type, COUNT(*) FROM users GROUP BY account_type")
    account_type_data = cur.fetchall()
    account_types = [row[0] for row in account_type_data]
    account_type_counts = [row[1] for row in account_type_data]

    conn.close()

    # ===== Render template =====
    return render_template(
        'admin.html',
        users=all_users,
        total_users=total_users,
        total_transactions=total_transactions,
        total_deposits=total_deposits,
        total_withdrawals=total_withdrawals,
        total_transfers=total_transfers,
        total_bank_balance=total_bank_balance,
        transaction_dates=transaction_dates,
        transaction_counts=transaction_counts,
        deposit_counts=deposit_counts,
        withdrawal_counts=withdrawal_counts,
        transfer_counts=transfer_counts,
        balance_dates=sorted_dates,
        balance_values=balance_values,
        account_types=account_types,
        account_type_counts=account_type_counts,
        fraud_alerts=fraud_alerts,
        new_alerts=new_alerts,
        alert_count=alert_count
    )

# ===== Signup / Create User =====
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        first_name = request.form["first_name"].strip()
        last_name = request.form["last_name"].strip()
        id_number = request.form["id_number"]
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        confirm_password = request.form["confirm_password"].strip()
        account_type = request.form["account_type"].strip()

        if password != confirm_password:
            return render_template(
                "signup.html",
                message="Passwords do not match!"
            )
        
        conn = get_db()
        cur = conn.cursor()

        # Generate account number
        cur.execute("SELECT account_number FROM users ORDER BY id DESC LIMIT 1")
        last = cur.fetchone()
        if last:
            new_account_number = str(int(last["account_number"]) + 1)
        else:
            new_account_number = "301120060001"

        try:
            cur.execute("""
                INSERT INTO users (username, password, first_name, last_name, id_number, account_number, account_type, balance, role, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, password, first_name, last_name, id_number, new_account_number, account_type, 0, "user", "active"))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template(
                "signup.html",
                message="Username or account number already exists!"
            )

        conn.close()
        return render_template(
            "signup.html",
            message="User account created successfully!"
        )

    return render_template("signup.html")

# ===== Deposit =====
@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if request.method == 'POST':
        account_number = request.form.get('account_number', '').strip()
        try:
            amount = int(request.form.get('amount'))
        except (ValueError, TypeError):
            return render_template('deposit.html', message="Enter a valid amount!")

        if amount <= 0:
            return render_template('deposit.html', message="Amount must be greater than zero!")

        # Use one connection per request
        with get_db() as conn:
            cur = conn.cursor()

            # Fetch user
            cur.execute("SELECT first_name, balance FROM users WHERE account_number = ?", (account_number,))
            user = cur.fetchone()
            if not user:
                return render_template('deposit.html', message="Account not found!")

            # Check fraud
            if check_fraud(cur, account_number, amount, 'deposit', account_number, None):
                conn.commit()
                return render_template('deposit.html', message="⚠ Transaction flagged. Account suspended for review.")

            # Update balance
            new_balance = user['balance'] + amount
            cur.execute("UPDATE users SET balance = ? WHERE account_number = ?", (new_balance, account_number))

            # Log transaction
            cur.execute("INSERT INTO transactions (account_number, type, amount) VALUES (?, 'deposit', ?)",
                        (account_number, amount))

            conn.commit()

        return render_template('deposit.html', message=f"Deposited KES {amount:,} successfully to {user['first_name']}!")

    return render_template('deposit.html')


# ===== Withdraw =====
@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    username = session.get('username')
    if not username:
        return redirect(url_for('home'))

    message = None
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if not user:
            return redirect(url_for('home'))

        if user['status'] == 'suspended':
            return render_template('withdraw.html', message="Your account is suspended. You cannot withdraw.", user=user)

        if request.method == 'POST':
            try:
                amount = int(request.form.get('amount'))
            except (ValueError, TypeError):
                message = "Enter a valid amount!"
                return render_template('withdraw.html', message=message, user=user)

            if amount <= 0:
                message = "Amount must be greater than zero!"
                return render_template('withdraw.html', message=message, user=user)

            if user['balance'] < amount:
                message = "Insufficient balance!"
                return render_template('withdraw.html', message=message, user=user)

            # Fraud check
            if check_fraud(cur, user['account_number'], amount, 'withdraw', user['account_number'], None):
                conn.commit()
                return render_template('withdraw.html', message="⚠ Suspicious activity detected. Account suspended.", user=user)

            # Deduct balance and log transaction atomically
            cur.execute("UPDATE users SET balance = balance - ? WHERE account_number = ?", (amount, user['account_number']))
            cur.execute("INSERT INTO transactions (account_number, type, amount) VALUES (?, 'withdraw', ?)",
                        (user['account_number'], amount))

            conn.commit()

            # Refresh user balance
            cur.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            message = f"Withdrew KES {amount:,} successfully!"

    return render_template('withdraw.html', message=message, user=user)



# ===== Transfer =====
@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    username = session.get('username')
    if not username:
        return redirect(url_for('home'))

    message = None
    with get_db() as conn:
        cur = conn.cursor()

        # Sender
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        sender = cur.fetchone()
        if not sender:
            return redirect(url_for('home'))

        if sender['status'] == 'suspended':
            return render_template('transfer.html', user=sender, message="Your account is suspended. Cannot transfer.")

        if request.method == 'POST':
            from_account = sender['account_number']
            to_account = request.form.get('to_account', '').strip()
            try:
                amount = int(request.form.get('amount'))
            except (ValueError, TypeError):
                return render_template('transfer.html', user=sender, message="Enter a valid amount!")

            if amount <= 0:
                return render_template('transfer.html', user=sender, message="Amount must be greater than zero!")

            if from_account == to_account:
                return render_template('transfer.html', user=sender, message="Sender and receiver must be different!")

            # Receiver
            cur.execute("SELECT * FROM users WHERE account_number = ?", (to_account,))
            receiver = cur.fetchone()
            if not receiver:
                return render_template('transfer.html', user=sender, message="Invalid recipient account!")

            if sender['balance'] < amount:
                return render_template('transfer.html', user=sender, message="Insufficient funds!")

            # Fraud check
            if check_fraud(cur, from_account, amount, 'transfer', from_account, to_account):
                conn.commit()
                return render_template('transfer.html', user=sender, message="⚠ Suspicious activity detected. Account suspended.")

            # Perform transfer atomically
            cur.execute("UPDATE users SET balance = balance - ? WHERE account_number = ?", (amount, from_account))
            cur.execute("UPDATE users SET balance = balance + ? WHERE account_number = ?", (amount, to_account))

            # Log transactions
            cur.execute("""INSERT INTO transactions (account_number, type, amount, from_account, to_account)
                           VALUES (?, 'transfer_out', ?, ?, ?)""", (from_account, amount, from_account, to_account))
            cur.execute("""INSERT INTO transactions (account_number, type, amount, from_account, to_account)
                           VALUES (?, 'transfer_in', ?, ?, ?)""", (to_account, amount, from_account, to_account))

            conn.commit()
            message = f"Transferred KES {amount:,} to {receiver['first_name']} {receiver['last_name']}!"

    return render_template('transfer.html', user=sender, message=message)

# ===== View Users (Admin) =====
@app.route('/view_users')
def view_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    all_users = cur.fetchall()
    conn.close()
    return render_template('view_users.html', users=all_users)


# ===== Manage User (Admin) with Fraud Review =====
@app.route('/manage/<account_number>', methods=['GET', 'POST'])
def manage_user(account_number):
    conn = get_db()
    cur = conn.cursor()

    # 1️⃣ Fetch user
    cur.execute("SELECT * FROM users WHERE account_number = ?", (account_number,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return "User not found! <a href='/admin'>Go back</a>"

    message = None

    # 2️⃣ Handle Fraud Review Actions
    if request.method == 'POST':
        action = request.form.get('action')
        alert_id = request.form.get('alert_id')

        if alert_id and action:
            # Fetch the specific alert
            cur.execute("SELECT * FROM fraud_alerts WHERE id = ?", (alert_id,))
            alert = cur.fetchone()

            if alert:
                alert_acc = alert['account_number']
                tx_type = alert['type']
                amount = alert['amount']
                from_acc = alert['from_account']
                to_acc = alert['to_account']

                if action == 'legitimate':
                    try:
                        # ----- Deposit -----
                        if tx_type == 'deposit':
                            cur.execute(
                                "UPDATE users SET balance = balance + ? WHERE account_number=?",
                                (amount, alert_acc)
                            )
                            cur.execute(
                                "INSERT INTO transactions (account_number, type, amount) VALUES (?, 'deposit', ?)",
                                (alert_acc, amount)
                            )

                        # ----- Withdrawal -----
                        elif tx_type == 'withdraw':
                            cur.execute(
                                "UPDATE users SET balance = balance - ? WHERE account_number=?",
                                (amount, alert_acc)
                            )
                            cur.execute(
                                "INSERT INTO transactions (account_number, type, amount) VALUES (?, 'withdraw', ?)",
                                (alert_acc, amount)
                            )

                        # ----- Transfer -----
                        elif tx_type in ('transfer', 'transfer_out', 'transfer_in'):
                            if from_acc and to_acc:
                                # Deduct from sender
                                cur.execute(
                                    "UPDATE users SET balance = balance - ? WHERE account_number=?",
                                    (amount, from_acc)
                                )
                                # Add to receiver
                                cur.execute(
                                    "UPDATE users SET balance = balance + ? WHERE account_number=?",
                                    (amount, to_acc)
                                )
                                # Log transactions
                                cur.execute(
                                    "INSERT INTO transactions (account_number, type, amount, from_account, to_account) "
                                    "VALUES (?, 'transfer_out', ?, ?, ?)",
                                    (from_acc, amount, from_acc, to_acc)
                                )
                                cur.execute(
                                    "INSERT INTO transactions (account_number, type, amount, from_account, to_account) "
                                    "VALUES (?, 'transfer_in', ?, ?, ?)",
                                    (to_acc, amount, from_acc, to_acc)
                                )

                        # Activate account
                        cur.execute(
                            "UPDATE users SET status='active' WHERE account_number=?",
                            (alert_acc,)
                        )

                        # Mark alert as reviewed
                        cur.execute(
                            "UPDATE fraud_alerts SET status='reviewed', action='legitimate' WHERE id=?",
                            (alert_id,)
                        )

                        message = f"Alert ID {alert_id} marked legitimate; transaction processed and account activated."

                    except Exception as e:
                        conn.rollback()
                        message = f"Error processing transaction: {str(e)}"

                elif action == 'investigate':
                    cur.execute(
                        "UPDATE fraud_alerts SET status='reviewed', action='investigating' WHERE id=?",
                        (alert_id,)
                    )
                    message = f"Alert ID {alert_id} flagged for investigation. Account remains suspended."

                elif action == 'freeze':
                    cur.execute(
                        "UPDATE users SET status='suspended' WHERE account_number=?",
                        (alert_acc,)
                    )
                    cur.execute(
                        "UPDATE fraud_alerts SET status='reviewed', action='frozen' WHERE id=?",
                        (alert_id,)
                    )
                    message = f"Alert ID {alert_id} confirmed; account frozen."

                conn.commit()

    # 3️⃣ Fetch updated transactions & alerts
    cur.execute(
        "SELECT * FROM transactions WHERE account_number=? ORDER BY date DESC",
        (user['account_number'],)
    )
    transactions = cur.fetchall()

    cur.execute(
        "SELECT * FROM fraud_alerts WHERE account_number=? ORDER BY date DESC",
        (user['account_number'],)
    )
    alerts = cur.fetchall()

    conn.close()

    # 4️⃣ Render template
    return render_template(
        'manage_user.html',
        user=user,
        transactions=transactions,
        alerts=alerts,
        message=message
    )

# ===== Toggle Status =====
@app.route('/toggle_status/<account_number>', methods=['POST'])
def toggle_status(account_number):
    conn = get_db()
    cur = conn.cursor()

    # Get current status
    cur.execute("SELECT status FROM users WHERE account_number = ?", (account_number,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return "User not found! <a href='/admin'>Go back</a>"

    # Toggle status
    new_status = 'suspended' if user['status'] == 'active' else 'active'
    cur.execute("UPDATE users SET status = ? WHERE account_number = ?", (new_status, account_number))
    conn.commit()
    conn.close()

    # Redirect back to manage page using account_number
    return redirect(url_for('manage_user', account_number=account_number))

# ===== Forgot Password =====
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username'].strip()
        account_number = request.form['account_number'].strip()
        id_number = request.form['id_number'].strip()
        new_password = request.form['new_password'].strip()
        confirm_password = request.form['confirm_password'].strip()

        if new_password != confirm_password:
            return render_template(
                'forgot_password.html',
                message="Passwords do not match!"
            )

        conn = get_db()
        cur = conn.cursor()

        # Verify user with multiple details
        cur.execute("""
            SELECT * FROM users
            WHERE username = ?
              AND account_number = ?
              AND id_number = ?
        """, (username, account_number, id_number))

        user = cur.fetchone()

        if not user:
            conn.close()
            return render_template(
                'forgot_password.html',
                message="Details do not match any account!"
            )

        # Update password
        cur.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (new_password, username)
        )
        conn.commit()
        conn.close()

        return render_template(
            'forgot_password.html',
            success=True,
            message="Password reset successful! Redirecting to login..."
        )

    return render_template('forgot_password.html')

# ===== FDownload pdf =====
@app.route('/download_pdf', methods=['GET', 'POST'])
def download_pdf():
    username = session.get('username')
    if not username:
        return redirect(url_for('home'))

    conn = get_db()
    cur = conn.cursor()

    # Get logged-in user info
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return redirect(url_for('home'))

    # ===== Handle Filters =====
    filter_option = request.form.get('filter_option')  # past30days, past14days, custom
    start_date = None
    end_date = datetime.now().strftime('%Y-%m-%d')  # default to today

    if filter_option == 'past30days':
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    elif filter_option == 'past14days':
        start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    elif filter_option == 'custom':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

    tx_type = request.form.get('tx_type')  # deposit, withdraw, transfer_out, transfer_in, or empty

    # ===== Build query dynamically =====
    query = "SELECT type, amount, date, from_account, to_account FROM transactions WHERE account_number = ?"
    params = [user['account_number']]

    if start_date:
        query += " AND date(date) >= date(?)"
        params.append(start_date)
    if end_date:
        query += " AND date(date) <= date(?)"
        params.append(end_date)
    if tx_type:
        query += " AND type = ?"
        params.append(tx_type)

    query += " ORDER BY date DESC"
    cur.execute(query, params)
    transactions = cur.fetchall()
    conn.close()

    # ===== Generate PDF =====
    pdf = FPDF()
    pdf.add_page()

    # Bank Logo (adjust path & size if needed)
    pdf.image('static/images/logo.png', x=10, y=8, w=33)

    # Title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"{user['first_name']} {user['last_name']}'s Transaction History", ln=True, align='C')
    pdf.ln(5)

    # Account info
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Account Number: {user['account_number']} | Balance: KES {user['balance']:,}", ln=True, align='C')
    if start_date and end_date:
        pdf.cell(0, 10, f"Transactions from {start_date} to {end_date}", ln=True, align='C')
    pdf.ln(10)

    # Table headers
    pdf.set_font("Arial", "B", 12)
    pdf.cell(45, 10, "Date", border=1)
    pdf.cell(30, 10, "Type", border=1)
    pdf.cell(30, 10, "Amount", border=1)
    pdf.cell(45, 10, "From", border=1)
    pdf.cell(45, 10, "To", border=1)
    pdf.ln()

    # Table rows
    pdf.set_font("Arial", "", 12)
    for tx in transactions:
        pdf.cell(45, 10, str(tx['date']), border=1)
        pdf.cell(30, 10, tx['type'], border=1)
        pdf.cell(30, 10, f"KES {tx['amount']:,}", border=1)
        pdf.cell(45, 10, tx['from_account'] if tx['from_account'] else "-", border=1)
        pdf.cell(45, 10, tx['to_account'] if tx['to_account'] else "-", border=1)
        pdf.ln()

    # Save PDF in memory
    pdf_file = io.BytesIO()
    pdf.output(pdf_file)
    pdf_file.seek(0)

    return send_file(pdf_file, download_name=f"{user['username']}_transactions.pdf", as_attachment=True)


# ===== Run App =====
if __name__ == '__main__':
    app.run(debug=True)
