
import pandas as pd
import customtkinter as ctk
from tkinter import messagebox
from sqlalchemy import create_engine, text
from datetime import datetime
import re
import sys
import os
import keyring
import json
from pathlib import Path
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# ============================================================
# GLOBAL APPEARANCE (keep V3 styling)
# ============================================================
ctk.set_appearance_mode("dark")  # keep the existing dark theme
ctk.set_default_color_theme("blue")

# ============================================================
# STEP 0 — Package Check (same as V3)
# ============================================================
def check_required_packages():
    required_packages = {
        'sqlalchemy': 'SQLAlchemy',
        'redshift_connector': 'redshift-connector',
        'sqlalchemy_redshift': 'sqlalchemy-redshift',
        'psycopg2': 'psycopg2-binary'
    }
    
    missing_packages = []
    for package, pip_name in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(pip_name)
    
    if missing_packages:
        message = "Missing required packages:\n" + "\n".join(missing_packages)
        message += "\n\nWould you like to install them now?"
        if messagebox.askyesno("Missing Packages", message):
            try:
                import pip
                for package in missing_packages:
                    pip.main(['install', package])
                messagebox.showinfo("Success", "Packages installed successfully!")
                # Restart application needed
                if messagebox.askyesno("Restart Required", 
                    "The application needs to restart to use the new packages. Restart now?"):
                    python = sys.executable
                    os.execl(python, python, *sys.argv)
            except Exception as e:
                messagebox.showerror("Installation Error", 
                    f"Failed to install packages:\n{str(e)}\n"
                    "Please run:\npip install " + " ".join(missing_packages))
                exit()
        else:
            exit()

check_required_packages()

