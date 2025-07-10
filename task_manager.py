import sys
import os
import sqlite3
import uuid
import random
from datetime import datetime, timedelta
import pendulum
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QCalendarWidget, QListWidget, QListWidgetItem, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QLabel, QDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QSpinBox, QDateEdit, QTimeEdit, QScrollArea,
    QProgressBar, QSizePolicy, QToolButton, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, QTranslator, QLocale, QDate, QTime, QPropertyAnimation, QEasingCurve, QSize, QRect
from PyQt6.QtGui import QColor, QIcon, QFont, QPalette, QPainter, QLinearGradient
from PyQt6.QtSvgWidgets import QSvgWidget
import qdarkstyle
from plyer import notification
import win32api
import win32con

class Database:
    def __init__(self):
        self.db_path = 'tasks.db'
        self.conn = sqlite3.connect(self.db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                time TEXT,
                priority TEXT,
                category TEXT,
                is_recurring BOOLEAN,
                recurring_type TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                notes TEXT,
                attachment_path TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                date TEXT PRIMARY KEY,
                completion_percentage REAL,
                task_ids TEXT,
                total_tasks INTEGER,
                completed_tasks INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT
            )
        ''')
        self.conn.commit()

    def add_task(self, title, description, date, time, priority, category, is_recurring, recurring_type, notes, attachment_path):
        cursor = self.conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO tasks (title, description, date, time, priority, category, is_recurring, recurring_type, status, created_at, updated_at, notes, attachment_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, date, time, priority, category, is_recurring, recurring_type, 'pending', created_at, created_at, notes, attachment_path))
        self.conn.commit()
        task_id = cursor.lastrowid
        if is_recurring:
            self.add_recurring_tasks(task_id, date, recurring_type, title, description, time, priority, category, notes, attachment_path)
        return task_id

    def add_recurring_tasks(self, task_id, start_date, recurring_type, title, description, time, priority, category, notes, attachment_path):
        cursor = self.conn.cursor()
        start = pendulum.parse(start_date)
        end = start.add(years=9)
        delta = {
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'monthly': timedelta(days=30),
            'yearly': timedelta(days=365)
        }.get(recurring_type, timedelta(days=1))
        current = start.add(days=1)
        created_at = datetime.now().isoformat()
        while current <= end:
            cursor.execute('''
                INSERT INTO tasks (title, description, date, time, priority, category, is_recurring, recurring_type, status, created_at, updated_at, notes, attachment_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, description, current.to_date_string(), time, priority, category, True, recurring_type, 'pending', created_at, created_at, notes, attachment_path))
            current = current + delta
        self.conn.commit()

    def get_tasks(self, date):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE date = ?', (date,))
        return cursor.fetchall()

    def get_all_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tasks ORDER BY date')
        return cursor.fetchall()

    def update_task_status(self, task_id, status):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?', (status, datetime.now().isoformat(), task_id))
        self.conn.commit()

    def update_task(self, task_id, title, description, time, priority, category, notes, attachment_path):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE tasks SET title = ?, description = ?, time = ?, priority = ?, category = ?, notes = ?, attachment_path = ?, updated_at = ?
            WHERE id = ?
        ''', (title, description, time, priority, category, notes, attachment_path, datetime.now().isoformat(), task_id))
        self.conn.commit()

    def delete_task(self, task_id, all_future=False):
        cursor = self.conn.cursor()
        cursor.execute('SELECT date, is_recurring, recurring_type, title FROM tasks WHERE id = ?', (task_id,))
        task = cursor.fetchone()
        if all_future and task[1]:
            cursor.execute('DELETE FROM tasks WHERE title = ? AND is_recurring = ? AND date >= ?',
                          (task[3], 1, task[0]))
        else:
            cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        self.conn.commit()

    def get_history(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM history ORDER BY date DESC')
        return cursor.fetchall()

    def update_history(self, date):
        cursor = self.conn.cursor()
        tasks = self.get_tasks(date)
        if tasks:
            total_tasks = len(tasks)
            completed_tasks = sum(1 for task in tasks if task[9] == 'completed')
            percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            task_ids = ','.join(str(task[0]) for task in tasks)
            cursor.execute('''
                INSERT OR REPLACE INTO history (date, completion_percentage, task_ids, total_tasks, completed_tasks)
                VALUES (?, ?, ?, ?, ?)
            ''', (date, percentage, task_ids, total_tasks, completed_tasks))
            self.conn.commit()

    def add_category(self, name, color):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO categories (name, color) VALUES (?, ?)', (name, color))
        self.conn.commit()

    def get_categories(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT name FROM categories')
        return [row[0] for row in cursor.fetchall()]

    def save_setting(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        self.conn.commit()

    def get_setting(self, key, default=None):
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        return result[0] if result else default

    def search_tasks(self, query):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE title LIKE ? OR description LIKE ?', (f'%{query}%', f'%{query}%'))
        return cursor.fetchall()

    def backup_database(self, path):
        import shutil
        shutil.copyfile(self.db_path, path)

    def restore_database(self, path):
        import shutil
        self.conn.close()
        shutil.copyfile(path, self.db_path)
        self.conn = sqlite3.connect(self.db_path)

class TaskDialog(QDialog):
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        self.db = parent.db
        self.setWindowTitle(self.tr('Add Task') if not task else self.tr('Edit Task'))
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(10)

        # Title
        layout.addWidget(QLabel(self.tr('Title')), 0, 0)
        self.title_edit = QLineEdit(self.task[1] if self.task else '')
        self.title_edit.setPlaceholderText(self.tr('Enter task title'))
        layout.addWidget(self.title_edit, 0, 1, 1, 2)

        # Description
        layout.addWidget(QLabel(self.tr('Description')), 1, 0)
        self.desc_edit = QTextEdit(self.task[2] if self.task else '')
        self.desc_edit.setPlaceholderText(self.tr('Enter task description'))
        self.desc_edit.setMinimumHeight(100)
        layout.addWidget(self.desc_edit, 1, 1, 1, 2)

        # Date
        layout.addWidget(QLabel(self.tr('Date')), 2, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.fromString(self.task[3], 'yyyy-MM-dd') if self.task else QDate.currentDate())
        self.date_edit.setMinimumDate(QDate.currentDate())
        self.date_edit.setMaximumDate(QDate.currentDate().addYears(9))
        layout.addWidget(self.date_edit, 2, 1)

        # Time
        layout.addWidget(QLabel(self.tr('Time')), 3, 0)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat('HH:mm')
        if self.task and self.task[4]:
            self.time_edit.setTime(QTime.fromString(self.task[4], 'HH:mm'))
        layout.addWidget(self.time_edit, 3, 1)

        # Priority
        layout.addWidget(QLabel(self.tr('Priority')), 4, 0)
        self.priority_combo = QComboBox()
        self.priority_combo.addItems([self.tr('Low'), self.tr('Medium'), self.tr('High')])
        if self.task:
            self.priority_combo.setCurrentText(self.task[5])
        layout.addWidget(self.priority_combo, 4, 1)

        # Category
        layout.addWidget(QLabel(self.tr('Category')), 5, 0)
        self.category_combo = QComboBox()
        self.category_combo.addItems([''] + self.db.get_categories())
        self.category_combo.setEditable(True)
        if self.task:
            self.category_combo.setCurrentText(self.task[6])
        layout.addWidget(self.category_combo, 5, 1)

        # Notes
        layout.addWidget(QLabel(self.tr('Notes')), 6, 0)
        self.notes_edit = QTextEdit(self.task[12] if self.task else '')
        self.notes_edit.setPlaceholderText(self.tr('Additional notes'))
        layout.addWidget(self.notes_edit, 6, 1, 1, 2)

        # Recurring
        self.recurring_check = QCheckBox(self.tr('Recurring Task'))
        self.recurring_check.setChecked(self.task[7] if self.task else False)
        layout.addWidget(self.recurring_check, 7, 0)
        self.recurring_type = QComboBox()
        self.recurring_type.addItems([self.tr('Daily'), self.tr('Weekly'), self.tr('Monthly'), self.tr('Yearly')])
        self.recurring_type.setEnabled(self.recurring_check.isChecked())
        if self.task:
            self.recurring_type.setCurrentText(self.task[8])
        layout.addWidget(self.recurring_type, 7, 1)
        self.recurring_check.stateChanged.connect(lambda: self.recurring_type.setEnabled(self.recurring_check.isChecked()))

        # Status (for editing)
        if self.task:
            self.complete_check = QCheckBox(self.tr('Completed'))
            self.complete_check.setChecked(self.task[9] == 'completed')
            layout.addWidget(self.complete_check, 8, 0)
            self.delete_all_check = QCheckBox(self.tr('Delete for all future dates (if recurring)'))
            self.delete_all_check.setEnabled(self.task[7])
            layout.addWidget(self.delete_all_check, 8, 1)

        # Buttons
        self.save_btn = QPushButton(self.tr('Save'))
        self.save_btn.clicked.connect(self.save_task)
        layout.addWidget(self.save_btn, 9, 0)

        if self.task:
            self.delete_btn = QPushButton(self.tr('Delete'))
            self.delete_btn.clicked.connect(self.delete_task)
            layout.addWidget(self.delete_btn, 9, 1)

        self.cancel_btn = QPushButton(self.tr('Cancel'))
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self.cancel_btn, 9, 2)

    def save_task(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, self.tr('Error'), self.tr('Title is required!'))
            return
        description = self.desc_edit.toPlainText()
        date = self.date_edit.date().toString('yyyy-MM-dd')
        time = self.time_edit.time().toString('HH:mm') if self.time_edit.time().isValid() else ''
        priority = self.priority_combo.currentText()
        category = self.category_combo.currentText()
        notes = self.notes_edit.toPlainText()
        is_recurring = self.recurring_check.isChecked()
        recurring_type = self.recurring_type.currentText() if is_recurring else ''
        attachment_path = ''

        if self.task:
            self.db.update_task(self.task[0], title, description, time, priority, category, notes, attachment_path)
            if self.complete_check.isChecked():
                self.db.update_task_status(self.task[0], 'completed')
                messages = {
                    'fa': ['آفرین! تو عالی هستی!', 'یک قدم دیگه به هدفت نزدیک شدی!', 'فوق‌العاده بود، ادامه بده!'],
                    'en': ['Great job! You’re awesome!', 'One step closer to your goal!', 'Keep it up, you’re amazing!'],
                    'zh': ['干得好！你很棒！', '离你的目标又近了一步！', '继续努力，你很出色！']
                }
                QMessageBox.information(self, self.tr('Success'), random.choice(messages[self.parent().language]))
            if self.delete_all_check.isChecked():
                self.db.delete_task(self.task[0], True)
        else:
            self.db.add_task(title, description, date, time, priority, category, is_recurring, recurring_type, notes, attachment_path)
        self.parent().update_task_list()
        self.accept()

    def delete_task(self):
        if self.task:
            self.db.delete_task(self.task[0], self.delete_all_check.isChecked())
            self.parent().update_task_list()
            self.accept()

class TaskItemWidget(QWidget):
    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.task[9] == 'completed')
        self.checkbox.stateChanged.connect(self.toggle_task_status)
        layout.addWidget(self.checkbox)

        task_info = f"{self.task[1]} ({self.task[4] or '-'}) - {self.task[5]}"
        self.label = QLabel(task_info)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.label)

        self.edit_btn = QToolButton()
        self.edit_btn.setIcon(QIcon('edit.svg'))
        self.edit_btn.clicked.connect(self.edit_task)
        layout.addWidget(self.edit_btn)

        self.setLayout(layout)

    def toggle_task_status(self):
        status = 'completed' if self.checkbox.isChecked() else 'pending'
        self.parent.db.update_task_status(self.task[0], status)
        if status == 'completed':
            messages = {
                'fa': ['آفرین! تو عالی هستی!', 'یک قدم دیگه به هدفت نزدیک شدی!', 'فوق‌العاده بود، ادامه بده!'],
                'en': ['Great job! You’re awesome!', 'One step closer to your goal!', 'Keep it up, you’re amazing!'],
                'zh': ['干得好！你很棒！', '离你的目标又近了一步！', '继续努力，你很出色！']
            }
            QMessageBox.information(self, self.tr('Success'), random.choice(messages[self.parent.language]))
        self.parent.update_task_list()

    def edit_task(self):
        dialog = TaskDialog(self.parent, self.task)
        dialog.exec()

class TaskManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.translator = QTranslator()
        self.language = self.db.get_setting('language', 'fa')
        self.theme = self.db.get_setting('theme', 'system')
        self.set_language()
        self.init_ui()
        self.setup_timers()
        self.setup_system_tray()
        self.load_default_categories()

    def set_language(self):
        if self.language == 'fa':
            self.translator.load('translations/fa.qm')
            QLocale.setDefault(QLocale(QLocale.Language.Persian))
        elif self.language == 'en':
            self.translator.load('translations/en.qm')
            QLocale.setDefault(QLocale(QLocale.Language.English))
        elif self.language == 'zh':
            self.translator.load('translations/zh.qm')
            QLocale.setDefault(QLocale(QLocale.Language.Chinese))
        QApplication.instance().installTranslator(self.translator)

    def set_theme(self):
        if self.theme == 'dark':
            self.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))
        elif self.theme == 'light':
            light_style = '''
                QWidget {
                    background-color: #F5F5F5;
                    color: #000000;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #45A049;
                }
                QLineEdit, QTextEdit, QComboBox, QDateEdit, QTimeEdit {
                    background-color: #FFFFFF;
                    border: 1px solid #CCCCCC;
                    border-radius: 5px;
                    padding: 3px;
                }
                QListWidget {
                    background-color: #FFFFFF;
                    border: 1px solid #CCCCCC;
                }
                QProgressBar {
                    border: 1px solid #CCCCCC;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                }
            '''
            self.setStyleSheet(light_style)
        else:
            if win32api.GetSysColor(win32con.COLOR_WINDOW) < 128:
                self.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))
            else:
                light_style = '''
                    QWidget {
                        background-color: #F5F5F5;
                        color: #000000;
                    }
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border-radius: 5px;
                        padding: 5px;
                    }
                    QPushButton:hover {
                        background-color: #45A049;
                    }
                    QLineEdit, QTextEdit, QComboBox, QDateEdit, QTimeEdit {
                        background-color: #FFFFFF;
                        border: 1px solid #CCCCCC;
                        border-radius: 5px;
                        padding: 3px;
                    }
                    QListWidget {
                        background-color: #FFFFFF;
                        border: 1px solid #CCCCCC;
                    }
                    QProgressBar {
                        border: 1px solid #CCCCCC;
                        border-radius: 5px;
                        text-align: center;
                    }
                    QProgressBar::chunk {
                        background-color: #4CAF50;
                    }
                '''
                self.setStyleSheet(light_style)

    def load_default_categories(self):
        default_categories = [
            (self.tr('Work'), '#FF6B6B'),
            (self.tr('Personal'), '#4ECDC4'),
            (self.tr('Study'), '#45B7D1'),
            (self.tr('Exercise'), '#96CEB4'),
            (self.tr('Other'), '#FFEEAD')
        ]
        for name, color in default_categories:
            self.db.add_category(name, color)

    def init_ui(self):
        self.setWindowTitle(self.tr('Task Manager'))
        self.setWindowIcon(QIcon('images.png'))
        self.setMinimumSize(800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.layout.addWidget(self.tabs)

        # Tasks Tab
        self.tasks_tab = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_tab)
        self.tasks_layout.setSpacing(10)

        self.calendar = QCalendarWidget()
        self.calendar.setLocale(QLocale(QLocale.Language.Persian) if self.language == 'fa' else QLocale())
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self.update_task_list)
        self.tasks_layout.addWidget(self.calendar)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(self.tr('Search tasks...'))
        self.search_bar.textChanged.connect(self.search_tasks)
        self.tasks_layout.addWidget(self.search_bar)

        self.task_list = QListWidget()
        self.task_list.setAlternatingRowColors(True)
        self.task_list.setMinimumHeight(200)
        scroll = QScrollArea()
        scroll.setWidget(self.task_list)
        scroll.setWidgetResizable(True)
        self.tasks_layout.addWidget(scroll)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat(self.tr('%p% Completed'))
        self.tasks_layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        self.add_task_btn = QPushButton(self.tr('Add Task'))
        self.add_task_btn.setIcon(QIcon('add_task.svg'))
        self.add_task_btn.clicked.connect(self.show_add_task_dialog)
        btn_layout.addWidget(self.add_task_btn)

        self.refresh_btn = QPushButton(self.tr('Refresh'))
        self.refresh_btn.setIcon(QIcon('refresh.svg'))
        self.refresh_btn.clicked.connect(self.update_task_list)
        btn_layout.addWidget(self.refresh_btn)

        self.tasks_layout.addLayout(btn_layout)

        # History Tab
        self.history_tab = QWidget()
        self.history_layout = QVBoxLayout(self.history_tab)
        self.history_calendar = QCalendarWidget()
        self.history_calendar.setLocale(QLocale(QLocale.Language.Persian) if self.language == 'fa' else QLocale())
        self.history_calendar.clicked.connect(self.show_history_details)
        self.history_layout.addWidget(self.history_calendar)

        self.history_details = QListWidget()
        self.history_details.setAlternatingRowColors(True)
        scroll = QScrollArea()
        scroll.setWidget(self.history_details)
        scroll.setWidgetResizable(True)
        self.history_layout.addWidget(scroll)

        # Settings Tab
        self.settings_tab = QWidget()
        self.settings_layout = QGridLayout(self.settings_tab)
        self.settings_layout.setSpacing(10)

        self.language_combo = QComboBox()
        self.language_combo.addItems([self.tr('Persian'), self.tr('English'), self.tr('Chinese')])
        self.language_combo.setCurrentText(self.tr('Persian') if self.language == 'fa' else self.tr('English') if self.language == 'en' else self.tr('Chinese'))
        self.language_combo.currentTextChanged.connect(self.change_language)
        self.settings_layout.addWidget(QLabel(self.tr('Language')), 0, 0)
        self.settings_layout.addWidget(self.language_combo, 0, 1)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.tr('System'), self.tr('Light'), self.tr('Dark')])
        self.theme_combo.setCurrentText(self.tr('System') if self.theme == 'system' else self.tr('Light') if self.theme == 'light' else self.tr('Dark'))
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        self.settings_layout.addWidget(QLabel(self.tr('Theme')), 1, 0)
        self.settings_layout.addWidget(self.theme_combo, 1, 1)

        self.notification_check = QCheckBox(self.tr('Enable Notifications'))
        self.notification_check.setChecked(self.db.get_setting('notifications', 'true') == 'true')
        self.notification_check.stateChanged.connect(self.toggle_notifications)
        self.settings_layout.addWidget(self.notification_check, 2, 0, 1, 2)

        self.backup_btn = QPushButton(self.tr('Backup Database'))
        self.backup_btn.clicked.connect(self.backup_database)
        self.settings_layout.addWidget(self.backup_btn, 3, 0)

        self.restore_btn = QPushButton(self.tr('Restore Database'))
        self.restore_btn.clicked.connect(self.restore_database)
        self.settings_layout.addWidget(self.restore_btn, 3, 1)

        self.tabs.addTab(self.tasks_tab, self.tr('Tasks'))
        self.tabs.addTab(self.history_tab, self.tr('History'))
        self.tabs.addTab(self.settings_tab, self.tr('Settings'))

        self.update_task_list()
        self.set_theme()
        self.set_layout_direction()

    def set_layout_direction(self):
        direction = Qt.LayoutDirection.RightToLeft if self.language == 'fa' else Qt.LayoutDirection.LeftToRight
        self.central_widget.setLayoutDirection(direction)
        self.task_list.setLayoutDirection(direction)
        self.history_details.setLayoutDirection(direction)
        self.tabs.setLayoutDirection(direction)
        self.search_bar.setLayoutDirection(direction)
        self.calendar.setLayoutDirection(direction)
        self.history_calendar.setLayoutDirection(direction)
        self.progress_bar.setLayoutDirection(direction)

    def setup_timers(self):
        self.reminder_timer = QTimer()
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(60000)
        self.daily_check_timer = QTimer()
        self.daily_check_timer.timeout.connect(self.check_daily_plan)
        self.daily_check_timer.start(3600000)

    def setup_system_tray(self):
        self.system_tray = QSystemTrayIcon(QIcon('images.png'), self)
        menu = QMenu()
        show_action = menu.addAction(self.tr('Show'))
        show_action.triggered.connect(self.show)
        quit_action = menu.addAction(self.tr('Quit'))
        quit_action.triggered.connect(QApplication.quit)
        self.system_tray.setContextMenu(menu)
        self.system_tray.show()

    def update_task_list(self):
        date = self.calendar.selectedDate().toString('yyyy-MM-dd')
        self.task_list.clear()
        tasks = self.db.get_tasks(date)
        for task in tasks:
            item_widget = TaskItemWidget(task, self)
            item = QListWidgetItem(self.task_list)
            item.setSizeHint(item_widget.sizeHint())
            self.task_list.addItem(item)
            self.task_list.setItemWidget(item, item_widget)
        total_tasks = len(tasks)
        completed_tasks = sum(1 for task in tasks if task[9] == 'completed')
        percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        self.progress_bar.setValue(int(percentage))
        self.db.update_history(date)

    def search_tasks(self):
        query = self.search_bar.text().strip()
        self.task_list.clear()
        tasks = self.db.search_tasks(query) if query else self.db.get_tasks(self.calendar.selectedDate().toString('yyyy-MM-dd'))
        for task in tasks:
            item_widget = TaskItemWidget(task, self)
            item = QListWidgetItem(self.task_list)
            item.setSizeHint(item_widget.sizeHint())
            self.task_list.addItem(item)
            self.task_list.setItemWidget(item, item_widget)

    def show_add_task_dialog(self):
        dialog = TaskDialog(self)
        dialog.exec()

    def show_history_details(self):
        date = self.history_calendar.selectedDate().toString('yyyy-MM-dd')
        self.history_details.clear()
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT completion_percentage, task_ids, total_tasks, completed_tasks FROM history WHERE date = ?', (date,))
        history = cursor.fetchone()
        if history:
            percentage = history[0]
            gradient = QLinearGradient(0, 0, 100, 0)
            gradient.setColorAt(0, QColor(255, int(255 * (1 - percentage / 100)), 0))
            gradient.setColorAt(1, QColor(0, int(255 * (percentage / 100)), 255))
            palette = QPalette()
            palette.setBrush(QPalette.ColorRole.Window, gradient)
            self.history_calendar.setPalette(palette)
            self.history_details.addItem(self.tr(f'Completion: {percentage:.1f}% ({history[3]} of {history[2]} tasks)'))
            task_ids = history[1].split(',')
            for task_id in task_ids:
                cursor.execute('SELECT title, status, time, priority FROM tasks WHERE id = ?', (task_id,))
                task = cursor.fetchone()
                if task:
                    item = QListWidgetItem(f"{task[0]} ({task[2] or '-'}) - {task[3]} - {task[1]}")
                    item.setBackground(QColor(0, 255, 0, 50) if task[1] == 'completed' else QColor(255, 255, 255, 50))
                    self.history_details.addItem(item)
        else:
            self.history_details.addItem(self.tr('No tasks for this date'))

    def check_reminders(self):
        if self.db.get_setting('notifications', 'true') != 'true':
            return
        now = datetime.now()
        current_date = now.strftime('%Y-%m-%d')
        current_time = now.strftime('%H:%M')
        tasks = self.db.get_tasks(current_date)
        for task in tasks:
            if task[4] and task[9] == 'pending' and task[4] <= current_time:
                notification.notify(
                    title=self.tr('Task Reminder'),
                    message=f"{self.tr('Task')}: {task[1]} {self.tr('is overdue!')}",
                    app_name='Task Manager',
                    app_icon='icon.ico',
                    timeout=10
                )
                anim = QPropertyAnimation(self, b"windowOpacity")
                anim.setDuration(500)
                anim.setStartValue(1.0)
                anim.setEndValue(0.7)
                anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
                anim.start()

    def check_daily_plan(self):
        if self.db.get_setting('notifications', 'true') != 'true':
            return
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        if not self.db.get_tasks(tomorrow):
            notification.notify(
                title=self.tr('Plan Tomorrow'),
                message=self.tr('You haven’t planned tasks for tomorrow!'),
                app_name='Task Manager',
                app_icon='icon.ico',
                timeout=10
            )

    def change_language(self, language):
        lang_map = {
            self.tr('Persian'): 'fa',
            self.tr('English'): 'en',
            self.tr('Chinese'): 'zh'
        }
        self.language = lang_map.get(language, 'fa')
        self.db.save_setting('language', self.language)
        self.set_language()
        self.init_ui()

    def change_theme(self, theme):
        theme_map = {
            self.tr('System'): 'system',
            self.tr('Light'): 'light',
            self.tr('Dark'): 'dark'
        }
        self.theme = theme_map.get(theme, 'system')
        self.db.save_setting('theme', self.theme)
        self.set_theme()

    def toggle_notifications(self):
        self.db.save_setting('notifications', 'true' if self.notification_check.isChecked() else 'false')

    def backup_database(self):
        path, _ = QInputDialog.getText(self, self.tr('Backup Database'), self.tr('Enter backup file path:'))
        if path:
            try:
                self.db.backup_database(path)
                QMessageBox.information(self, self.tr('Success'), self.tr('Database backed up successfully!'))
            except Exception as e:
                QMessageBox.critical(self, self.tr('Error'), self.tr(f'Failed to backup database: {str(e)}'))

    def restore_database(self):
        path, _ = QInputDialog.getText(self, self.tr('Restore Database'), self.tr('Enter backup file path:'))
        if path and os.path.exists(path):
            try:
                self.db.restore_database(path)
                QMessageBox.information(self, self.tr('Success'), self.tr('Database restored successfully!'))
                self.update_task_list()
            except Exception as e:
                QMessageBox.critical(self, self.tr('Error'), self.tr(f'Failed to restore database: {str(e)}'))

    def closeEvent(self, event):
        tasks = self.db.get_tasks(QDate.currentDate().toString('yyyy-MM-dd'))
        pending_tasks = [task[1] for task in tasks if task[9] == 'pending']
        if pending_tasks:
            msg = QMessageBox(self)
            msg.setWindowTitle(self.tr('Pending Tasks'))
            msg.setText(self.tr('You have pending tasks:') + '\n' + '\n'.join(pending_tasks))
            msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if msg.exec() == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        self.system_tray.hide()
        event.accept()

    def tr(self, text):
        translations = {
            'fa': {
                'Task Manager': 'مدیریت وظایف',
                'Tasks': 'وظایف',
                'History': 'تاریخچه',
                'Settings': 'تنظیمات',
                'Add Task': 'افزودن وظیفه',
                'Edit Task': 'ویرایش وظیفه',
                'Title': 'عنوان',
                'Description': 'توضیحات',
                'Date': 'تاریخ',
                'Time': 'زمان',
                'Priority': 'اولویت',
                'Low': 'کم',
                'Medium': 'متوسط',
                'High': 'بالا',
                'Category': 'دسته‌بندی',
                'Notes': 'یادداشت‌ها',
                'Recurring Task': 'وظیفه تکراری',
                'Daily': 'روزانه',
                'Weekly': 'هفتگی',
                'Monthly': 'ماهانه',
                'Yearly': 'سالانه',
                'Completed': 'تکمیل شده',
                'Delete for all future dates (if recurring)': 'حذف برای تمام تاریخ‌های آینده (در صورت تکراری بودن)',
                'Save': 'ذخیره',
                'Delete': 'حذف',
                'Cancel': 'لغو',
                'Error': 'خطا',
                'Title is required!': 'عنوان ضروری است!',
                'Success': 'موفقیت',
                'Search tasks...': 'جستجوی وظایف...',
                'Refresh': 'تازه‌سازی',
                '%p% Completed': '%p% تکمیل شده',
                'No tasks for this date': 'هیچ وظیفه‌ای برای این تاریخ وجود ندارد',
                'Completion: {percentage:.1f}% ({completed} of {total} tasks)': 'تکمیل: {percentage:.1f}% ({completed} از {total} وظیفه)',
                'Task Reminder': 'یادآور وظیفه',
                'Task': 'وظیفه',
                'is overdue!': 'از موعد گذشته است!',
                'Plan Tomorrow': 'برنامه‌ریزی برای فردا',
                'You haven’t planned tasks for tomorrow!': 'شما وظایفی برای فردا برنامه‌ریزی نکرده‌اید!',
                'Show': 'نمایش',
                'Quit': 'خروج',
                'Pending Tasks': 'وظایف در انتظار',
                'You have pending tasks:': 'شما وظایف در انتظاری دارید:',
                'Language': 'زبان',
                'Persian': 'فارسی',
                'English': 'انگلیسی',
                'Chinese': 'چینی',
                'Theme': 'تم',
                'System': 'سیستم',
                'Light': 'روشن',
                'Dark': 'تیره',
                'Enable Notifications': 'فعال کردن اعلان‌ها',
                'Backup Database': 'پشتیبان‌گیری از پایگاه داده',
                'Restore Database': 'بازگرداندن پایگاه داده',
                'Enter backup file path:': 'مسیر فایل پشتیبان را وارد کنید:',
                'Database backed up successfully!': 'پایگاه داده با موفقیت پشتیبان‌گیری شد!',
                'Failed to backup database: {error}': 'پشتیبان‌گیری از پایگاه داده ناموفق بود: {error}',
                'Enter task title': 'عنوان وظیفه را وارد کنید',
                'Enter task description': 'توضیحات وظیفه را وارد کنید',
                'Additional notes': 'یادداشت‌های اضافی',
                'Work': 'کار',
                'Personal': 'شخصی',
                'Study': 'مطالعه',
                'Exercise': 'ورزش',
                'Other': 'سایر'
            },
            'en': {
                'Task Manager': 'Task Manager',
                'Tasks': 'Tasks',
                'History': 'History',
                'Settings': 'Settings',
                'Add Task': 'Add Task',
                'Edit Task': 'Edit Task',
                'Title': 'Title',
                'Description': 'Description',
                'Date': 'Date',
                'Time': 'Time',
                'Priority': 'Priority',
                'Low': 'Low',
                'Medium': 'Medium',
                'High': 'High',
                'Category': 'Category',
                'Notes': 'Notes',
                'Recurring Task': 'Recurring Task',
                'Daily': 'Daily',
                'Weekly': 'Weekly',
                'Monthly': 'Monthly',
                'Yearly': 'Yearly',
                'Completed': 'Completed',
                'Delete for all future dates (if recurring)': 'Delete for all future dates (if recurring)',
                'Save': 'Save',
                'Delete': 'Delete',
                'Cancel': 'Cancel',
                'Error': 'Error',
                'Title is required!': 'Title is required!',
                'Success': 'Success',
                'Search tasks...': 'Search tasks...',
                'Refresh': 'Refresh',
                '%p% Completed': '%p% Completed',
                'No tasks for this date': 'No tasks for this date',
                'Completion: {percentage:.1f}% ({completed} of {total} tasks)': 'Completion: {percentage:.1f}% ({completed} of {total} tasks)',
                'Task Reminder': 'Task Reminder',
                'Task': 'Task',
                'is overdue!': 'is overdue!',
                'Plan Tomorrow': 'Plan Tomorrow',
                'You haven’t planned tasks for tomorrow!': 'You haven’t planned tasks for tomorrow!',
                'Show': 'Show',
                'Quit': 'Quit',
                'Pending Tasks': 'Pending Tasks',
                'You have pending tasks:': 'You have pending tasks:',
                'Language': 'Language',
                'Persian': 'Persian',
                'English': 'English',
                'Chinese': 'Chinese',
                'Theme': 'Theme',
                'System': 'System',
                'Light': 'Light',
                'Dark': 'Dark',
                'Enable Notifications': 'Enable Notifications',
                'Backup Database': 'Backup Database',
                'Restore Database': 'Restore Database',
                'Enter backup file path:': 'Enter backup file path:',
                'Database backed up successfully!': 'Database backed up successfully!',
                'Failed to backup database: {error}': 'Failed to backup database: {error}',
                'Enter task title': 'Enter task title',
                'Enter task description': 'Enter task description',
                'Additional notes': 'Additional notes',
                'Work': 'Work',
                'Personal': 'Personal',
                'Study': 'Study',
                'Exercise': 'Exercise',
                'Other': 'Other'
            },
            'zh': {
                'Task Manager': '任务管理器',
                'Tasks': '任务',
                'History': '历史记录',
                'Settings': '设置',
                'Add Task': '添加任务',
                'Edit Task': '编辑任务',
                'Title': '标题',
                'Description': '描述',
                'Date': '日期',
                'Time': '时间',
                'Priority': '优先级',
                'Low': '低',
                'Medium': '中',
                'High': '高',
                'Category': '类别',
                'Notes': '备注',
                'Recurring Task': '重复任务',
                'Daily': '每天',
                'Weekly': '每周',
                'Monthly': '每月',
                'Yearly': '每年',
                'Completed': '已完成',
                'Delete for all future dates (if recurring)': '删除所有未来日期（如果重复）',
                'Save': '保存',
                'Delete': '删除',
                'Cancel': '取消',
                'Error': '错误',
                'Title is required!': '标题是必填项！',
                'Success': '成功',
                'Search tasks...': '搜索任务...',
                'Refresh': '刷新',
                '%p% Completed': '%p% 已完成',
                'No tasks for this date': '此日期没有任务',
                'Completion: {percentage:.1f}% ({completed} of {total} tasks)': '完成度：{percentage:.1f}%（{completed}/{total} 任务）',
                'Task Reminder': '任务提醒',
                'Task': '任务',
                'is overdue!': '已逾期！',
                'Plan Tomorrow': '计划明天',
                'You haven’t planned tasks for tomorrow!': '你还没有为明天计划任务！',
                'Show': '显示',
                'Quit': '退出',
                'Pending Tasks': '待完成任务',
                'You have pending tasks:': '你有待完成的任务：',
                'Language': '语言',
                'Persian': '波斯语',
                'English': '英语',
                'Chinese': '中文',
                'Theme': '主题',
                'System': '系统',
                'Light': '明亮',
                'Dark': '暗色',
                'Enable Notifications': '启用通知',
                'Backup Database': '备份数据库',
                'Restore Database': '恢复数据库',
                'Enter backup file path:': '输入备份文件路径：',
                'Database backed up successfully!': '数据库备份成功！',
                'Failed to backup database: {error}': '数据库备份失败：{error}',
                'Enter task title': '输入任务标题',
                'Enter task description': '输入任务描述',
                'Additional notes': '附加备注',
                'Work': '工作',
                'Personal': '个人',
                'Study': '学习',
                'Exercise': '锻炼',
                'Other': '其他'
            }
        }
        return translations[self.language].get(text, text).format(percentage='{percentage:.1f}', completed='{completed}', total='{total}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = TaskManager()
    window.show()
    sys.exit(app.exec())