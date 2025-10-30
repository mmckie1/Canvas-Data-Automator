# 🎓 Canvas Data Automator (V4 – SQL Developer Style)

**Canvas Data Automator V4** is a Python-based desktop application built with **CustomTkinter**, **SQLAlchemy**, and **Pandas** to automate complex data extraction and reporting from **Instructure’s Canvas Data 2 / Redshift**.  
It features a **modern SQL Developer–style interface** with secure credential management, real-time progress tracking, and Excel export capabilities — empowering LMS administrators and data teams to run advanced forensic reports with ease.

---

## 🖼️ Screenshots

### 🏠 Main Dashboard
![Canvas Data Automator Main UI](https://github.com/mmckie1/Canvas-Data-Automator/blob/test/imgs/Screenshot%202025-10-30%20131639.png?raw=true)

> **Home view:** Start by adding a database connection.  
> The left sidebar lists active connections, and the main workspace serves as the SQL and results area.

---

### 🔑 Add Database Connection
![Add Database Connection Dialog](./78863bd1-5c5e-404e-a45a-a5127e65ff5d.png)
> **Secure connection setup:** Enter your database credentials (PostgreSQL or Redshift).  
> Credentials can be securely stored using your system keyring.

---

## 🚀 Features

- 💻 **Modern Dark UI** (CustomTkinter)
- 🔐 **Secure credential storage** using `keyring`
- 🧠 **Predefined SQL queries:**
  - **Activity Logs:** Track user web activity, sessions, and IPs  
  - **Submissions Logs:** Correlate assignment submissions to forensic events
- ⚡ **Live query progress tracking**
- 📊 **Automatic Excel export** with timestamped filenames
- 🧭 **IP Geolocation** integration (optional)
- 🧩 **Multiple database connections** in one session
- 🎨 **SQL Developer–style dual panels** (query editor + results console)

---

## 🧰 Tech Stack

| Category | Tools / Libraries |
|-----------|------------------|
| UI | `customtkinter`, `tkinter`, `CTkTextbox`, progress bars |
| Database | `SQLAlchemy`, `psycopg2-binary`, `redshift-connector` |
| Data Handling | `pandas` |
| Security | `keyring`, JSON config profile |
| Export | Excel (`pandas.to_excel`) |
| Utilities | `datetime`, `re`, `os`, `json`, `pathlib`, `time` |

---

## ⚙️ Installation

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/<your-username>/canvas-data-automator.git
cd canvas-data-automator
```

### 2️⃣ Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
```

### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install pandas customtkinter SQLAlchemy redshift-connector sqlalchemy-redshift psycopg2-binary keyring
```

## 🧾 requirements.txt
If you need to recreate this file, use:
```text
pandas
customtkinter
SQLAlchemy
redshift-connector
sqlalchemy-redshift
psycopg2-binary
keyring
```

## 🧑‍💻 Usage
Launch the app:
```bash
python canvasdata_dual_queries_secure_V4_SQLStyle.py
```

### Workflow

<ol>
  <li>Add Connection – Enter your database credentials (PostgreSQL/Redshift).</li>
  <li>Run Query – Choose between Activity Logs or Submissions.</li>
  <li>Set Parameters – Enter username and date range.</li>
  <li>Execute – The query runs with live progress feedback.</li>
  <li>Export – Results automatically save to Excel in the same directory.</li>
</ol>

## 📁 Example Export Files

- ActivityLogs_jdoe_20251030_104512.xlsx
- SubmissionsLogs_jdoe_20251030_104812.xlsx
- Each file includes timestamped user activity, course context, and submission data.

## 🔐 Security

-Passwords are encrypted via the system keyring — never stored in plaintext.
-Connection settings are saved in canvas_config.json (no passwords).
-The app never sends data to external servers.



