#!/usr/bin/env python3
"""
Canvas Data Automator - PyQt6 Version
Main Window Structure (Step 1 of Migration)
"""

import sys
import os
import re
from datetime import datetime
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QFrame, QLabel, QPushButton, QStatusBar, QToolBar,
    QStackedWidget, QScrollArea, QSizePolicy, QSpacerItem,
    QDialog, QLineEdit, QCheckBox, QProgressBar, QMessageBox,
    QComboBox, QTextEdit, QDateEdit, QFormLayout, QGridLayout
)
from PySide6.QtCore import Qt, QSize, Signal, QTimer, QThread, QObject, QDate
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QAction

# Qt Worker Class for Database Queries
class QueryWorker(QObject):
    """Worker class for executing database queries in a separate thread"""
    
    # Signals for communicating with main thread
    progress_updated = Signal(int, str)  # progress_value, progress_text
    query_completed = Signal(object, list, list, float, dict)  # query_config, rows, columns, query_time, params
    query_failed = Signal(str)  # error_message
    
    def __init__(self, engine, query_config, params):
        super().__init__()
        self.engine = engine
        self.query_config = query_config
        self.params = params
    
    def run_query(self):
        """Execute the database query"""
        try:
            # Add time suffixes to date parameters (copy params to avoid modifying original)
            query_params = self.params.copy()
            if "from_date" in query_params:
                query_params["from_date"] += " 00:00:00"
            if "to_date" in query_params:
                query_params["to_date"] += " 23:59:59"
            
            # Update progress
            self.progress_updated.emit(30, "[MATRIX] Executing SQL query...")
            
            # Execute SQL query using pandas (same as V4)
            import pandas as pd
            start_time = time.time()
            
            # Use raw connection like V4 does - this avoids SQLAlchemy transaction management
            conn = None
            
            try:
                conn = self.engine.raw_connection()
                
                df = pd.read_sql(self.query_config["sql"], conn, params=query_params)
                
                query_time = time.time() - start_time
                
                # Process geolocation if enabled (same as V4)
                geolocation_enabled = self.params.get('include_geolocation', False)
                print(f"DEBUG: Geolocation setting: {geolocation_enabled}")
                
                if geolocation_enabled:
                    try:
                        self.progress_updated.emit(60, "[MATRIX] Processing IP geolocation...")
                        
                        # Import geolocation module (same as V4)
                        from ip_geolocation import IPGeolocation
                        geoip = IPGeolocation()
                        
                        # Determine correct IP column based on query type (same as V4)
                        query_name = self.query_config.get('name', '')
                        ip_column = 'ip_at_submit' if ('submissions' in query_name.lower()) else 'ip'
                        print(f"DEBUG: Geolocation - Query name: '{query_name}', Using IP column: '{ip_column}'")
                        
                        if ip_column in df.columns and len(df) > 0:
                            # Use optimized geolocation processing (same as V4)
                            geo_start_time = time.time()
                            df = geoip.process_dataframe(df, ip_column)
                            geo_time = time.time() - geo_start_time
                            print(f"DEBUG: Geolocation completed in {geo_time:.2f}s")
                            self.progress_updated.emit(75, f"[MATRIX] Geolocation complete ({geo_time:.1f}s)")
                        else:
                            print("DEBUG: No IP column found or empty dataset")
                            self.progress_updated.emit(75, "[MATRIX] No geolocation data to process")
                            
                    except Exception as e:
                        print(f"DEBUG: Geolocation error: {e}")
                        self.progress_updated.emit(75, "[MATRIX] Geolocation failed - continuing")
                else:
                    print("DEBUG: Geolocation processing skipped")
                    self.progress_updated.emit(70, "[MATRIX] Geolocation skipped")
                
                # Convert DataFrame to rows/columns format for compatibility
                rows = [tuple(row) for row in df.values]
                columns = df.columns.tolist()
                
                # Update progress
                self.progress_updated.emit(80, f"[MATRIX] Query completed - {len(rows)} rows")
                
                # Emit results (keep original params for display)
                self.query_completed.emit(self.query_config, rows, columns, query_time, self.params)
                
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
            
        except Exception as e:
            # Print full error for debugging
            import traceback
            error_details = f"{str(e)}\n\nFull traceback:\n{traceback.format_exc()}"
            print(f"Query execution error: {error_details}")
            self.query_failed.emit(str(e))