# ============================================================
# Credential Management (same API as V3)
# ============================================================
class CredentialManager:
    def __init__(self, profile_name: str = "default"):
        # Profile name is used to distinguish keyring entries if needed later
        self.profile_name = profile_name
        self.service_name = f"CanvasDataAutomator::{self.profile_name}"
        self.config_file = Path("canvas_config.json")  # keep single-file config to match V3
    
    def save_credentials(self, username, password, host, port, database):
        try:
            keyring.set_password(self.service_name, username, password)
            config = {
                "username": username,
                "host": host,
                "port": port,
                "database": database,
                "saved_at": datetime.now().isoformat()
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving credentials: {e}")
            return False
    
    def load_credentials(self):
        try:
            if not self.config_file.exists():
                return None
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            password = keyring.get_password(self.service_name, config["username"])
            if password:
                return {
                    "username": config["username"],
                    "password": password,
                    "host": config["host"],
                    "port": config["port"],
                    "database": config["database"],
                    "saved_at": config.get("saved_at")
                }
        except Exception as e:
            print(f"Error loading credentials: {e}")
        return None
    
    def clear_credentials(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                try:
                    keyring.delete_password(self.service_name, config["username"])
                except:
                    pass
                self.config_file.unlink()
            return True
        except Exception as e:
            print(f"Error clearing credentials: {e}")
            return False

# ============================================================
# Splash (unchanged look/feel)
# ============================================================
def splash_screen():
    splash = ctk.CTk()
    splash.title("Canvas Data Automator")
    splash.geometry("500x300")
    splash.configure(fg_color="#0e1a2b")

    label = ctk.CTkLabel(
        splash, 
        text="Canvas Data Automator",
        font=("Segoe UI", 24, "bold"),
        text_color="#99ccff"
    )
    label.pack(pady=100)

    sub = ctk.CTkLabel(
        splash,
        text="Automate data queries & exports effortlessly",
        font=("Segoe UI", 14),
        text_color="#b3cde0"
    )
    sub.pack()

    splash.after(1800, splash.destroy)  # slightly faster intro
    splash.mainloop()

# ============================================================
# Connection Dialog (reuse V3 get_db_connection implementation to keep behavior)
# NOTE: We keep this as a stand-alone window with its own mainloop to minimize change.
# ============================================================
def get_db_connection(parent=None):
    credential_manager = CredentialManager()
    
    def validate_port(port_str):
        try:
            port = int(port_str)
            return 1 <= port <= 65535
        except ValueError:
            return False

    def load_saved_credentials():
        saved_creds = credential_manager.load_credentials()
        if saved_creds:
            user_entry.insert(0, saved_creds["username"])
            pass_entry.insert(0, saved_creds["password"])
            host_entry.insert(0, saved_creds["host"])
            port_entry.insert(0, saved_creds["port"])
            db_entry.insert(0, saved_creds["database"])
            save_creds_var.set(True)
            return True
        return False

    def connect_db():
        nonlocal engine
        
        progress_bar.set(0.1)
        progress_label.configure(text="Validating connection details...")
        root.update()

        user = user_entry.get().strip()
        password = pass_entry.get().strip()
        host = host_entry.get().strip() or "localhost"
        port = port_entry.get().strip() or "5432"
        db = db_entry.get().strip() or "canvasdata2"

        if not user or not password:
            messagebox.showerror("Missing Info", "Username and password are required.")
            connect_btn.configure(state="normal")
            progress_frame.pack_forget()
            return

        if not validate_port(port):
            messagebox.showerror("Invalid Port", "Port must be a number between 1 and 65535.")
            return

        port_num = int(port)

        try:
            progress_bar.set(0.3)
            progress_label.configure(text="Preparing connection string...")
            root.update()

            if re.search("redshift", host, re.IGNORECASE):
                conn_str = f"redshift+psycopg2://{user}:{password}@{host}:{port_num}/{db}"
            else:
                conn_str = f"postgresql+psycopg2://{user}:{password}@{host}:{port_num}/{db}?options=-c%20client_encoding=utf8"

            progress_bar.set(0.5)
            progress_label.configure(text="Creating database engine...")
            root.update()

            temp_engine = create_engine(conn_str)
            
            progress_bar.set(0.7)
            progress_label.configure(text="Testing connection...")
            root.update()
            
            conn = None
            try:
                conn = temp_engine.connect()
                conn.execute(text("SELECT 1"))
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

            progress_bar.set(1.0)
            progress_label.configure(text="Connection successful!")
            root.update()

            engine = temp_engine
            
            if save_creds_var.get():
                credential_manager.save_credentials(user, password, host, port, db)
            
            # Close dialog first, then show success message
            root.destroy()
            print(f"✅ Connected to {db} at {host}:{port}")
            
            # Show success message after dialog is closed (non-blocking for parent)
            if parent:
                parent.after(100, lambda: messagebox.showinfo("Connection Success", f"Connected to {db} at {host}:{port}"))
            else:
                messagebox.showinfo("Connection Success", f"Connected to {db} at {host}:{port}")
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Could not connect:\n{e}")

    engine = None
    if parent:
        root = ctk.CTkToplevel(parent)
        root.transient(parent)
        root.grab_set()  # Make it modal
    else:
        root = ctk.CTk()
    root.title("Add Database Connection")
    root.geometry("520x420")

    frame = ctk.CTkFrame(root, corner_radius=20)
    frame.pack(padx=40, pady=40, fill="both", expand=True)

    title = ctk.CTkLabel(frame, text="New Connection", font=("Segoe UI", 20, "bold"))
    title.pack(pady=(20, 10))

    entries = {}
    for label in ["Username", "Password", "Host", "Port", "Database"]:
        ctk.CTkLabel(frame, text=label + ":").pack(anchor="w", padx=40, pady=(5, 0))
        entry = ctk.CTkEntry(
            frame, 
            show="*" if label == "Password" else "", 
            width=320
        )
        entry.pack(padx=40, pady=(0, 10))
        entries[label] = entry

    user_entry = entries["Username"]
    pass_entry = entries["Password"]
    host_entry = entries["Host"]
    port_entry = entries["Port"]
    db_entry = entries["Database"]

    creds_frame = ctk.CTkFrame(frame, fg_color="transparent")
    creds_frame.pack(pady=10, padx=20, fill="x")

    save_creds_var = ctk.BooleanVar()
    save_creds_checkbox = ctk.CTkCheckBox(
        creds_frame, 
        text="Save credentials securely", 
        variable=save_creds_var,
        font=("Segoe UI", 11)
    )
    save_creds_checkbox.pack(side="left", padx=10)

    def clear_saved_credentials():
        if CredentialManager().clear_credentials():
            messagebox.showinfo("Success", "Saved credentials cleared")
            for entry in entries.values():
                entry.delete(0, 'end')
            save_creds_var.set(False)
        else:
            messagebox.showerror("Error", "Failed to clear credentials")

    clear_creds_btn = ctk.CTkButton(
        creds_frame,
        text="Clear Saved",
        command=clear_saved_credentials,
        width=110,
        height=28,
        font=("Segoe UI", 10)
    )
    clear_creds_btn.pack(side="right", padx=10)

    # Progress (hidden initially)
    progress_frame = ctk.CTkFrame(frame, fg_color="transparent")
    progress_frame.pack(pady=10, padx=20, fill="x", expand=True)
    progress_frame.pack_forget()
    
    progress_label = ctk.CTkLabel(progress_frame, text="Connecting...", font=("Segoe UI", 11))
    progress_label.pack(pady=(0, 5))
    
    progress_bar = ctk.CTkProgressBar(progress_frame)
    progress_bar.pack(fill="x", padx=40)
    progress_bar.set(0)
    
    def start_connection():
        connect_btn.configure(state="disabled")
        progress_frame.pack(pady=10, padx=20, fill="x", expand=True)
        progress_bar.set(0.1)
        progress_label.configure(text="Initializing connection...")
        root.update()
        connect_db()
    
    load_saved_credentials()
    connect_btn = ctk.CTkButton(
        frame,
        text="Connect",
        fg_color="#0078d7",
        hover_color="#005a9e",
        font=("Segoe UI", 13, "bold"),
        corner_radius=12,
        command=start_connection
    )
    connect_btn.pack(pady=20)

    # Don't use mainloop - let the parent window handle events
    # Instead, wait for the window to be destroyed
    root.wait_window()  # This waits for the window to be destroyed without starting a new event loop
    
    # Return engine for the new connection (None if cancelled/failed)
    if engine is not None:
        # return metadata with connection for sidebar label
        try:
            creds = CredentialManager().load_credentials()
            meta = {
                "username": creds["username"] if creds else "",
                "host": creds["host"] if creds else "",
                "port": creds["port"] if creds else "",
                "database": creds["database"] if creds else ""
            }
        except Exception:
            meta = {"username": "", "host": "", "port": "", "database": ""}
        return engine, meta
    return None, None

# ============================================================
# Queries (same as V3)
# ============================================================
queries = {
    "activity": """
SELECT DISTINCT 
    r.timestamp AS timestamp_UTC,
    convert_timezone('EST','PST',r.timestamp::timestamp) AS timestamp_EST,
    p.unique_id AS username,
    r.remote_ip as ip,
    r.user_agent,
    r.http_method,
    r.http_status,
    r.session_id,
    r.URL,
    r.web_application_controller AS controller,
    r.web_application_action AS action,
    r.web_application_context_type AS context_type,
    r.web_application_context_id AS context_id,
    d.title AS discussion_topic,
    c.subject AS conversation_subject,
    a.title AS assignment,
    q.title AS quiz,
    co.sis_source_id AS course_sis_id,
    co.name AS course_name
FROM web_logs r
LEFT JOIN pseudonyms p ON r.user_id = p.user_id
LEFT JOIN assignments a ON r.assignment_id = a.id
LEFT JOIN quizzes q ON r.quiz_id = q.id
LEFT JOIN conversations c ON r.conversation_id = c.id
LEFT JOIN discussion_topics d ON r.discussion_id = d.id
LEFT JOIN courses co ON r.course_id = co.id
WHERE p.unique_id = %(username)s
  AND r.timestamp >= to_timestamp(%(from_date)s, 'YYYY-MM-DD HH24:MI:SS')
  AND r.timestamp < to_timestamp(%(to_date)s, 'YYYY-MM-DD HH24:MI:SS')
ORDER BY r.timestamp""",

    "submissions": """
WITH fs AS (
  SELECT
      s.user_id,
      s.assignment_id,
      s.attempt,
      s.submitted_at,
      s.workflow_state,
      s.submission_type,
      s.score,
      s.graded_at
  FROM submissions s
  JOIN pseudonyms p ON p.user_id = s.user_id
  WHERE p.unique_id = %(username)s
    AND s.submitted_at BETWEEN CAST(%(from_date)s AS TIMESTAMP)
                           AND CAST(%(to_date)s AS TIMESTAMP)
    AND s.workflow_state IN ('submitted','graded')
    AND s.submission_type IS NOT NULL
),
matched AS (
  SELECT
      fs.user_id,
      fs.assignment_id,
      fs.submitted_at,
      fs.attempt,
      fs.workflow_state,
      fs.submission_type,
      fs.score,
      fs.graded_at,
      r.remote_ip,
      r.url,
      r.session_id,
      r.http_method,
      r.http_status,
      r.user_agent,
      r.web_application_controller AS controller,
      r.web_application_action     AS action,
      r.timestamp                  AS log_time,
      CASE
        WHEN r.web_application_controller IN ('submissions','assignment_submissions','quiz_submissions')
         AND r.web_application_action     IN ('create','update','submit','finish','complete')
         AND r.http_method                IN ('POST','PUT')
        THEN 1
        ELSE 3
      END AS source_rank,
      ROW_NUMBER() OVER (
        PARTITION BY fs.user_id, fs.assignment_id, fs.submitted_at
        ORDER BY r.timestamp - fs.submitted_at
      ) AS rn
  FROM fs
  LEFT JOIN web_logs r
    ON r.user_id = fs.user_id
   AND r.timestamp BETWEEN fs.submitted_at - INTERVAL '20 minutes'
                       AND fs.submitted_at + INTERVAL '20 minutes'
)
SELECT
    fs.submitted_at AS timestamp_est,
    p.unique_id AS username,
    co.sis_source_id AS course_sis_id,
    co.name AS course_name,
    a.title AS assignment,
    fs.attempt,
    fs.workflow_state,
    fs.submission_type,
    fs.score,
    fs.graded_at,
    m.remote_ip AS ip_at_submit,
    m.url AS url_at_submit,
    m.http_method,
    m.http_status,
    m.controller,
    m.action,
    m.user_agent,
    m.log_time,
    m.source_rank AS match_tier
FROM fs
JOIN assignments a ON a.id = fs.assignment_id
JOIN courses co ON a.context_type = 'Course' AND a.context_id = co.id
JOIN enrollments e ON e.user_id = fs.user_id AND e.course_id = co.id
JOIN pseudonyms p ON p.user_id = fs.user_id
LEFT JOIN matched m
  ON m.user_id = fs.user_id
 AND m.assignment_id = fs.assignment_id
 And m.submitted_at = fs.submitted_at
 AND m.rn = 1
ORDER BY fs.submitted_at"""
}

# ============================================================
# Query Runner - REMOVED (replaced with optimized run_query_with_panel_updates)
# ============================================================
# The old run_query function has been removed to avoid conflicts.
# All query execution now uses the optimized run_query_with_panel_updates method.

# ============================================================
# Parameter Dialog (unchanged behavior)
# ============================================================
def get_query_parameters():
    params = {}
    MAX_DATE_RANGE_DAYS = 90

    def validate_date(date_str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

    def on_closing():
        params.clear()
        root.destroy()  # Use destroy() instead of quit() for CTkToplevel

    def submit():
        username = username_entry.get().strip()
        from_date = from_entry.get().strip()
        to_date = to_entry.get().strip()

        if not all([username, from_date, to_date]):
            messagebox.showerror("Missing Info", "All fields are required.")
            return

        from_dt = validate_date(from_date)
        to_dt = validate_date(to_date)

        if not from_dt or not to_dt:
            messagebox.showerror("Invalid Date", "Dates must be in YYYY-MM-DD format.")
            return

        if to_dt < from_dt:
            messagebox.showerror("Invalid Dates", "'To Date' must be after 'From Date'.")
            return

        date_range = (to_dt - from_dt).days
        if date_range > MAX_DATE_RANGE_DAYS:
            messagebox.showerror("Invalid Date Range", 
                               f"Date range cannot exceed {MAX_DATE_RANGE_DAYS} days.")
            return

        params["username"] = username
        params["from_date"] = from_date
        params["to_date"] = to_date
        params["include_geolocation"] = include_geo_var.get()
        params["export_excel"] = export_excel_var.get()
        
        # DEBUG: Show parameter values
        print(f"DEBUG: Query parameters - Geolocation: {params['include_geolocation']}, Excel: {params['export_excel']}")
        
        root.destroy()  # Use destroy() instead of quit() for CTkToplevel

    # Create as a modal dialog window (Toplevel, not new CTk instance)
    root = ctk.CTkToplevel()
    root.title("Query Parameters")
    root.geometry("480x400")
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Make it modal and bring to front
    root.transient()  # Make it a transient window
    root.grab_set()   # Make it modal
    root.lift()       # Bring to front
    root.focus_force() # Force focus

    ctk.CTkLabel(root, text="Enter Query Parameters", font=("Segoe UI", 13, "bold")).pack(pady=10)

    ctk.CTkLabel(root, text="Username:").pack(anchor="w", padx=30, pady=(10, 0))
    username_entry = ctk.CTkEntry(root, width=300)
    username_entry.pack(padx=30)

    ctk.CTkLabel(root, text="From Date (YYYY-MM-DD):").pack(anchor="w", padx=30, pady=(10, 0))
    from_entry = ctk.CTkEntry(root, width=300)
    from_entry.pack(padx=30)

    ctk.CTkLabel(root, text="To Date (YYYY-MM-DD):").pack(anchor="w", padx=30, pady=(10, 0))
    to_entry = ctk.CTkEntry(root, width=300)
    to_entry.pack(padx=30)

    # Options frame
    options_frame = ctk.CTkFrame(root, fg_color="transparent")
    options_frame.pack(pady=(15, 0))
    
    # Geolocation checkbox
    include_geo_var = ctk.BooleanVar(value=True)  # Default enabled
    geo_checkbox = ctk.CTkCheckBox(
        options_frame,
        text="Include IP Geolocation",
        variable=include_geo_var,
        font=("Segoe UI", 11)
    )
    geo_checkbox.pack(anchor="w", padx=30, pady=2)
    
    # Excel export checkbox  
    export_excel_var = ctk.BooleanVar(value=True)  # Default enabled
    excel_checkbox = ctk.CTkCheckBox(
        options_frame,
        text="Export to Excel file",
        variable=export_excel_var,
        font=("Segoe UI", 11)
    )
    excel_checkbox.pack(anchor="w", padx=30, pady=2)

    ctk.CTkButton(root, text="Run Query", command=submit, fg_color="#2b5797",
           font=("Segoe UI", 11, "bold"), corner_radius=10).pack(pady=20)
    

    # Wait for the modal dialog to close
    root.wait_window(root)  # Wait for this specific window to be destroyed
    return params

# ============================================================
# Main Application (V4: SQL Developer-style layout, V3 theme)
# ============================================================
class CanvasDataApp:
    def __init__(self):
        self.active_engine = None
        self.active_meta = None  # dict with username, host, port, database
        self.connections = []    # list of dicts: {"engine":..., "meta":..., "label":..., "button":...}
        self.credential_manager = CredentialManager()
        self.root = None

        # UI references
        self.sidebar_frame = None
        self.workspace_frame = None
        self.status_label = None

    # --------- UI Shell ---------
    def build_shell(self):
        self.root = ctk.CTk()
        self.root.title("Canvas Data Automator")
        self.root.geometry("1100x720")

        # Top bar
        top_bar = ctk.CTkFrame(self.root, height=40, fg_color="#2a2a2a", corner_radius=0)
        top_bar.pack(fill="x", side="top")

        add_btn = ctk.CTkButton(
            top_bar, text="+", width=34, height=28,
            fg_color="#28a745", hover_color="#218838",
            font=("Segoe UI", 18, "bold"),
            corner_radius=6,
            command=self.add_connection
        )
        add_btn.pack(side="left", padx=(10, 6), pady=6)

        ctk.CTkLabel(top_bar, text="Add Connection", font=("Segoe UI", 11)).pack(side="left", padx=(2, 10))

        # Body split
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar_frame = ctk.CTkFrame(body, width=260, fg_color="#1f1f1f", corner_radius=0)
        self.sidebar_frame.pack(fill="y", side="left")
        ctk.CTkLabel(self.sidebar_frame, text="Connections", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 6))

        # Workspace
        self.workspace_frame = ctk.CTkFrame(body, fg_color="#111111")
        self.workspace_frame.pack(fill="both", expand=True, side="left", padx=8, pady=8)

        # Status bar
        status_bar = ctk.CTkFrame(self.root, height=26, fg_color="#2a2a2a", corner_radius=0)
        status_bar.pack(fill="x", side="bottom")
        self.status_label = ctk.CTkLabel(status_bar, text="No connections", font=("Segoe UI", 10))
        self.status_label.pack(anchor="w", padx=10)

        # Initial workspace content
        self.render_welcome()

        self.root.protocol("WM_DELETE_WINDOW", self.root.quit)

    def render_welcome(self):
        for w in self.workspace_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.workspace_frame, text="Canvas Data Automator", font=("Segoe UI", 24, "bold")).pack(pady=(30, 8))
        ctk.CTkLabel(self.workspace_frame, text="Click + Add Connection to begin.", font=("Segoe UI", 13)).pack()

    def render_connected(self):
        for w in self.workspace_frame.winfo_children():
            w.destroy()

        # Header with connection status
        header_frame = ctk.CTkFrame(self.workspace_frame, height=60, fg_color="#2a2a2a")
        header_frame.pack(fill="x", padx=8, pady=(8, 0))
        header_frame.pack_propagate(False)

        conn_text = f"🟢 Connected to {self.active_meta.get('database','')} as {self.active_meta.get('username','')}"
        ctk.CTkLabel(header_frame, text=conn_text, font=("Segoe UI", 12)).pack(side="left", padx=15, pady=15)

        # Query buttons in header
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right", padx=15, pady=10)

        def debug_activity_click():
            print("DEBUG: Activity Logs button clicked!")
            self.run_query_workflow("activity")
            
        def debug_submissions_click():
            print("DEBUG: Submissions button clicked!")
            self.run_query_workflow("submissions")

        ctk.CTkButton(
            btn_frame,
            text="📊 Activity Logs",
            command=debug_activity_click,
            width=140,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color="#2b5797"
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="📝 Submissions",
            command=debug_submissions_click,
            width=140,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color="#2b5797"
        ).pack(side="left", padx=5)

        # Main query workspace - split between SQL and Results
        workspace_splitter = ctk.CTkFrame(self.workspace_frame, fg_color="transparent")
        workspace_splitter.pack(fill="both", expand=True, padx=8, pady=8)

        # SQL Worksheet Panel (Top half)
        self.sql_panel = ctk.CTkFrame(workspace_splitter, fg_color="#1a1a1a")
        self.sql_panel.pack(fill="both", expand=True, pady=(0, 4))

        # SQL Panel Header
        sql_header = ctk.CTkFrame(self.sql_panel, height=35, fg_color="#2a2a2a")
        sql_header.pack(fill="x")
        sql_header.pack_propagate(False)
        
        ctk.CTkLabel(sql_header, text="📄 Query Worksheet", font=("Segoe UI", 11, "bold")).pack(side="left", padx=12, pady=8)
        
        # SQL Text Area
        self.sql_text = ctk.CTkTextbox(
            self.sql_panel, 
            font=("Consolas", 11),
            fg_color="#0f0f0f",
            text_color="#ffffff",
            wrap="none"
        )
        self.sql_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        
        # Results Panel (Bottom half)
        self.results_panel = ctk.CTkFrame(workspace_splitter, fg_color="#1a1a1a")
        self.results_panel.pack(fill="both", expand=True, pady=(4, 0))

        # Results Panel Header
        results_header = ctk.CTkFrame(self.results_panel, height=35, fg_color="#2a2a2a")
        results_header.pack(fill="x")
        results_header.pack_propagate(False)
        
        self.results_label = ctk.CTkLabel(results_header, text="� Query Results", font=("Segoe UI", 11, "bold"))
        self.results_label.pack(side="left", padx=12, pady=8)
        
        # Results status (right side of header)
        self.results_status = ctk.CTkLabel(results_header, text="Ready", font=("Segoe UI", 10))
        self.results_status.pack(side="right", padx=12, pady=8)
        
        # Progress Bar Frame (Matrix-themed, hidden by default) - COMPACT SIZE
        self.progress_frame = ctk.CTkFrame(
            self.results_panel, 
            fg_color="#2a2a2a",  # Lighter background for visibility
            border_width=1,
            border_color="#00ff00",  # Matrix green border
            height=60  # Fixed compact height
        )
        self.progress_frame.pack(fill="x", padx=8, pady=(2, 0))
        self.progress_frame.pack_propagate(False)  # Don't expand
        self.progress_frame.pack_forget()  # Hide initially
        
        # Progress bar with Matrix green theme - SMALLER
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, 
            width=300,  # Fixed width instead of fill
            height=15,  # Much smaller height
            progress_color="#00ff00",  # Matrix green
            fg_color="#000000",       # Pure black background for contrast
        )
        self.progress_bar.pack(pady=(5, 2), padx=20)  # Smaller padding
        self.progress_bar.set(0)
        
        # Progress label with Matrix styling - SMALLER
        self.progress_label = ctk.CTkLabel(
            self.progress_frame, 
            text="Initializing...", 
            font=("Consolas", 9),  # Much smaller font
            text_color="#00ff00"
        )
        self.progress_label.pack(pady=(0, 5))

        # Results Text Area (with proper scrolling)
        self.results_text = ctk.CTkTextbox(
            self.results_panel,
            font=("Consolas", 10),
            fg_color="#0f0f0f", 
            text_color="#00ff00",
            wrap="word",  # Enable word wrapping for better readability
            scrollbar_button_color="#00ff00",  # Matrix green scrollbar
            scrollbar_button_hover_color="#00aa00"  # Darker green on hover
        )
        self.results_text.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # Management buttons at bottom
        mgmt = ctk.CTkFrame(self.workspace_frame, height=50, fg_color="#2a2a2a")
        mgmt.pack(fill="x", padx=8, pady=(0, 8))
        mgmt.pack_propagate(False)

        ctk.CTkButton(
            mgmt,
            text="🔄 New Connection",
            command=self.add_connection,
            width=150,
            height=30,
            font=("Segoe UI", 10)
        ).pack(side="left", padx=12, pady=10)

        ctk.CTkButton(
            mgmt,
            text="🗑️ Clear Credentials",
            command=self.clear_saved_credentials,
            width=150,
            height=30,
            font=("Segoe UI", 10)
        ).pack(side="left", padx=5, pady=10)

        # Initialize with welcome message
        self.show_ready_state()

    def show_ready_state(self):
        """Display ready state in SQL panels"""
        if hasattr(self, 'sql_text'):
            self.sql_text.delete("1.0", "end")
            self.sql_text.insert("1.0", "-- Canvas Data Automator Query Workspace\n-- Select a query type above to begin\n\n-- Available Queries:\n--   📊 Activity Logs: User activity tracking\n--   📝 Submissions: Assignment submission analysis")
            
        if hasattr(self, 'results_text'):
            self.results_text.delete("1.0", "end")
            self.results_text.insert("1.0", "Ready to execute queries...\n\nConnection Status: ✅ Connected\nDatabase: " + str(self.active_meta.get('database', 'Unknown')) + "\nUser: " + str(self.active_meta.get('username', 'Unknown')))
            
        if hasattr(self, 'results_status'):
            self.results_status.configure(text="Ready")
        
        # Hide progress bar when in ready state
        self.hide_progress_bar()

    def show_progress_bar(self):
        """Show the Matrix-themed progress bar"""
        print("DEBUG: show_progress_bar called")
        if hasattr(self, 'progress_frame') and hasattr(self, 'progress_bar') and hasattr(self, 'progress_label'):
            print("DEBUG: All progress components exist, showing progress bar")
            try:
                # Show the frame
                self.progress_frame.pack(fill="x", padx=8, pady=(4, 0))
                
                # Initialize with visible progress to test
                self.progress_bar.set(0.1)  # Set to 10% to make it visible immediately
                self.progress_label.configure(text="[MATRIX] Initializing query execution...")
                
                # Force a brief visual update to ensure it appears
                if hasattr(self, 'root') and self.root:
                    try:
                        self.root.update_idletasks()
                    except:
                        pass  # Ignore update errors
                
                print("DEBUG: Progress bar shown successfully with initial 10% progress")
            except Exception as e:
                print(f"DEBUG: Error showing progress bar: {e}")
        else:
            print("DEBUG: Progress components not found! Make sure you're connected to a database first.")
            print(f"DEBUG: Has progress_frame: {hasattr(self, 'progress_frame')}")
            print(f"DEBUG: Has progress_bar: {hasattr(self, 'progress_bar')}")
            print(f"DEBUG: Has progress_label: {hasattr(self, 'progress_label')}")

    def hide_progress_bar(self):
        """Hide the progress bar"""
        print("DEBUG: hide_progress_bar called")
        if hasattr(self, 'progress_frame'):
            try:
                self.progress_frame.pack_forget()
                print("DEBUG: Progress bar hidden successfully")
            except Exception as e:
                print(f"DEBUG: Error hiding progress bar: {e}")
        else:
            print("DEBUG: Progress frame not found for hiding!")

    def update_progress(self, value, message):
        """Thread-safe progress bar update"""
        def _update_ui():
            """Internal UI update function"""
            print(f"DEBUG: Progress update - {value*100:.0f}% - {message}")
            if hasattr(self, 'progress_bar') and hasattr(self, 'progress_label'):
                try:
                    self.progress_bar.set(value)
                    self.progress_label.configure(text=f"[{value*100:.0f}%] {message}")
                    print(f"DEBUG: Progress updated to {value*100:.0f}%")
                except Exception as e:
                    print(f"DEBUG: Progress update error: {e}")
            else:
                print("DEBUG: Progress bar components not available")

        # Schedule UI update on main thread if called from background thread
        if hasattr(self, 'root') and self.root:
            try:
                self.root.after(0, _update_ui)
            except:
                # Fallback to direct update if scheduling fails
                _update_ui()
        else:
            _update_ui()

    def show_query_executing(self, query_type, sql, params):
        """Display query execution state with Matrix-themed progress bar"""
        # Show progress bar first
        self.show_progress_bar()
        # Add initial progress update to show it's working
        self.update_progress(0.05, "Starting query execution...")
        
        if hasattr(self, 'sql_text'):
            self.sql_text.delete("1.0", "end")
            
            # Format the SQL for display
            formatted_sql = f"-- Canvas Data Query: {query_type.upper()}\n"
            formatted_sql += f"-- Parameters: username={params.get('username')}, "
            formatted_sql += f"from_date={params.get('from_date')}, to_date={params.get('to_date')}\n"
            formatted_sql += f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            formatted_sql += sql
            
            self.sql_text.insert("1.0", formatted_sql)
            
        if hasattr(self, 'results_text'):
            self.results_text.delete("1.0", "end")
            results_text = f"🔄 EXECUTING {query_type.upper()} QUERY...\n"
            results_text += f"{'='*50}\n\n"
            results_text += f"Status: RUNNING\n"
            results_text += f"Started: {datetime.now().strftime('%H:%M:%S')}\n"
            results_text += f"Parameters:\n"
            results_text += f"  • Username: {params.get('username')}\n"
            results_text += f"  • Date Range: {params.get('from_date')} to {params.get('to_date')}\n"
            results_text += f"  • Geolocation: {'ENABLED' if params.get('include_geolocation') else 'DISABLED'}\n"
            results_text += f"  • Excel Export: {'ENABLED' if params.get('export_excel') else 'DISABLED'}\n\n"
            results_text += f"Progress tracking active...\n"
            results_text += f"{'='*50}"
            self.results_text.insert("1.0", results_text)
            
        if hasattr(self, 'results_status'):
            self.results_status.configure(text="🔄 Executing...")

    def show_query_results(self, query_type, row_count, filename, execution_time, success=True, exported_to_excel=True, included_geolocation=True):
        """Display query results and hide progress bar"""
        # Hide progress bar now that query is complete
        self.hide_progress_bar()
        
        if hasattr(self, 'results_text'):
            self.results_text.delete("1.0", "end")
            
            if success:
                results_text = f"{query_type.upper()} Query Completed Successfully!\n\n"
                results_text += f"Results Summary:\n"
                results_text += f"Rows Retrieved: {row_count:,}\n"
                results_text += f"Execution Time: {execution_time}\n"
                results_text += f"Completed: {datetime.now().strftime('%H:%M:%S')}\n\n"
                
                # Show export status
                if exported_to_excel and filename and filename != "No file exported":
                    results_text += f"Excel Export: {filename}\n"
                    try:
                        results_text += f"File Location: {os.path.abspath(filename)}\n\n"
                    except:
                        results_text += f"File Location: {filename}\n\n"
                else:
                    results_text += f"Excel Export: Skipped (user disabled)\n\n"
                
                # Show geolocation status
                if included_geolocation and row_count > 0:
                    geo_status = "Included"
                elif not included_geolocation:
                    geo_status = "Skipped (user disabled)"
                else:
                    geo_status = "No data"
                
                results_text += f"Geographic Data: {geo_status}\n"
                results_text += f"Caching: Active (speeds up future queries)\n\n"
                results_text += f"Ready for next query..."
                
                self.results_text.configure(text_color="#00ff00")
                self.results_status.configure(text=f"Complete ({row_count:,} rows)")
            else:
                results_text = f"{query_type.upper()} Query Failed\n\n"
                results_text += f"An error occurred during query execution.\n"
                results_text += f"Check the error message above and try again.\n\n"
                results_text += f"Failed: {datetime.now().strftime('%H:%M:%S')}"
                
                self.results_text.configure(text_color="#ff4444")
                self.results_status.configure(text="Error")
                
            self.results_text.insert("1.0", results_text)

    def update_query_progress(self, message):
        """Update query progress in results panel"""
        if hasattr(self, 'results_text'):
            current_text = self.results_text.get("1.0", "end")
            # Append progress message
            self.results_text.insert("end", f"\n{datetime.now().strftime('%H:%M:%S')} - {message}")
            # Auto-scroll to bottom
            self.results_text.see("end")

    # --------- Sidebar mgmt ---------
    def refresh_sidebar(self):
        # Clear all but header
        for w in self.sidebar_frame.winfo_children()[1:]:
            w.destroy()
        if not self.connections:
            ctk.CTkLabel(self.sidebar_frame, text="No connections yet.", font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(4, 8))
            return

        for idx, c in enumerate(self.connections):
            is_active = (c is self.get_active_connection())
            
            # Create a frame for each connection row
            conn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
            conn_frame.pack(fill="x", padx=12, pady=3)
            
            # Connection button (takes most of the space)
            conn_btn = ctk.CTkButton(
                conn_frame,
                text=c["label"],
                command=lambda i=idx: self.select_connection(i),
                width=180,
                height=32,
                fg_color=("#2b5797" if is_active else "#3a3a3a"),
                hover_color="#2b5797",
                corner_radius=8,
                font=("Segoe UI", 10)
            )
            conn_btn.pack(side="left", fill="x", expand=True)
            
            # Remove button (small, on the right)
            remove_btn = ctk.CTkButton(
                conn_frame,
                text="✕",
                command=lambda i=idx: self.remove_connection(i),
                width=28,
                height=32,
                fg_color="#dc3545",
                hover_color="#c82333",
                corner_radius=6,
                font=("Segoe UI", 12, "bold")
            )
            remove_btn.pack(side="right", padx=(4, 0))
            
            c["button"] = conn_btn
            c["remove_button"] = remove_btn

    def get_active_connection(self):
        for c in self.connections:
            if c["engine"] is self.active_engine:
                return c
        return None

    def select_connection(self, idx: int):
        chosen = self.connections[idx]
        self.active_engine = chosen["engine"]
        self.active_meta = chosen["meta"]
        # Update buttons to reflect active state
        self.refresh_sidebar()
        # Update status bar and workspace
        self.status_label.configure(
            text=f"Connected to {self.active_meta.get('database','')} as {self.active_meta.get('username','')}"
        )
        self.render_connected()

    def remove_connection(self, idx: int):
        """Remove a connection from the list and clean up resources"""
        if idx < 0 or idx >= len(self.connections):
            return
        
        connection_to_remove = self.connections[idx]
        connection_label = connection_to_remove["label"]
        
        # Confirm removal
        if not messagebox.askyesno("Remove Connection", 
                                  f"Remove connection '{connection_label}'?\n\nThis will close the database connection."):
            return
        
        # Close the database engine if it exists
        try:
            if connection_to_remove["engine"]:
                connection_to_remove["engine"].dispose()
                print(f"Closed database connection for {connection_label}")
        except Exception as e:
            print(f"Error closing connection {connection_label}: {e}")
        
        # Remove from connections list
        self.connections.pop(idx)
        
        # Handle active connection cleanup
        was_active = (connection_to_remove["engine"] is self.active_engine)
        if was_active:
            # Set new active connection or clear if no connections left
            if self.connections:
                # Set the first remaining connection as active
                self.select_connection(0)
            else:
                # No connections left
                self.active_engine = None
                self.active_meta = None
                self.status_label.configure(text="No connections")
                self.render_welcome()
        
        # Refresh sidebar to reflect changes
        self.refresh_sidebar()
        
        print(f"Removed connection: {connection_label}")

    # --------- Connection management ---------
    def add_connection(self):
        print("Starting connection process...")
        
        # Call connection dialog
        engine, meta = get_db_connection(parent=self.root)
        
        print(f"Connection dialog returned: engine={engine is not None}, meta={meta is not None}")
        
        if engine and meta:
            print(f"Creating connection entry for {meta.get('database','Unknown')}@{meta.get('host','Unknown')}")
            
            label = f"{meta.get('database','')}"
            entry = {"engine": engine, "meta": meta, "label": label, "button": None}
            self.connections.append(entry)
            
            # Set newly added as active
            self.active_engine = engine
            self.active_meta = meta
            
            print("Refreshing UI components...")
            
            # Refresh each component explicitly
            try:
                print("  - Refreshing sidebar...")
                self.refresh_sidebar()
                
                print("  - Updating status label...")
                status_text = f"Connected to {meta.get('database','')} as {meta.get('username','')}"
                self.status_label.configure(text=status_text)
                
                print("  - Rendering connected workspace...")
                self.render_connected()
                
                print("All UI components updated successfully!")
                
            except Exception as e:
                print(f"Error updating UI: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("No connection established (user cancelled or error occurred)")

    def clear_saved_credentials(self):
        if messagebox.askyesno("Confirm", "Clear saved credentials? (This doesn't remove active connections.)"):
            if self.credential_manager.clear_credentials():
                messagebox.showinfo("Success", "Credentials cleared successfully")
            else:
                messagebox.showerror("Error", "Failed to clear credentials")

    # --------- Query workflow (unchanged behaviors) ---------
    def run_query_workflow(self, query_type):
        print(f"DEBUG: run_query_workflow called with query_type='{query_type}'")
        
        try:
            if self.active_engine:
                print("DEBUG: Testing database connection...")
                self.active_engine.connect().close()
                print("DEBUG: Database connection OK")
            else:
                print("DEBUG: No active engine found")
                raise Exception("No database connection")
        except Exception as e:
            print(f"DEBUG: Connection error: {e}")
            messagebox.showerror("Connection Lost", "Database connection was lost. Please add/reconnect.")
            if hasattr(self, 'show_query_results'):
                self.show_query_results(query_type, 0, "", "0s", success=False)
            return
        
        print("DEBUG: Opening parameter dialog...")
        params = get_query_parameters()
        print(f"DEBUG: Parameter dialog returned: {params}")
        if not params:
            print("DEBUG: No parameters provided, returning to ready state")
            self.show_ready_state()
            return
        
        print("DEBUG: Processing parameters and starting query...")
        params["from_date"] += " 00:00:00"
        params["to_date"] += " 23:59:59"
        
        # Show query in SQL panel
        sql_query = queries[query_type]
        print("DEBUG: Calling show_query_executing...")
        self.show_query_executing(query_type, sql_query, params)
        
        # Execute query in background thread to prevent UI freezing
        start_time = datetime.now()
        
        def run_query_thread():
            """Run query in background thread"""
            try:
                print("DEBUG: Starting threaded query execution...")
                result = self.run_query_with_panel_updates(self.active_engine, sql_query, params, query_type)
                print(f"DEBUG: Threaded query execution completed. Result: {result is not None}")
                
                end_time = datetime.now()
                execution_time = str(end_time - start_time).split('.')[0]
                
                # Schedule UI update on main thread
                self.root.after(0, lambda: self.handle_query_completion(result, query_type, execution_time))
                
            except Exception as e:
                end_time = datetime.now()
                execution_time = str(end_time - start_time).split('.')[0]
                print(f"DEBUG: Threaded query error: {e}")
                # Schedule error handling on main thread
                self.root.after(0, lambda: self.handle_query_error(query_type, execution_time, str(e)))
        
        # Start query in background thread
        query_thread = threading.Thread(target=run_query_thread, daemon=True)
        query_thread.start()
        print("DEBUG: Query started in background thread - UI should remain responsive")

    def handle_query_completion(self, result, query_type, execution_time):
        """Handle successful query completion on main thread"""
        try:
            if result and isinstance(result, dict):
                self.show_query_results(
                    query_type, 
                    result.get('row_count', 0), 
                    result.get('filename', ''), 
                    execution_time, 
                    success=True,
                    exported_to_excel=result.get('exported_to_excel', True),
                    included_geolocation=result.get('included_geolocation', True)
                )
            else:
                self.show_query_results(query_type, 0, "", execution_time, success=False)
                if messagebox.askyesno("Error", "Query execution failed. Try again?"):
                    self.run_query_workflow(query_type)
        except Exception as e:
            print(f"DEBUG: Error in completion handler: {e}")

    def handle_query_error(self, query_type, execution_time, error_message):
        """Handle query error on main thread"""
        try:
            self.show_query_results(query_type, 0, "", execution_time, success=False)
            messagebox.showerror("Error", f"Query execution failed:\n{error_message}")
        except Exception as e:
            print(f"DEBUG: Error in error handler: {e}")

    def run_query_with_panel_updates(self, engine, sql, params, name):
        """Modified run_query that updates the results panel with progress - OPTIMIZED"""
        MAX_ROWS = 1000000
        CHUNK_SIZE = 100000
        SMALL_DATASET_THRESHOLD = 1000  # Skip optimizations for datasets under 1000 rows
        
        # Update panel with connection verification
        self.update_query_progress("Verifying database connection...")
        self.update_progress(0.15, "Verifying database connection")
        
        if engine is None:
            self.update_query_progress("Error: Database connection not initialized")
            return None
            
        try:
            conn = engine.connect()
            conn.close()
            self.update_query_progress("Database connection verified")
            self.update_progress(0.2, "Database connection verified")
            print("DEBUG: Database connection test passed")
        except Exception as e:
            self.update_query_progress(f"Connection test failed: {str(e)}")
            print(f"DEBUG: Database connection test failed: {e}")
            return None
        
        def is_valid_ip(ip):
            if not ip:
                return False
            try:
                import ipaddress
                ipaddress.ip_address(ip)
                return True
            except Exception:
                return False

        try:
            self.update_query_progress("Preparing query execution...")
            self.update_progress(0.25, "Preparing query execution")
            conn = engine.raw_connection()
            
            try:
                # OPTIMIZATION: Skip row counting for small expected datasets, execute directly
                self.update_query_progress("Executing query (optimized - no pre-counting)...")
                self.update_progress(0.3, "Executing SQL query")
                
                print(f"DEBUG: About to execute SQL query...")
                print(f"DEBUG: SQL preview: {sql[:100]}...")
                print(f"DEBUG: Parameters: {params}")
                
                start_query_time = time.time()
                df = pd.read_sql(sql, conn, params=params)
                query_time = time.time() - start_query_time
                
                total_rows = len(df)
                print(f"DEBUG: SQL execution completed - {total_rows} rows in {query_time:.2f}s")
                self.update_query_progress(f"Query completed in {query_time:.2f}s - Retrieved {total_rows:,} rows")
                self.update_progress(0.6, f"Retrieved {total_rows:,} rows")
                
                # If result set is unexpectedly large, warn user
                if total_rows > MAX_ROWS:
                    if not messagebox.askyesno(
                        "Large Dataset Warning",
                        f"Query returned {total_rows:,} rows. This may consume significant memory. Continue processing?"
                    ):
                        self.update_query_progress("Processing cancelled by user")
                        return None
                        
            finally:
                conn.close()

        except Exception as e:
            self.update_query_progress(f"Query execution failed: {str(e)}")
            print(f"DEBUG: Query execution error: {e}")
            print(f"DEBUG: Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            # Make sure to hide progress bar on error
            self.hide_progress_bar()
            return None

        # Process data - OPTIMIZED
        if len(df) > 0:
            # OPTIMIZATION: Only process datetime columns if they exist and contain timezone data
            datetime_cols = df.select_dtypes(include=["datetimetz"]).columns
            if len(datetime_cols) > 0:
                self.update_query_progress("Processing datetime columns...")
                self.update_progress(0.65, "Processing datetime columns")
                for col in datetime_cols:
                    df[col] = df[col].dt.tz_localize(None)
        
        # Geolocation processing - OPTIMIZED (OPTIONAL)
        # CRITICAL: Only process if explicitly enabled by user
        geolocation_enabled = params.get('include_geolocation', False)  # Changed default to False for safety
        print(f"DEBUG: Geolocation setting: {geolocation_enabled}")
        
        if geolocation_enabled is True:
            try:
                self.update_query_progress("Processing IP geolocation...")
                self.update_progress(0.7, "Processing IP geolocation")
                # Import only when needed to avoid any initialization delays
                from ip_geolocation import IPGeolocation
                geoip = IPGeolocation()
                ip_column = 'ip_at_submit' if name == 'submissions' else 'ip'
                
                if ip_column in df.columns and len(df) > 0:
                    # OPTIMIZATION: Use optimized geolocation processing
                    geo_start_time = time.time()
                    df = geoip.process_dataframe(df, ip_column)
                    geo_time = time.time() - geo_start_time
                    self.update_query_progress(f"Geolocation completed in {geo_time:.2f}s")
                    self.update_progress(0.8, f"Geolocation complete ({geo_time:.1f}s)")
                else:
                    self.update_query_progress("No IP column found or empty dataset")
                    self.update_progress(0.8, "No geolocation data to process")
            except Exception as e:
                self.update_query_progress(f"Geolocation processing failed: {str(e)}")
                self.update_progress(0.8, "Geolocation failed - continuing")
                print(f"DEBUG: Geolocation error: {e}")
        else:
            self.update_query_progress("Skipping IP geolocation (user disabled)")
            self.update_progress(0.8, "Geolocation skipped")
            print("DEBUG: Geolocation processing skipped")

        # Excel Export (OPTIONAL)
        filename = None
        estimated_size = 0
        
        # CRITICAL: Only export if explicitly enabled by user  
        excel_enabled = params.get('export_excel', False)  # Changed default to False for safety
        print(f"DEBUG: Excel export setting: {excel_enabled}")
        
        if excel_enabled is True:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name.capitalize()}Logs_{params['username']}_{timestamp}.xlsx"

            # OPTIMIZATION: Skip memory calculation for small datasets
            if len(df) > SMALL_DATASET_THRESHOLD:
                self.update_query_progress("Calculating file size...")
                self.update_progress(0.85, "Calculating Excel file size")
                estimated_size = df.memory_usage(deep=True).sum() / (1024 * 1024)
                
                if estimated_size > 50:
                    if not messagebox.askyesno("Large File Warning", 
                        f"The Excel file will be approximately {estimated_size:.1f}MB. Continue?"):
                        self.update_query_progress("Export cancelled by user")
                        return None
            else:
                # For small datasets, estimate a small file size
                estimated_size = len(df) * 0.001  # Rough estimate: ~1KB per row

            self.update_query_progress(f"Saving to Excel: {filename}")
            self.update_progress(0.9, f"Exporting {len(df):,} rows to Excel")
            
            max_retries = 3
            print(f"DEBUG: About to save {len(df)} rows to {filename}")
            for attempt in range(max_retries):
                try:
                    df.to_excel(filename, index=False)
                    self.update_query_progress("File saved successfully!")
                    self.update_progress(0.98, "Excel file saved successfully")
                    print(f"DEBUG: File saved successfully!")
                    break
                    
                except PermissionError:
                    if attempt < max_retries - 1:
                        retry = messagebox.askretrycancel("File in Use", 
                            f"Unable to save {filename}. The file may be open. Close it and retry?")
                        if retry:
                            continue
                    self.update_query_progress("Export failed: File in use")
                    return None
                except Exception as e:
                    self.update_query_progress(f"Export failed: {str(e)}")
                    return None
        else:
            self.update_query_progress("Skipping Excel export (user disabled)")
            self.update_progress(0.98, "Excel export skipped")
            
        # Final completion
        self.update_progress(1.0, "Query execution complete!")
        
        # Return success info for panel display
        print(f"DEBUG: Query completed successfully! Returning result.")
        print(f"DEBUG: Final status - Geolocation: {geolocation_enabled}, Excel: {excel_enabled}")
        return {
            'row_count': len(df),
            'filename': filename if filename else "No file exported",
            'file_size': estimated_size,
            'exported_to_excel': excel_enabled,  # Use actual processed value
            'included_geolocation': geolocation_enabled  # Use actual processed value
        }

    # --------- App entry ---------
    def run(self):
        splash_screen()
        self.build_shell()
        self.root.mainloop()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = CanvasDataApp()
    app.run()
