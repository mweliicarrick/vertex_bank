# 🏦 Bank Management System (Flask + SQLite)

A web-based banking system built using Flask and SQLite.  
It supports user accounts, transactions, fraud detection, admin controls, and PDF transaction reports.

---

## 🚀 Features

### 👤 User Features
- User registration and login
- Deposit money
- Withdraw money
- Transfer money between accounts
- View transaction history
- Appeal fraud alerts
- Download transaction history as PDF

### 🛡️ Fraud Detection System
- Flags large transactions (above 100,000)
- Detects rapid multiple transactions within 5 minutes
- Automatically suspends suspicious accounts
- Admin review system for fraud alerts

### 🧑‍💼 Admin Features
- Admin dashboard with analytics
- View all users
- View all transactions
- Fraud alert management (approve, investigate, freeze)
- Activate or suspend user accounts
- Banking statistics (deposits, withdrawals, transfers)

---

## ⚙️ Tech Stack

- Python
- Flask
- SQLite
- HTML (Jinja2 templates)
- FPDF (PDF generation)

---

## 📂 Project Structure

app.py  
bank.db (auto-created)  

templates/  
&nbsp;&nbsp;&nbsp;&nbsp;login.html  
&nbsp;&nbsp;&nbsp;&nbsp;signup.html  
&nbsp;&nbsp;&nbsp;&nbsp;dashboard.html  
&nbsp;&nbsp;&nbsp;&nbsp;admin.html  
&nbsp;&nbsp;&nbsp;&nbsp;deposit.html  
&nbsp;&nbsp;&nbsp;&nbsp;withdraw.html  
&nbsp;&nbsp;&nbsp;&nbsp;transfer.html  
&nbsp;&nbsp;&nbsp;&nbsp;manage_user.html  
&nbsp;&nbsp;&nbsp;&nbsp;forgot_password.html  
&nbsp;&nbsp;&nbsp;&nbsp;view_users.html  

static/  
&nbsp;&nbsp;&nbsp;&nbsp;images/  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;logo.png  

---

## 🔧 Installation & Setup

### 1. Clone the repository
git clone https://github.com/mweliicarrick/vertex_bank.git  
cd bank-system  

### 2. Create virtual environment (optional)
python -m venv venv  
venv\Scripts\activate   (Windows)  
source venv/bin/activate   (Mac/Linux)  

### 3. Install dependencies
pip install flask fpdf  

### 4. Run the app
python app.py  

### 5. Open in browser
http://127.0.0.1:5000/  

---

## 🗄️ Database Setup

Initialize the database by visiting:  
http://127.0.0.1:5000/init-db  

---

## ⚠️ Disclaimer

This project is for educational purposes only and does not connect to real banking systems.

---

## 👨‍💻 Author

Built by: **Mwelii Carrick**