# Query Library System - Enhanced and Expandable
queries = {
    "activity_logs": {
        "name": "Activity Logs",
        "description": "User activity tracking with IP geolocation and session details",
        "icon": "📊",
        "category": "User Activity",
        "sql": """
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
        "parameters": [
            {"name": "username", "type": "text", "label": "Username", "required": True, "placeholder": "Enter Canvas username"},
            {"name": "from_date", "type": "date", "label": "From Date", "required": True},
            {"name": "to_date", "type": "date", "label": "To Date", "required": True}
        ]
    },
    
    "submissions": {
        "name": "Submissions Analysis",
        "description": "Assignment submission tracking with activity correlation and timing analysis",
        "icon": "📝",
        "category": "Academic Activity",
        "sql": """
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
ORDER BY fs.submitted_at""",
        "parameters": [
            {"name": "username", "type": "text", "label": "Username", "required": True, "placeholder": "Enter Canvas username"},
            {"name": "from_date", "type": "date", "label": "From Date", "required": True},
            {"name": "to_date", "type": "date", "label": "To Date", "required": True}
        ]
    }
}

class CanvasDataApp(QMainWindow):
    """Main application window - PyQt6 version"""
    
    def __init__(self):
        super().__init__()
        
        # Data attributes (same as CustomTkinter version)
        self.active_engine = None
        self.active_meta = None
        self.connections = []
        
        # UI references
        self.sidebar_frame = None
        self.workspace_stack = None
        self.status_label = None
        self.sidebar_splitter = None
        
        # Initialize UI
        self.init_ui()
        self.apply_dark_theme()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Canvas Data Automator")
        self.resize(1100, 720)
        self.setMinimumSize(800, 600)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        main_layout.setSpacing(0)  # Remove spacing between toolbar and content
        
        # Create toolbar (replaces top bar)
        self.create_toolbar()
        
        # Create main content splitter (replaces body frame)
        self.create_main_content(main_layout)
        
        # Create status bar
        self.create_status_bar()
        
        # Show welcome screen initially
        self.show_welcome_screen()
        
    def create_toolbar(self):
        """Create top toolbar with add connection button"""
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)  # Prevent toolbar from being moved
        toolbar.setFloatable(False)  # Prevent toolbar from being floated
        toolbar.setObjectName("main_toolbar")
        
        # Add Connection Action
        add_action = QAction("＋", self)  # Using Unicode plus symbol
        add_action.setToolTip("Add Connection")
        add_action.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        add_action.triggered.connect(self.add_connection)
        toolbar.addAction(add_action)
        
        # Add label next to button
        label = QLabel("Add Connection")
        label.setFont(QFont("Segoe UI", 11))
        label.setStyleSheet("color: white; margin-left: 8px;")
        toolbar.addWidget(label)
        
        # Add spacer to push everything to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
    def create_main_content(self, main_layout):
        """Create the main content area with sidebar and workspace"""
        # Create horizontal splitter for sidebar + workspace
        self.sidebar_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.sidebar_splitter.setHandleWidth(1)  # Thin splitter handle
        main_layout.addWidget(self.sidebar_splitter)
        
        # Create sidebar
        self.create_sidebar()
        
        # Create workspace (stacked widget for different views)
        self.create_workspace()
        
        # Set splitter proportions (260px sidebar, rest for workspace)
        # Note: setSizes() uses proportional values, not pixels
        self.sidebar_splitter.setSizes([260, 840])
        self.sidebar_splitter.setCollapsible(0, False)  # Prevent sidebar from collapsing completely
        
    def create_sidebar(self):
        """Create the connections sidebar"""
        # Sidebar container
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebar")
        self.sidebar_frame.setMinimumWidth(200)  # Responsive minimum
        self.sidebar_frame.setMaximumWidth(400)  # Responsive maximum
        
        # Sidebar layout
        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(6)
        
        # Sidebar header
        header_label = QLabel("Connections")
        header_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header_label.setObjectName("sidebar_header")
        sidebar_layout.addWidget(header_label)
        
        # Connections scroll area (for when there are many connections)
        self.connections_scroll = QScrollArea()
        self.connections_scroll.setWidgetResizable(True)
        self.connections_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.connections_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.connections_scroll.setObjectName("connections_scroll")
        
        # Connections container widget
        self.connections_widget = QWidget()
        self.connections_layout = QVBoxLayout(self.connections_widget)
        self.connections_layout.setContentsMargins(0, 0, 0, 0)
        self.connections_layout.setSpacing(3)
        
        self.connections_scroll.setWidget(self.connections_widget)
        sidebar_layout.addWidget(self.connections_scroll)
        
        # Add sidebar to splitter
        self.sidebar_splitter.addWidget(self.sidebar_frame)
        
        # Initialize with no connections message
        self.refresh_sidebar()
        
    def create_workspace(self):
        """Create the main workspace area"""
        # Use QStackedWidget for different views (welcome, connected, etc.)
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setObjectName("workspace")
        
        # Create different workspace views
        self.welcome_view = self.create_welcome_view()
        self.connected_view = self.create_connected_view()
        
        # Add views to stack
        self.workspace_stack.addWidget(self.welcome_view)
        self.workspace_stack.addWidget(self.connected_view)
        
        # Add to splitter
        self.sidebar_splitter.addWidget(self.workspace_stack)
        
    def create_welcome_view(self):
        """Create the welcome screen view"""
        welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(welcome_widget)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Main title
        title_label = QLabel("Canvas Data Automator")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("welcome_title")
        welcome_layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel("Click + Add Connection to begin.")
        subtitle_label.setFont(QFont("Segoe UI", 13))
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setObjectName("welcome_subtitle")
        welcome_layout.addWidget(subtitle_label)
        
        return welcome_widget
        
    def create_connected_view(self):
        """Create the connected workspace view"""
        connected_widget = QWidget()
        connected_layout = QVBoxLayout(connected_widget)
        connected_layout.setContentsMargins(8, 8, 8, 8)
        connected_layout.setSpacing(8)
        
        # Header frame (connection status + query controls)
        header_frame = QFrame()
        header_frame.setObjectName("header_frame")
        header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)
        
        # Connection status label (left side)
        self.connection_status_label = QLabel("🟢 Connected to database")
        self.connection_status_label.setFont(QFont("Segoe UI", 12))
        header_layout.addWidget(self.connection_status_label)
        
        # Spacer to push query controls to the right
        header_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Query controls (right side)
        self.create_query_controls(header_layout)
        
        connected_layout.addWidget(header_frame)
        
        # Main workspace splitter (SQL panel + Results panel)
        workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        workspace_splitter.setHandleWidth(3)
        
        # SQL Panel (top)
        sql_panel = self.create_sql_panel()
        workspace_splitter.addWidget(sql_panel)
        
        # Results Panel (bottom)  
        results_panel = self.create_results_panel()
        workspace_splitter.addWidget(results_panel)
        
        # Set equal proportions for SQL and Results panels
        workspace_splitter.setSizes([350, 350])
        
        connected_layout.addWidget(workspace_splitter)
        
        # Trigger initial SQL display update now that all components exist
        QTimer.singleShot(100, self.update_initial_sql_display)
        
        return connected_widget
        
    def create_sql_panel(self):
        """Create the SQL worksheet panel"""
        sql_frame = QFrame()
        sql_frame.setObjectName("sql_panel")
        sql_layout = QVBoxLayout(sql_frame)
        sql_layout.setContentsMargins(0, 0, 0, 0)
        sql_layout.setSpacing(0)
        
        # SQL panel header
        sql_header = QFrame()
        sql_header.setObjectName("panel_header")
        sql_header.setFixedHeight(35)
        sql_header_layout = QHBoxLayout(sql_header)
        sql_header_layout.setContentsMargins(12, 8, 12, 8)
        
        sql_title = QLabel("📄 Query Worksheet")
        sql_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        sql_header_layout.addWidget(sql_title)
        
        sql_layout.addWidget(sql_header)
        
        # SQL text area
        self.sql_text = QTextEdit()
        self.sql_text.setFont(QFont("Consolas", 11))
        self.sql_text.setObjectName("sql_text_area")
        self.sql_text.setPlaceholderText("SQL query will be displayed here when you select a query...")
        sql_layout.addWidget(self.sql_text)
        
        return sql_frame
        
    def create_results_panel(self):
        """Create the query results panel"""
        results_frame = QFrame()
        results_frame.setObjectName("results_panel")
        results_layout = QVBoxLayout(results_frame)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)
        
        # Results panel header
        results_header = QFrame()
        results_header.setObjectName("panel_header")
        results_header.setFixedHeight(35)
        results_header_layout = QHBoxLayout(results_header)
        results_header_layout.setContentsMargins(12, 8, 12, 8)
        
        results_title = QLabel("📊 Query Results")
        results_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        results_header_layout.addWidget(results_title)
        
        # Results status (right side)
        self.results_status_label = QLabel("Ready")
        self.results_status_label.setFont(QFont("Segoe UI", 10))
        results_header_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        results_header_layout.addWidget(self.results_status_label)
        
        results_layout.addWidget(results_header)
        
        # Progress Bar Frame (Matrix-themed, hidden by default)
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("matrix_progress_frame")
        self.progress_frame.setFixedHeight(60)
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(20, 8, 20, 8)
        
        # Progress bar with Matrix green theme
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setObjectName("matrix_progress_bar")
        progress_layout.addWidget(self.progress_bar)
        
        # Progress label
        self.progress_label = QLabel("Initializing...")
        self.progress_label.setFont(QFont("Consolas", 9))
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setObjectName("matrix_progress_label")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_frame.hide()  # Hidden initially
        results_layout.addWidget(self.progress_frame)
        
        # Results text area
        self.results_text = QTextEdit()
        self.results_text.setFont(QFont("Consolas", 10))
        self.results_text.setObjectName("results_text_area")
        self.results_text.setPlaceholderText("Query results will appear here...\n\nReady to execute queries.")
        results_layout.addWidget(self.results_text)
        
        return results_frame
        
    def create_status_bar(self):
        """Create bottom status bar"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        
        self.status_label = QLabel("No connections")
        self.status_label.setFont(QFont("Segoe UI", 10))
        status_bar.addWidget(self.status_label)
        
    def show_welcome_screen(self):
        """Show the welcome screen"""
        self.workspace_stack.setCurrentWidget(self.welcome_view)
        
    def show_connected_screen(self):
        """Show the connected workspace"""
        self.workspace_stack.setCurrentWidget(self.connected_view)
        
    def refresh_sidebar(self):
        """Refresh the connections sidebar"""
        # Clear existing connections
        for i in reversed(range(self.connections_layout.count())):
            child = self.connections_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
                
        if not self.connections:
            # Show "no connections" message
            no_conn_label = QLabel("No connections yet.")
            no_conn_label.setFont(QFont("Segoe UI", 11))
            no_conn_label.setStyleSheet("color: #888888; padding: 4px;")
            self.connections_layout.addWidget(no_conn_label)
        else:
            # Add connection items (will implement in next step)
            for i, conn in enumerate(self.connections):
                conn_button = QPushButton(conn.get("label", f"Connection {i+1}"))
                conn_button.setFont(QFont("Segoe UI", 10))
                conn_button.setObjectName("connection_item")
                self.connections_layout.addWidget(conn_button)
                
        # Add stretch to push connections to top
        self.connections_layout.addStretch()
        
    def apply_dark_theme(self):
        """Apply dark theme styling"""
        dark_stylesheet = """
        /* Main Window */
        QMainWindow {
            background-color: #111111;
            color: white;
        }
        
        /* Toolbar */
        QToolBar#main_toolbar {
            background-color: #2a2a2a;
            border: none;
            spacing: 8px;
            padding: 6px;
        }
        
        QToolBar#main_toolbar QAction {
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: bold;
            font-size: 18px;
        }
        
        QToolBar#main_toolbar QAction:hover {
            background-color: #218838;
        }
        
        /* Sidebar */
        QFrame#sidebar {
            background-color: #1f1f1f;
            border-right: 1px solid #333333;
        }
        
        QLabel#sidebar_header {
            color: white;
            font-weight: bold;
            padding-bottom: 6px;
        }
        
        QScrollArea#connections_scroll {
            border: none;
            background-color: transparent;
        }
        
        QPushButton#connection_item {
            background-color: #2a2a2a;
            border: 1px solid #404040;
            border-radius: 4px;
            padding: 8px;
            text-align: left;
            color: white;
        }
        
        QPushButton#connection_item:hover {
            background-color: #3a3a3a;
        }
        
        QPushButton#connection_item:pressed {
            background-color: #4a4a4a;
        }
        
        /* Workspace */
        QStackedWidget#workspace {
            background-color: #111111;
        }
        
        /* Welcome Screen */
        QLabel#welcome_title {
            color: white;
            margin: 30px 0 8px 0;
        }
        
        QLabel#welcome_subtitle {
            color: #cccccc;
        }
        
        /* Connected View */
        QFrame#header_frame {
            background-color: #2a2a2a;
            border: none;
            border-radius: 4px;
        }
        
        QFrame#sql_panel, QFrame#results_panel {
            background-color: #1a1a1a;
            border: none;
            border-radius: 4px;
        }
        
        QFrame#panel_header {
            background-color: #2a2a2a;
            border: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        
        /* Status Bar */
        QStatusBar {
            background-color: #2a2a2a;
            border-top: 1px solid #404040;
            color: white;
        }
        
        /* Query Controls */
        QComboBox#query_dropdown {
            background-color: #2a2a2a;
            border: 1px solid #404040;
            border-radius: 4px;
            padding: 6px 12px;
            color: white;
            margin: 0 8px;
        }
        
        QComboBox#query_dropdown:hover {
            border: 1px solid #2b5797;
        }
        
        QComboBox#query_dropdown::drop-down {
            border: none;
        }
        
        QComboBox#query_dropdown::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid white;
            margin-right: 10px;
        }
        
        QPushButton#execute_query_button {
            background-color: #2b5797;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            color: white;
            font-weight: bold;
            margin-left: 5px;
        }
        
        QPushButton#execute_query_button:hover {
            background-color: #1e4a7a;
        }
        
        QPushButton#execute_query_button:pressed {
            background-color: #164a6b;
        }
        
        /* SQL and Results Text Areas */
        QTextEdit#sql_text_area, QTextEdit#results_text_area {
            background-color: #0f0f0f;
            border: none;
            color: white;
            selection-background-color: #2b5797;
            padding: 8px;
        }
        
        QTextEdit#sql_text_area {
            color: #ffffff;
            font-family: 'Consolas';
        }
        
        QTextEdit#results_text_area {
            color: #00ff00;
            font-family: 'Consolas';
        }
        
        /* Matrix Progress Bar */
        QFrame#matrix_progress_frame {
            background-color: #2a2a2a;
            border: 1px solid #00ff00;
            border-radius: 4px;
        }
        
        QProgressBar#matrix_progress_bar {
            background-color: #000000;
            border: 1px solid #404040;
            border-radius: 4px;
            text-align: center;
            color: #00ff00;
            font-family: 'Consolas';
            font-weight: bold;
        }
        
        QProgressBar#matrix_progress_bar::chunk {
            background-color: #00ff00;
            border-radius: 3px;
        }
        
        QLabel#matrix_progress_label {
            color: #00ff00;
            font-family: 'Consolas';
            font-size: 9px;
        }
        
        /* Splitter */
        QSplitter::handle {
            background-color: #404040;
        }
        
        QSplitter::handle:horizontal {
            width: 1px;
        }
        
        QSplitter::handle:vertical {
            height: 3px;
        }
        
        QSplitter::handle:hover {
            background-color: #2b5797;
        }
        """
        
        self.setStyleSheet(dark_stylesheet)
        
    # --------- Event Handlers ---------
    def add_connection(self):
        """Handle add connection button click - open database dialog"""
        print("Opening database connection dialog...")
        
        # Open connection dialog
        dialog = DatabaseConnectionDialog(self)
        result = dialog.exec()
        
        if result == dialog.DialogCode.Accepted:
            engine, meta = dialog.get_connection_result()
            if engine and meta:
                # Create connection entry
                conn_label = f"{meta.get('username', 'user')}@{meta.get('database', 'db')}"
                connection = {
                    "label": conn_label,
                    "engine": engine,
                    "meta": meta
                }
                
                self.connections.append(connection)
                self.refresh_sidebar()
                
                # Set as active connection
                self.active_engine = engine
                self.active_meta = meta
                
                # Update status and switch to connected view
                self.status_label.setText(f"Connected: {conn_label}")
                self.show_connected_screen()
                self.connection_status_label.setText(f"🟢 Connected to {meta.get('database', '')} as {meta.get('username', '')}")
                
                print(f"✅ Connection successful: {conn_label}")
        else:
            print("Connection dialog cancelled")

    def create_query_controls(self, layout):
        """Create query dropdown and execute button"""
        # Query selection label
        query_label = QLabel("Select Query:")
        query_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(query_label)
        
        # Query dropdown
        self.query_dropdown = QComboBox()
        self.query_dropdown.setFont(QFont("Segoe UI", 11))
        self.query_dropdown.setMinimumWidth(220)
        self.query_dropdown.setFixedHeight(32)
        self.query_dropdown.setObjectName("query_dropdown")
        
        # Populate dropdown with queries
        query_options = [f"{q['icon']} {q['name']}" for q in queries.values()]
        self.query_dropdown.addItems(query_options)
        
        # Connect selection change to update SQL display
        self.query_dropdown.currentTextChanged.connect(self.on_query_selection_changed)
        
        layout.addWidget(self.query_dropdown)
        
        # Execute button
        execute_btn = QPushButton("🚀 Execute Query")
        execute_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        execute_btn.setFixedSize(140, 32)
        execute_btn.setObjectName("execute_query_button")
        execute_btn.clicked.connect(self.execute_selected_query)
        layout.addWidget(execute_btn)
        
        # Set default selection (SQL update will happen later when sql_text is ready)
        if query_options:
            self.query_dropdown.setCurrentIndex(0)
    
    def on_query_selection_changed(self, selected_text):
        """Handle query selection change - update SQL display"""
        query_key = self.parse_query_selection(selected_text)
        if query_key and query_key in queries:
            query_config = queries[query_key]
            # Only update SQL text if it exists (may not be created yet during init)
            if hasattr(self, 'sql_text'):
                self.sql_text.setPlainText(query_config["sql"])
    
    def parse_query_selection(self, selected_text):
        """Parse dropdown selection text to get query key"""
        for key, config in queries.items():
            expected_text = f"{config['icon']} {config['name']}"
            if selected_text == expected_text:
                return key
        return None
    
    def update_initial_sql_display(self):
        """Update SQL display after all components are created"""
        if hasattr(self, 'query_dropdown') and hasattr(self, 'sql_text'):
            selected_text = self.query_dropdown.currentText()
            self.on_query_selection_changed(selected_text)
    
    def execute_selected_query(self):
        """Execute the selected query"""
        print("Execute Query clicked!")
        
        # Check if connected
        if not self.active_engine:
            QMessageBox.warning(self, "No Connection", "Please connect to a database first.")
            return
        
        # Get selected query
        selected_text = self.query_dropdown.currentText()
        query_key = self.parse_query_selection(selected_text)
        
        if not query_key:
            QMessageBox.critical(self, "Invalid Selection", f"Could not identify query: {selected_text}")
            return
        
        # Get query configuration
        query_config = queries[query_key]
        print(f"Executing query: {query_config['name']}")
        
        # Show parameter dialog
        params = self.get_query_parameters(query_key, query_config)
        if not params:
            print("Parameter dialog cancelled")
            return
        
        # Execute query with parameters
        self.run_query_with_progress(query_key, query_config, params)
    
    def get_query_parameters(self, query_key, query_config):
        """Show parameter input dialog"""
        dialog = QueryParameterDialog(query_config, self)
        result = dialog.exec()
        
        if result == dialog.DialogCode.Accepted:
            return dialog.get_parameters()
        
        return None
    
    def run_query_with_progress(self, query_key, query_config, params):
        """Execute query with progress updates using Qt threading"""
        print(f"Starting query execution: {query_config['name']}")
        
        # Show progress
        self.show_progress_bar()
        self.update_progress(0, "[MATRIX] Initializing query execution...")
        self.results_status_label.setText("Running...")
        
        # Clear previous results
        self.results_text.clear()
        self.results_text.append(f"Executing {query_config['name']}...\n")
        
        # Create worker and thread
        self.query_thread = QThread()
        self.query_worker = QueryWorker(self.active_engine, query_config, params)
        
        # Move worker to thread
        self.query_worker.moveToThread(self.query_thread)
        
        # Connect signals
        self.query_worker.progress_updated.connect(self.update_progress)
        self.query_worker.query_completed.connect(self.display_query_results)
        self.query_worker.query_failed.connect(self.handle_query_error)
        
        # Connect thread signals
        self.query_thread.started.connect(self.query_worker.run_query)
        self.query_worker.query_completed.connect(self.query_thread.quit)
        self.query_worker.query_failed.connect(self.query_thread.quit)
        self.query_thread.finished.connect(self.query_worker.deleteLater)
        self.query_thread.finished.connect(self.query_thread.deleteLater)
        
        # Start thread
        self.query_thread.start()
    
    def show_progress_bar(self):
        """Show the Matrix-themed progress bar"""
        self.progress_frame.show()
        self.progress_bar.setValue(0)
        
    def hide_progress_bar(self):
        """Hide the progress bar"""
        self.progress_frame.hide()
        
    def update_progress(self, value, text):
        """Update progress bar and label"""
        self.progress_bar.setValue(value)
        self.progress_label.setText(text)
        
    def display_query_results(self, query_config, rows, columns, query_time, params):
        """Display query results in the text area and handle Excel export"""
        self.update_progress(80, "[MATRIX] Processing results...")
        
        # Handle Excel export if enabled
        excel_filename = None
        excel_enabled = params.get('export_excel', False)
        
        if excel_enabled:
            try:
                # Convert back to DataFrame for export (same as V4)
                import pandas as pd
                from PySide6.QtWidgets import QMessageBox  # Import at top level
                df = pd.DataFrame(rows, columns=columns)
                
                # Fix timezone issue - convert timezone-aware datetime columns to timezone-naive
                for col in df.columns:
                    if pd.api.types.is_datetime64tz_dtype(df[col]):
                        print(f"DEBUG: Converting timezone-aware column '{col}' to timezone-naive")
                        df[col] = df[col].dt.tz_convert('UTC').dt.tz_localize(None)
                
                # Create filename (same format as V4)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                username = params.get('username', 'unknown')
                query_name = query_config['name'].replace(' ', '').replace('&', 'and')
                excel_filename = f"{query_name}Logs_{username}_{timestamp}.xlsx"
                
                self.update_progress(90, "[MATRIX] Exporting to Excel...")
                
                # Debug info like V4
                print(f"DEBUG: About to save {len(df)} rows to {excel_filename}")
                print(f"DEBUG: DataFrame shape: {df.shape}")
                print(f"DEBUG: DataFrame columns: {list(df.columns)}")
                print(f"DEBUG: DataFrame dtypes: {dict(df.dtypes)}")
                
                # Save to Excel with retry logic like V4
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        df.to_excel(excel_filename, index=False)
                        print(f"DEBUG: Excel file saved successfully: {excel_filename}")
                        break
                    except PermissionError:
                        if attempt < max_retries - 1:
                            reply = QMessageBox.question(self, "File in Use", 
                                f"Unable to save {excel_filename}. The file may be open. Close it and retry?",
                                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel)
                            if reply == QMessageBox.StandardButton.Retry:
                                continue
                        excel_filename = None
                        print(f"DEBUG: Excel export failed - file in use")
                        QMessageBox.warning(self, "Export Error", f"Unable to save Excel file - it may be open in another program.")
                        break
                    except Exception as e:
                        excel_filename = None
                        print(f"DEBUG: Excel export failed: {str(e)}")
                        QMessageBox.warning(self, "Export Error", f"Excel export failed:\n{str(e)}")
                        break
                
            except Exception as e:
                excel_filename = None
                print(f"DEBUG: Excel export setup failed: {e}")
                import traceback
                traceback.print_exc()
                from PySide6.QtWidgets import QMessageBox  # Import here too for safety
                QMessageBox.warning(self, "Export Error", f"Excel export failed:\n{str(e)}")
        else:
            print("DEBUG: Excel export disabled by user")
        
        self.update_progress(100, "[MATRIX] Query execution complete!")
        
        # Format results display
        result_text = f"{query_config['name']} - Completed Successfully!\n\n"
        result_text += f"Execution Time: {query_time:.2f} seconds\n"
        result_text += f"Rows Retrieved: {len(rows):,}\n"
        result_text += f"Parameters Used:\n"
        for key, value in params.items():
            if key != 'export_excel':  # Don't show internal parameters
                result_text += f"  • {key}: {value}\n"
        result_text += f"  • Excel Export: {'ENABLED' if excel_enabled else 'DISABLED'}\n"
        
        if excel_filename:
            result_text += f"\nExcel file saved: {excel_filename}\n"
        
        result_text += f"\nFirst 10 rows:\n"
        result_text += "=" * 50 + "\n"
        
        # Show column headers
        headers = " | ".join([str(col) for col in columns])
        result_text += headers + "\n"
        result_text += "-" * len(headers) + "\n"
        
        # Show first 10 rows
        for i, row in enumerate(rows[:10]):
            row_text = " | ".join([str(cell)[:30] for cell in row])
            result_text += f"{row_text}\n"
        
        if len(rows) > 10:
            result_text += f"\n... and {len(rows) - 10} more rows\n"
        
        result_text += "\n" + "=" * 50
        result_text += f"\nQuery completed at {datetime.now().strftime('%H:%M:%S')}"
        
        self.results_text.setPlainText(result_text)
        self.results_status_label.setText(f"Complete ({len(rows):,} rows)")
        
        # Hide progress bar after brief delay
        QTimer.singleShot(1000, self.hide_progress_bar)
        
    def handle_query_error(self, error_message):
        """Handle query execution error"""
        self.hide_progress_bar()
        self.results_status_label.setText("Error")
        
        error_text = f"Query Execution Failed\n\n"
        error_text += f"Error: {error_message}\n"
        error_text += f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
        error_text += "Please check your query parameters and try again."
        
        self.results_text.setPlainText(error_text)
        
        QMessageBox.critical(self, "Query Failed", f"Query execution failed:\n\n{error_message}")


class QueryParameterDialog(QDialog):
    """Dialog for collecting query parameters"""
    
    def __init__(self, query_config, parent=None):
        super().__init__(parent)
        self.query_config = query_config
        self.parameters = {}
        self.entries = {}
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the parameter dialog UI"""
        self.setWindowTitle(f"Parameters - {self.query_config['name']}")
        self.resize(520, 450)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header_label = QLabel(f"Parameters for {self.query_config['name']}")
        header_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)
        
        # Description
        desc_label = QLabel(self.query_config['description'])
        desc_label.setFont(QFont("Segoe UI", 11))
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #cccccc; margin: 10px;")
        layout.addWidget(desc_label)
        
        # Parameters form
        form_widget = QFrame()
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(15)
        
        for param in self.query_config['parameters']:
            label = QLabel(f"{param['label']}:")
            label.setFont(QFont("Segoe UI", 11))
            
            if param['type'] == 'date':
                widget = QDateEdit()
                widget.setDate(QDate.currentDate())
                widget.setDisplayFormat("yyyy-MM-dd")
                widget.setCalendarPopup(True)
            else:
                widget = QLineEdit()
                if 'placeholder' in param:
                    widget.setPlaceholderText(param['placeholder'])
            
            widget.setFont(QFont("Segoe UI", 11))
            widget.setMinimumHeight(32)
            widget.setObjectName("param_field")
            
            self.entries[param['name']] = widget
            form_layout.addRow(label, widget)
        
        layout.addWidget(form_widget)
        
        # Processing options
        options_frame = QFrame()
        options_layout = QVBoxLayout(options_frame)
        
        options_title = QLabel("Processing Options:")
        options_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        options_layout.addWidget(options_title)
        
        # Geolocation checkbox
        self.include_geo_checkbox = QCheckBox("Include IP Geolocation (~45s for optimized processing)")
        self.include_geo_checkbox.setFont(QFont("Segoe UI", 11))
        self.include_geo_checkbox.setChecked(True)
        options_layout.addWidget(self.include_geo_checkbox)
        
        # Excel export checkbox
        self.export_excel_checkbox = QCheckBox("Export to Excel file")
        self.export_excel_checkbox.setFont(QFont("Segoe UI", 11))
        self.export_excel_checkbox.setChecked(True)
        options_layout.addWidget(self.export_excel_checkbox)
        
        layout.addWidget(options_frame)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        execute_btn = QPushButton("🚀 Execute Query")
        execute_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        execute_btn.setObjectName("execute_button")
        execute_btn.clicked.connect(self.accept_parameters)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(execute_btn)
        layout.addLayout(button_layout)
        
        # Apply styling
        self.apply_parameter_styling()
    
    def accept_parameters(self):
        """Validate and accept parameters"""
        # Collect parameter values
        for param in self.query_config['parameters']:
            widget = self.entries[param['name']]
            
            if isinstance(widget, QDateEdit):
                value = widget.date().toString("yyyy-MM-dd")
            else:
                value = widget.text().strip()
            
            # Validate required fields
            if param.get('required', False) and not value:
                QMessageBox.warning(self, "Missing Required Field", 
                                  f"{param['label']} is required.")
                return
            
            self.parameters[param['name']] = value
        
        # Add processing options
        self.parameters['include_geolocation'] = self.include_geo_checkbox.isChecked()
        self.parameters['export_excel'] = self.export_excel_checkbox.isChecked()
        
        self.accept()
    
    def get_parameters(self):
        """Get the collected parameters"""
        return self.parameters
    
    def apply_parameter_styling(self):
        """Apply dark theme styling"""
        stylesheet = """
        QDialog {
            background-color: #111111;
            color: white;
        }
        
        QLineEdit#param_field, QDateEdit {
            background-color: #2a2a2a;
            border: 1px solid #404040;
            border-radius: 4px;
            padding: 6px 12px;
            color: white;
        }
        
        QLineEdit#param_field:focus, QDateEdit:focus {
            border: 2px solid #2b5797;
        }
        
        QCheckBox {
            color: white;
            spacing: 8px;
        }
        
        QPushButton#execute_button {
            background-color: #2b5797;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            color: white;
        }
        
        QPushButton#execute_button:hover {
            background-color: #1e4a7a;
        }
        """
        self.setStyleSheet(stylesheet)


class DatabaseConnectionDialog(QDialog):
    """Database connection dialog matching CustomTkinter design"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Connection result
        self.engine = None
        self.meta = None
        
        # Initialize UI
        self.init_ui()
        self.load_saved_credentials()
        
    def init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Add Database Connection")
        self.resize(550, 480)  # Larger size, allow resize
        self.setMinimumSize(500, 420)  # Set minimum but allow resize
        self.setModal(True)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Create main frame (equivalent to CTkFrame)
        main_frame = QFrame()
        main_frame.setObjectName("connection_dialog_frame")
        frame_layout = QVBoxLayout(main_frame)
        frame_layout.setContentsMargins(30, 25, 30, 25)
        frame_layout.setSpacing(5)
        
        # Title
        title_label = QLabel("New Connection")
        title_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("dialog_title")
        frame_layout.addWidget(title_label)
        
        # Connection form
        self.create_connection_form(frame_layout)
        
        # Credentials section
        self.create_credentials_section(frame_layout)
        
        # Progress section (hidden initially)
        self.create_progress_section(frame_layout)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.connect_btn.setMinimumHeight(45)  # Taller button
        self.connect_btn.setObjectName("connect_button")
        self.connect_btn.clicked.connect(self.start_connection)
        frame_layout.addWidget(self.connect_btn)
        
        layout.addWidget(main_frame)
        
        # Apply styling
        self.apply_dialog_styling()
        
    def create_connection_form(self, layout):
        """Create the connection form fields"""
        self.entries = {}
        
        fields = [
            ("Username", False),
            ("Password", True),  # True = password field
            ("Host", False),
            ("Port", False),
            ("Database", False)
        ]
        
        for field_name, is_password in fields:
            # Label
            label = QLabel(f"{field_name}:")
            label.setFont(QFont("Segoe UI", 11))
            label.setContentsMargins(0, 8, 0, 2)  # Add spacing above labels
            layout.addWidget(label)
            
            # Entry
            entry = QLineEdit()
            entry.setFont(QFont("Segoe UI", 11))
            entry.setMinimumHeight(36)  # Taller fields
            entry.setMinimumWidth(400)  # Wider fields
            entry.setObjectName("connection_field")
            
            if is_password:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            
            # Set placeholders
            placeholders = {
                "Host": "localhost",
                "Port": "5432", 
                "Database": "canvasdata2"
            }
            if field_name in placeholders:
                entry.setPlaceholderText(placeholders[field_name])
            
            self.entries[field_name] = entry
            layout.addWidget(entry)
            
    def create_credentials_section(self, layout):
        """Create the save credentials section"""
        creds_frame = QFrame()
        creds_layout = QHBoxLayout(creds_frame)
        creds_layout.setContentsMargins(10, 10, 10, 10)
        
        # Save credentials checkbox
        self.save_creds_checkbox = QCheckBox("Save credentials securely")
        self.save_creds_checkbox.setFont(QFont("Segoe UI", 11))
        creds_layout.addWidget(self.save_creds_checkbox)
        
        creds_layout.addStretch()
        
        # Clear saved button
        clear_btn = QPushButton("Clear Saved")
        clear_btn.setFont(QFont("Segoe UI", 10))
        clear_btn.setFixedSize(110, 28)
        clear_btn.setObjectName("clear_button")
        clear_btn.clicked.connect(self.clear_saved_credentials)
        creds_layout.addWidget(clear_btn)
        
        layout.addWidget(creds_frame)
        
    def create_progress_section(self, layout):
        """Create the progress section (hidden initially)"""
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("progress_frame")
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(20, 10, 20, 10)
        
        # Progress label
        self.progress_label = QLabel("Connecting...")
        self.progress_label.setFont(QFont("Segoe UI", 11))
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setObjectName("connection_progress")
        progress_layout.addWidget(self.progress_bar)
        
        # Hide initially
        self.progress_frame.hide()
        layout.addWidget(self.progress_frame)
        
    def load_saved_credentials(self):
        """Load saved credentials if available"""
        try:
            # Import credential manager from existing code
            from pathlib import Path
            import json
            import keyring
            
            config_file = Path("canvas_config.json")
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                # Load password from keyring
                password = keyring.get_password("CanvasDataAutomator::default", config["username"])
                
                if password:
                    self.entries["Username"].setText(config["username"])
                    self.entries["Password"].setText(password)
                    self.entries["Host"].setText(config["host"])
                    self.entries["Port"].setText(config["port"])
                    self.entries["Database"].setText(config["database"])
                    self.save_creds_checkbox.setChecked(True)
                    return True
        except Exception as e:
            print(f"Could not load saved credentials: {e}")
        
        return False
        
    def clear_saved_credentials(self):
        """Clear saved credentials"""
        try:
            from pathlib import Path
            import keyring
            
            # Clear entries
            for entry in self.entries.values():
                entry.clear()
            
            self.save_creds_checkbox.setChecked(False)
            
            # Clear saved files and keyring
            config_file = Path("canvas_config.json")
            if config_file.exists():
                config_file.unlink()
            
            # Note: We can't easily clear all keyring entries without knowing usernames
            # This is a limitation we'll document
            
            QMessageBox.information(self, "Success", "Saved credentials cleared")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear credentials: {str(e)}")
            
    def start_connection(self):
        """Start the connection process"""
        self.connect_btn.setEnabled(False)
        self.progress_frame.show()
        self.progress_bar.setValue(10)
        self.progress_label.setText("Validating connection details...")
        
        # Use QTimer for async processing to keep UI responsive
        QTimer.singleShot(100, self.connect_database)
        
    def connect_database(self):
        """Connect to database"""
        try:
            # Get form values
            username = self.entries["Username"].text().strip()
            password = self.entries["Password"].text().strip()
            host = self.entries["Host"].text().strip() or "localhost"
            port = self.entries["Port"].text().strip() or "5432"
            database = self.entries["Database"].text().strip() or "canvasdata2"
            
            # Update progress
            self.progress_bar.setValue(30)
            self.progress_label.setText("Preparing connection string...")
            QApplication.processEvents()
            
            # Validate inputs
            if not username or not password:
                self.connection_error("Username and password are required.")
                return
            
            try:
                port_num = int(port)
                if not (1 <= port_num <= 65535):
                    raise ValueError()
            except ValueError:
                self.connection_error("Port must be a number between 1 and 65535.")
                return
            
            # Create connection string
            import re
            if re.search("redshift", host, re.IGNORECASE):
                conn_str = f"redshift+psycopg2://{username}:{password}@{host}:{port_num}/{database}"
            else:
                conn_str = f"postgresql+psycopg2://{username}:{password}@{host}:{port_num}/{database}?options=-c%20client_encoding=utf8"
            
            self.progress_bar.setValue(50)
            self.progress_label.setText("Creating database engine...")
            QApplication.processEvents()
            
            # Create engine
            from sqlalchemy import create_engine, text
            temp_engine = create_engine(conn_str)
            
            self.progress_bar.setValue(70)
            self.progress_label.setText("Testing connection...")
            QApplication.processEvents()
            
            # Test connection
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
            
            self.progress_bar.setValue(100)
            self.progress_label.setText("Connection successful!")
            QApplication.processEvents()
            
            # Save credentials if requested
            if self.save_creds_checkbox.isChecked():
                self.save_credentials(username, password, host, port, database)
            
            # Store results
            self.engine = temp_engine
            self.meta = {
                "username": username,
                "host": host,
                "port": port,
                "database": database
            }
            
            # Close dialog successfully after a brief delay
            QTimer.singleShot(500, self.accept)
            
        except Exception as e:
            self.connection_error(f"Could not connect:\n{str(e)}")
            
    def connection_error(self, message):
        """Handle connection error"""
        self.progress_frame.hide()
        self.connect_btn.setEnabled(True)
        QMessageBox.critical(self, "Connection Failed", message)
        
    def save_credentials(self, username, password, host, port, database):
        """Save credentials securely"""
        try:
            import keyring
            import json
            from pathlib import Path
            from datetime import datetime
            
            # Save password to keyring
            keyring.set_password("CanvasDataAutomator::default", username, password)
            
            # Save other details to config file
            config = {
                "username": username,
                "host": host,
                "port": port,
                "database": database,
                "saved_at": datetime.now().isoformat()
            }
            
            with open("canvas_config.json", 'w') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            print(f"Could not save credentials: {e}")
            
    def get_connection_result(self):
        """Get the connection result"""
        return self.engine, self.meta
        
    def apply_dialog_styling(self):
        """Apply dark theme styling to dialog"""
        dialog_stylesheet = """
        QDialog {
            background-color: #111111;
            color: white;
        }
        
        QFrame#connection_dialog_frame {
            background-color: #1a1a1a;
            border: none;
            border-radius: 20px;
        }
        
        QLabel#dialog_title {
            color: white;
            margin: 10px 0;
        }
        
        QLabel {
            color: white;
            margin-bottom: 2px;
        }
        
        QLineEdit#connection_field {
            background-color: #2a2a2a;
            border: 1px solid #404040;
            border-radius: 6px;
            padding: 8px 16px;
            color: white;
            margin-bottom: 8px;
            font-size: 12px;
        }
        
        QLineEdit#connection_field:focus {
            border: 2px solid #2b5797;
        }
        
        QCheckBox {
            color: white;
            spacing: 8px;
        }
        
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        
        QCheckBox::indicator:unchecked {
            background-color: #2a2a2a;
            border: 1px solid #404040;
            border-radius: 3px;
        }
        
        QCheckBox::indicator:checked {
            background-color: #2b5797;
            border: 1px solid #2b5797;
            border-radius: 3px;
        }
        
        QPushButton#connect_button {
            background-color: #0078d7;
            border: none;
            border-radius: 12px;
            padding: 12px 24px;
            color: white;
            font-weight: bold;
            font-size: 13px;
            margin: 15px 20px;
        }
        
        QPushButton#connect_button:hover {
            background-color: #005a9e;
        }
        
        QPushButton#connect_button:pressed {
            background-color: #004578;
        }
        
        QPushButton#connect_button:disabled {
            background-color: #666666;
            color: #999999;
        }
        
        QPushButton#clear_button {
            background-color: #404040;
            border: 1px solid #666666;
            border-radius: 4px;
            padding: 4px 8px;
            color: white;
        }
        
        QPushButton#clear_button:hover {
            background-color: #505050;
        }
        
        QFrame#progress_frame {
            background-color: transparent;
            border: none;
            margin: 10px 0;
        }
        
        QProgressBar#connection_progress {
            background-color: #2a2a2a;
            border: 1px solid #404040;
            border-radius: 6px;
            text-align: center;
            color: white;
        }
        
        QProgressBar#connection_progress::chunk {
            background-color: #0078d7;
            border-radius: 5px;
        }
        """
        
        self.setStyleSheet(dialog_stylesheet)
        



def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Canvas Data Automator")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Canvas Data Tools")
    
    # Enable high DPI scaling (Qt 6.x handles this automatically)
    # These attributes are deprecated in Qt 6 but kept for compatibility
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass  # Qt 6.x handles high DPI automatically
    
    # Create and show main window
    window = CanvasDataApp()
    window.show()
    
    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()