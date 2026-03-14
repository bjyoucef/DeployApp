"""
DeployApp — A modern, visual deployment tool for Windows.

Compare and deploy files between a local project directory and a remote server
via SMB (network share) or SSH/SFTP. Features include smart file scanning,
visual diff, deployment history, server restart, and database backup.

Built with Python 3.10+ and PyQt6.

Usage:
    python main.py

Configuration:
    Copy ``deploy_config.example.json`` to ``deploy_config.json`` and fill in
    your environment-specific values (paths, credentials, server settings).

License:
    MIT — see LICENSE file for details.
"""

import os
import sys
import shutil
import json
import hashlib
import difflib
import base64
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import time
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
from pathlib import Path
import fnmatch
import posixpath

try:
    import paramiko
    import stat as stat_lib

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

from translations import tr, get_language, set_language

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QProgressBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QFrame,
    QSplitter,
    QDialog,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QGridLayout,
    QStyledItemDelegate,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QObject,
    QRect,
    QPropertyAnimation,
    pyqtProperty,
    QEasingCurve,
    QRectF,
)
from PyQt6.QtGui import QFont, QColor, QIcon, QPainter, QPainterPath, QPen, QBrush

# ============================================================================
# VERSION & CONSTANTES GLOBALES
# ============================================================================

APP_VERSION = "1.0"
APP_NAME = "DeployApp"

APP_DIR = Path(__file__).parent
CONFIG_FILE = APP_DIR / "deploy_config.json"
HISTORY_DB = APP_DIR / "deploy_history.db"


def _load_deploy_config() -> dict:
    """Loads deploy_config.json once at startup."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


_DEPLOY_CONFIG = _load_deploy_config()

# --- Palette de couleurs (Thème "Slate & Indigo") ---
COLORS = {
    "primary": "#3B82F6",  # Bleu Indigo
    "primary_hover": "#2563EB",
    "primary_dark": "#1D4ED8",
    "success": "#10B981",  # Vert Emeraude
    "success_hover": "#059669",
    "warning": "#F59E0B",  # Oranger Ambre
    "error": "#EF4444",  # Rouge
    "error_hover": "#DC2626",
    "bg_dark": "#0F172A",  # Slate 900 (Fond global)
    "bg_card": "#1E293B",  # Slate 800 (Cartes/Inputs)
    "bg_card_hover": "#334155",  # Slate 700 (Hover/Lignes)
    "text": "#F8FAFC",  # Slate 50 (Texte princ.)
    "text_muted": "#94A3B8",  # Slate 400 (Texte second.)
    "border": "#334155",  # Slate 700 (Bordures)
    "accent_blue": "#3B82F6",
    "accent_cyan": "#06B6D4",
    "new_file": "#10B981",
    "modified_file": "#F59E0B",
    "deleted_file": "#EF4444",
}

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLORS["bg_dark"]};
    color: {COLORS["text"]};
    font-family: 'Inter', 'Segoe UI', 'Roboto', sans-serif;
    font-size: 13px;
}}
QLabel {{
    color: {COLORS["text"]};
    background: transparent;
}}
QLineEdit {{
    background-color: {COLORS["bg_dark"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 12px;
    color: {COLORS["text"]};
    font-size: 13px;
}}
QLineEdit:focus {{
    border-color: {COLORS["primary"]};
}}
QComboBox {{
    background-color: {COLORS["bg_dark"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 12px;
    color: {COLORS["text"]};
}}
QComboBox::drop-down {{
    border: none;
}}
QPushButton {{
    background-color: {COLORS["primary"]};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {COLORS["primary_hover"]};
}}
QPushButton:disabled {{
    background-color: {COLORS["bg_card_hover"]};
    color: {COLORS["text_muted"]};
}}
QPushButton#btnDeploy {{
    background-color: {COLORS["success"]};
}}
QPushButton#btnDeploy:hover {{
    background-color: {COLORS["success_hover"]};
}}
QPushButton#btnDeploy:disabled {{
    background-color: {COLORS["bg_card_hover"]};
    color: {COLORS["text_muted"]};
}}
QPushButton#btnMinor, QPushButton#btnMajor {{
    background-color: transparent;
    border: 1px solid {COLORS["border"]};
    color: {COLORS["text_muted"]};
    font-size: 12px;
    padding: 6px 12px;
    border-radius: 6px;
    font-weight: normal;
}}
QPushButton#btnMinor:hover, QPushButton#btnMajor:hover {{
    border-color: {COLORS["text"]};
    color: {COLORS["text"]};
}}
QPushButton#btnRefresh, QPushButton#btnExport {{
    background-color: transparent;
    border: 1px solid {COLORS["border"]};
    color: {COLORS["text_muted"]};
    font-size: 12px;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: normal;
}}
QPushButton#btnRefresh:hover, QPushButton#btnExport:hover {{
    border-color: {COLORS["text"]};
    color: {COLORS["text"]};
}}
QProgressBar {{
    background-color: {COLORS["bg_dark"]};
    border: none;
    border-radius: 2px;
    height: 4px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {COLORS["primary"]};
    border-radius: 2px;
}}
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {COLORS["border"]};
    background-color: transparent;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {COLORS["text_muted"]};
    padding: 10px 20px;
    border: none;
    font-size: 13px;
    font-weight: normal;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    color: {COLORS["text"]};
    border-bottom: 2px solid {COLORS["primary"]};
}}
QTabBar::tab:hover:!selected {{
    color: {COLORS["text"]};
}}
QTreeWidget {{
    background-color: transparent;
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    color: {COLORS["text"]};
    font-size: 13px;
    alternate-background-color: {COLORS["bg_dark"]};
}}
QTreeWidget::item {{
    padding: 6px 4px;
    border-bottom: 1px solid {COLORS["bg_card"]};
}}
QTreeWidget::item:selected {{
    background-color: {COLORS["bg_card_hover"]};
    color: {COLORS["text"]};
}}
QHeaderView::section {{
    background-color: transparent;
    color: {COLORS["text_muted"]};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
}}
QTextEdit {{
    background-color: {COLORS["bg_dark"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    font-family: 'Consolas', monospace;
    font-size: 13px;
    padding: 10px;
}}
QFrame#statsFrame {{
    background-color: transparent;
}}
QFrame#headerFrame {{
    background-color: {COLORS["bg_dark"]};
    border-bottom: 1px solid {COLORS["border"]};
}}
QFrame#statusBar {{
    background-color: {COLORS["bg_card"]};
    border-top: 1px solid {COLORS["border"]};
}}
QFrame#pathsFrame {{
    background-color: {COLORS["bg_card"]};
    border-radius: 8px;
    border: 1px solid {COLORS["border"]};
}}
"""

# ============================================================================
# BOUTON TOGGLE ANIMÉ (SWITCH)
# ============================================================================


class AnimatedToggle(QCheckBox):
    """Custom animated toggle switch widget replacing the default checkbox."""

    _transparent_pen = QPen(Qt.GlobalColor.transparent)
    _light_grey_pen = QPen(Qt.GlobalColor.lightGray)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0
        self.animation = QPropertyAnimation(self, b"position")
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setDuration(200)
        self.stateChanged.connect(self.setup_animation)

    @pyqtProperty(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def setup_animation(self, value):
        self.animation.stop()
        if value:
            self.animation.setEndValue(1)
        else:
            self.animation.setEndValue(0)
        self.animation.start()

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._transparent_pen)

        # Draw background track
        track_rect = QRect(0, 0, self.width(), self.height())
        if self.isChecked():
            p.setBrush(QColor(COLORS["primary"]))
        else:
            p.setBrush(QColor(COLORS["bg_card_hover"]))
        p.drawRoundedRect(track_rect, 11, 11)

        # Draw circle handle
        p.setBrush(QColor("#FFFFFF"))
        x_pos = 2 + self._position * (self.width() - self.height())
        handle_rect = QRectF(x_pos, 2, self.height() - 4, self.height() - 4)
        p.drawEllipse(handle_rect)
        p.end()


# ============================================================================
# COMPOSANT BADGE POUR LES TABLEAUX
# ============================================================================


class BadgeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        # Centrer verticalement, aligner à droite avec un peu de marge
        margin = 10

        # Dimensions du badge
        font_metrics = painter.fontMetrics()
        text_width = font_metrics.horizontalAdvance(text)
        badge_width = text_width + 16
        badge_height = font_metrics.height() + 8

        # Position (aligné à droite)
        x = rect.right() - badge_width - margin
        y = rect.top() + (rect.height() - badge_height) // 2
        badge_rect = QRectF(x, y, badge_width, badge_height)

        # Dessiner le fond du badge (Vert translucide)
        success_col = QColor(COLORS["success"])
        bg_color = QColor(success_col)
        bg_color.setAlphaF(0.15)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(badge_rect, badge_height / 2, badge_height / 2)

        # Dessiner le texte (Vert)
        painter.setPen(success_col)
        text_rect = QRectF(x, y, badge_width, badge_height)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()


# ============================================================================
# CLASSES MÉTIER
# ============================================================================


class FileStatus(Enum):
    """Deployment status of a file after scanning."""

    NEW = "New"
    MODIFIED = "Modified"
    UPTODATE = "Up to date"
    DELETED = "Deleted"


@dataclass
class FileInfo:
    """Metadata for a single file discovered during scanning.

    Holds local and remote paths, sizes, modification times, and the computed
    deployment status (new, modified, deleted, or up-to-date).
    """

    relative_path: str
    local_path: str
    remote_path: str
    status: FileStatus
    local_size: int
    remote_size: Optional[int]
    local_mtime: Optional[datetime]
    remote_mtime: Optional[datetime]
    selected: bool = True

    @property
    def status_value(self) -> str:
        # Use tr for the specific status
        mapping = {
            FileStatus.NEW: "fs_new",
            FileStatus.MODIFIED: "fs_modified",
            FileStatus.UPTODATE: "fs_uptodate",
            FileStatus.DELETED: "fs_deleted"
        }
        return tr(mapping.get(self.status, "fs_modified"))

    @property
    def size_display(self) -> str:
        size = (
            self.remote_size if self.status == FileStatus.DELETED else self.local_size
        )
        if size is None or size == 0:
            return "—"
        for unit in ["o", "Ko", "Mo", "Go"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} To"


class FileComparator:
    """Compare local and remote files by size, timestamp, or MD5 hash."""

    TIME_TOLERANCE = 2.0

    @staticmethod
    def get_file_hash(filepath: str, block_size: int = 65536) -> Optional[str]:
        try:
            hasher = hashlib.md5()
            with open(filepath, "rb") as f:
                for block in iter(lambda: f.read(block_size), b""):
                    hasher.update(block)
            return hasher.hexdigest()
        except (IOError, OSError):
            return None

    @classmethod
    def compare_files(
        cls, local_path: str, remote_path: str, use_hash: bool = False
    ) -> FileStatus:
        if not os.path.exists(remote_path):
            return FileStatus.NEW

        try:
            local_size = os.path.getsize(local_path)
            remote_size = os.path.getsize(remote_path)
            local_mtime = os.path.getmtime(local_path)
            remote_mtime = os.path.getmtime(remote_path)

            if local_size != remote_size:
                return FileStatus.MODIFIED

            if abs(local_mtime - remote_mtime) > cls.TIME_TOLERANCE:
                if use_hash:
                    if cls.get_file_hash(local_path) != cls.get_file_hash(remote_path):
                        return FileStatus.MODIFIED
                else:
                    return FileStatus.MODIFIED

            return FileStatus.UPTODATE
        except (IOError, OSError):
            return FileStatus.MODIFIED


class ConfigManager:
    """Load and save application configuration from ``deploy_config.json``."""

    @staticmethod
    def _build_default_config() -> dict:
        """Builds the DEFAULT_CONFIG from deploy_config.json."""
        return {
            "local_dir": _DEPLOY_CONFIG.get("local_dir", ""),
            "remote_dir": _DEPLOY_CONFIG.get("remote_dir", ""),
            "use_hash_comparison": _DEPLOY_CONFIG.get("use_hash_comparison", False),
            "auto_backup": _DEPLOY_CONFIG.get("auto_backup", True),
            "ignore_patterns": list(_DEPLOY_CONFIG.get("ignore_patterns", [])),
            "deploy_method": _DEPLOY_CONFIG.get("deploy_method", "smb"),
            "ssh_host": _DEPLOY_CONFIG.get("ssh_host", ""),
            "ssh_port": _DEPLOY_CONFIG.get("ssh_port", 22),
            "ssh_user": _DEPLOY_CONFIG.get("ssh_user", ""),
            "ssh_key_path": _DEPLOY_CONFIG.get("ssh_key_path", ""),
            "ssh_remote_dir": _DEPLOY_CONFIG.get("ssh_remote_dir", ""),
            "ssh_password": _DEPLOY_CONFIG.get("ssh_password", ""),
            "all_ignore_patterns": list(_DEPLOY_CONFIG.get("all_ignore_patterns", [])),
        }

    @classmethod
    def load(cls) -> dict:
        defaults = cls._build_default_config()
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**defaults, **json.load(f)}
        except Exception:
            pass
        return defaults

    @classmethod
    def save(cls, config: dict):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(tr("err_save_config", err=e))


# ============================================================================
# GESTIONNAIRE DE VERSION (FICHIER VERSION)
# ============================================================================

VERSION_FILENAME = "VERSION"


class VersionManager:
    """Manages a VERSION file in SemVer format (MAJOR.MINOR.PATCH)."""

    @staticmethod
    def read_version(directory: str) -> tuple:
        try:
            version_file = os.path.join(directory, VERSION_FILENAME)
            if os.path.isfile(version_file):
                with open(version_file, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                parts = text.split(".")
                if len(parts) == 3:
                    return int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IOError, OSError):
            pass
        return 1, 0, 0

    @staticmethod
    def write_version(directory: str, version: tuple):
        try:
            os.makedirs(directory, exist_ok=True)
            version_file = os.path.join(directory, VERSION_FILENAME)
            with open(version_file, "w", encoding="utf-8") as f:
                f.write(f"{version[0]}.{version[1]}.{version[2]}")
        except (IOError, OSError) as e:
            print(tr("err_write_version", err=e))


# ============================================================================
# GESTIONNAIRE D'HISTORIQUE SQLITE
# ============================================================================
class HistoryManager:
    """SQLite-backed deployment history tracker.

    Records every deployment with version, timestamp, file list,
    success/error counts, duration, and user-entered changelog.
    """

    def __init__(self, db_path: Path = HISTORY_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deployments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT,
                    timestamp TEXT,
                    local_dir TEXT,
                    remote_dir TEXT,
                    total_files INTEGER,
                    success_count INTEGER,
                    error_count INTEGER,
                    duration_seconds REAL,
                    status TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deployment_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deployment_id INTEGER,
                    file_path TEXT,
                    file_status TEXT,
                    file_size INTEGER,
                    result TEXT,
                    error_message TEXT,
                    FOREIGN KEY (deployment_id) REFERENCES deployments(id)
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS changelog_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT,
                    timestamp TEXT,
                    added_count INTEGER,
                    modified_count INTEGER,
                    deleted_count INTEGER,
                    success_count INTEGER,
                    error_count INTEGER,
                    duration_seconds REAL
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS changelog_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    changelog_id INTEGER,
                    file_path TEXT,
                    change_type TEXT,
                    FOREIGN KEY (changelog_id) REFERENCES changelog_entries(id)
                )
            """
            )
            conn.commit()

    def create_deployment(self, version: str, local_dir: str, remote_dir: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO deployments
                   (version, timestamp, local_dir, remote_dir, total_files,
                    success_count, error_count, duration_seconds, status)
                   VALUES (?, ?, ?, ?, 0, 0, 0, 0, 'in_progress')""",
                (version, datetime.now().isoformat(), local_dir, remote_dir),
            )
            conn.commit()
            return cursor.lastrowid

    def add_file_record(
        self,
        deployment_id: int,
        file_path: str,
        file_status: str,
        file_size: int,
        result: str,
        error_message: str = "",
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO deployment_files
                   (deployment_id, file_path, file_status, file_size, result, error_message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    deployment_id,
                    file_path,
                    file_status,
                    file_size,
                    result,
                    error_message,
                ),
            )
            conn.commit()

    def finalize_deployment(
        self, deployment_id: int, total: int, success: int, errors: int, duration: float
    ):
        status = "success" if errors == 0 else ("partial" if success > 0 else "failed")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE deployments
                   SET total_files=?, success_count=?, error_count=?,
                       duration_seconds=?, status=?
                   WHERE id=?""",
                (total, success, errors, duration, status, deployment_id),
            )
            conn.commit()

    def get_deployments(self, limit: int = 50) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM deployments ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_deployment_files(self, deployment_id: int) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM deployment_files WHERE deployment_id=? ORDER BY id",
                (deployment_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- CHANGELOG ---
    def save_changelog(
        self,
        version,
        timestamp,
        added_files,
        modified_files,
        deleted_files,
        success_count,
        error_count,
        duration,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO changelog_entries
                   (version, timestamp, added_count, modified_count, deleted_count,
                    success_count, error_count, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version,
                    timestamp,
                    len(added_files),
                    len(modified_files),
                    len(deleted_files),
                    success_count,
                    error_count,
                    duration,
                ),
            )
            changelog_id = cursor.lastrowid
            for fp in added_files:
                conn.execute(
                    "INSERT INTO changelog_files (changelog_id, file_path, change_type) VALUES (?, ?, ?)",
                    (changelog_id, fp, "added"),
                )
            for fp in modified_files:
                conn.execute(
                    "INSERT INTO changelog_files (changelog_id, file_path, change_type) VALUES (?, ?, ?)",
                    (changelog_id, fp, "modified"),
                )
            for fp in deleted_files:
                conn.execute(
                    "INSERT INTO changelog_files (changelog_id, file_path, change_type) VALUES (?, ?, ?)",
                    (changelog_id, fp, "deleted"),
                )
            conn.commit()
            return changelog_id

    def get_changelogs(self, limit: int = 100) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM changelog_entries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_changelog_files(self, changelog_id: int) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM changelog_files WHERE changelog_id=? ORDER BY change_type, file_path",
                (changelog_id,),
            ).fetchall()
            return [dict(r) for r in rows]


# ============================================================================
# SIGNAUX THREAD-SAFE POUR PYQT
# ============================================================================
class WorkerSignals(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(float)
    status = pyqtSignal(str)
    ui_state = pyqtSignal(bool)
    refresh_tree = pyqtSignal()
    refresh_history = pyqtSignal()
    update_stats = pyqtSignal(int, int, int, int, int)
    finished = pyqtSignal()


# ============================================================================
# DIALOGUE D'EXCLUSION
# ============================================================================
class IgnorePatternsDialog(QDialog):
    """Dialog to manage file/directory exclusion patterns.

    Allows users to enable or disable ignore rules (e.g. ``.git``,
    ``__pycache__``, ``node_modules``) and add custom patterns.
    """

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        self.setWindowTitle(tr("dlg_excl_title"))
        self.setMinimumSize(400, 550)
        self.setStyleSheet(STYLESHEET)

        # Merge all_ignore_patterns and ignore_patterns to ensure everything is visible
        saved_all = list(self.config.get("all_ignore_patterns", []))
        saved_active = list(self.config.get("ignore_patterns", []))
        # Make sure any active pattern also appears in the master list
        for pat in saved_active:
            if pat not in saved_all:
                saved_all.append(pat)
        self.all_patterns = saved_all
        self.active_patterns = set(saved_active)

        layout = QVBoxLayout(self)

        lbl_info = QLabel(tr("dlg_excl_info"))
        lbl_info.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        layout.addWidget(lbl_info)

        lbl_help = QLabel(tr("dlg_excl_help"))
        lbl_help.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(lbl_help)

        # Boutons tout cocher / décocher
        btn_row = QHBoxLayout()
        btn_all = QPushButton(tr("btn_check_all"))
        btn_all.clicked.connect(self.check_all)
        btn_none = QPushButton(tr("btn_uncheck_all"))
        btn_none.clicked.connect(self.uncheck_all)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        layout.addLayout(btn_row)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("search_excl_ph"))
        self.search_input.textChanged.connect(self.populate_list)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background-color: {COLORS['bg_card']}; color: white; border-radius: 8px; }}"
            f"QListWidget::item {{ padding: 5px; }}"
            f"QListWidget::item:selected {{ background-color: {COLORS['primary']}; }}"
        )
        layout.addWidget(self.list_widget)

        self.populate_list()

        # Ajouter nouveau pattern (texte)
        add_row = QHBoxLayout()
        self.new_pattern_input = QLineEdit()
        self.new_pattern_input.setPlaceholderText(tr("add_excl_ph"))
        btn_add = QPushButton(tr("btn_add"))
        btn_add.clicked.connect(self.add_pattern)
        add_row.addWidget(self.new_pattern_input)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        # Ajouter un dossier via explorateur
        btn_add_folder = QPushButton(tr("btn_add_folder"))
        btn_add_folder.clicked.connect(self.add_folder)
        layout.addWidget(btn_add_folder)

        # Bouton supprimer
        btn_del = QPushButton(tr("btn_remove_sel"))
        btn_del.setStyleSheet(f"background-color: {COLORS['error']};")
        btn_del.clicked.connect(self.remove_pattern)
        layout.addWidget(btn_del)

        # Bouton Valider
        btn_ok = QPushButton(tr("btn_save"))
        btn_ok.setObjectName("btnDeploy")
        btn_ok.clicked.connect(self.save_and_close)
        layout.addWidget(btn_ok)

    def populate_list(self):
        search = self.search_input.text().lower().strip() if hasattr(self, 'search_input') else ""
        # Save current check states before clearing
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            pat = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if item.checkState() == Qt.CheckState.Checked:
                self.active_patterns.add(pat)
            else:
                self.active_patterns.discard(pat)

        self.list_widget.clear()
        for pat in sorted(self.all_patterns):
            if search and search not in pat.lower():
                continue
            # Determine if pattern looks like a file or folder
            is_file_pattern = '*' in pat or (pat.startswith('.') and not pat.startswith('.') == pat) or ('.' in pat and not pat.startswith('.'))
            icon = "📄" if is_file_pattern else "📁"
            item = QListWidgetItem(f"{icon}  {pat}")
            item.setData(Qt.ItemDataRole.UserRole, pat)  # store raw pattern
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if pat in self.active_patterns:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

    def check_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def uncheck_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def add_pattern(self):
        pat = self.new_pattern_input.text().strip()
        if pat and pat not in self.all_patterns:
            self.all_patterns.append(pat)
            self.active_patterns.add(pat)
            self.populate_list()
            self.new_pattern_input.clear()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("dlg_excl_folder_sel"))
        if folder:
            folder_name = os.path.basename(folder)
            if folder_name and folder_name not in self.all_patterns:
                self.all_patterns.append(folder_name)
                self.active_patterns.add(folder_name)
                self.populate_list()

    def remove_pattern(self):
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            pat = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if pat in self.all_patterns:
                self.all_patterns.remove(pat)
            if pat in self.active_patterns:
                self.active_patterns.remove(pat)
        self.populate_list()

    def save_and_close(self):
        # Sync check states from visible items
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            pat = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if item.checkState() == Qt.CheckState.Checked:
                self.active_patterns.add(pat)
            else:
                self.active_patterns.discard(pat)

        self.config["ignore_patterns"] = list(self.active_patterns)
        self.config["all_ignore_patterns"] = self.all_patterns
        ConfigManager.save(self.config)
        self.accept()


# ============================================================================
# SSH DEPLOYER
# ============================================================================


class SSHDeployer:
    """Handles SSH/SFTP operations if paramiko mode is active."""

    def __init__(self, host, port, user, password=None, key_path=None):
        self.host = host
        self.port = int(port) if port else 22
        self.user = user
        self.password = password
        self.key_path = key_path
        self.ssh = None
        self.sftp = None

    def connect(self):
        if not HAS_PARAMIKO:
            raise ImportError(tr("err_paramiko_missing"))

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.user,
        }

        if self.key_path and os.path.isfile(self.key_path):
            connect_kwargs["key_filename"] = self.key_path
            connect_kwargs["allow_agent"] = False
            connect_kwargs["look_for_keys"] = False
        elif self.password:
            connect_kwargs["password"] = self.password

        self.ssh.connect(**connect_kwargs)
        self.sftp = self.ssh.open_sftp()

    def disconnect(self):
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()

    def execute_command(self, command: str) -> tuple[int, str, str]:
        """Executes a command on the remote server and returns the exit code, stdout, and stderr."""
        if not self.ssh:
            raise Exception(tr("err_not_connected"))
        stdin, stdout, stderr = self.ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        raw_out = stdout.read()
        raw_err = stderr.read()
        # Windows peut retourner du UTF-16 ou cp1252, on gère les erreurs d'encodage
        try:
            out = raw_out.decode('utf-8').strip()
        except UnicodeDecodeError:
            try:
                out = raw_out.decode('utf-16').strip()
            except (UnicodeDecodeError, UnicodeError):
                out = raw_out.decode('cp1252', errors='replace').strip()
        try:
            err = raw_err.decode('utf-8').strip()
        except UnicodeDecodeError:
            try:
                err = raw_err.decode('utf-16').strip()
            except (UnicodeDecodeError, UnicodeError):
                err = raw_err.decode('cp1252', errors='replace').strip()
        return exit_status, out, err

    def remote_exists(self, remote_path):
        try:
            self.sftp.stat(remote_path)
            return True
        except IOError:
            return False

    def list_remote_files(self, remote_dir, ignore_patterns):
        """Recursively lists files on the server to detect deletions."""
        files = []
        if not self.sftp:
            return files

        def is_ignored(name):
            for pattern in ignore_patterns:
                if fnmatch.fnmatch(name, pattern):
                    return True
            return False

        def _walk(path):
            try:
                for entry in self.sftp.listdir_attr(path):
                    if is_ignored(entry.filename):
                        continue

                    full_path = path + "/" + entry.filename
                    if stat_lib.S_ISDIR(entry.st_mode):
                        _walk(full_path)
                    else:
                        files.append((full_path, entry.st_size, entry.st_mtime))
            except IOError:
                pass

        # Vérif existence base
        if self.remote_exists(remote_dir):
            _walk(remote_dir)

        return files

    def compare_file(self, local_path, remote_path, use_hash=False):
        """Retourne le FileStatus via SFTP."""
        if not self.sftp:
            return FileStatus.MODIFIED

        try:
            remote_stat = self.sftp.stat(remote_path)
        except IOError:
            return FileStatus.NEW

        local_size = os.path.getsize(local_path)
        remote_size = remote_stat.st_size
        local_mtime = os.path.getmtime(local_path)
        remote_mtime = remote_stat.st_mtime

        if local_size != remote_size:
            return FileStatus.MODIFIED

        if abs(local_mtime - remote_mtime) > FileComparator.TIME_TOLERANCE:
            # Hash calculation sur SSH n'est pas simple sans exec_command.
            # Reste sur modified ou exécute un md5sum (Linux).
            if use_hash:
                stdin, stdout, stderr = self.ssh.exec_command(f'md5sum "{remote_path}"')
                out = stdout.read().decode().strip()
                if out:
                    remote_hash = out.split()[0]
                    local_hash = FileComparator.get_file_hash(local_path)
                    if local_hash != remote_hash:
                        return FileStatus.MODIFIED
                else:
                    return FileStatus.MODIFIED
            else:
                return FileStatus.MODIFIED

        return FileStatus.UPTODATE

    def ensure_remote_dir(self, remote_path):
        """Creates the directory tree on the server side."""
        remote_dir = posixpath.dirname(remote_path)
        dirs = []
        while len(remote_dir) > 1:
            if self.remote_exists(remote_dir):
                break
            dirs.append(remote_dir)
            remote_dir = posixpath.dirname(remote_dir)

        while dirs:
            dir_to_create = dirs.pop()
            try:
                self.sftp.mkdir(dir_to_create)
            except IOError:
                pass

    def upload_file(self, local_path, remote_path):
        if not self.sftp:
            raise IOError(tr("err_sftp_not_connected"))

        self.ensure_remote_dir(remote_path)
        self.sftp.put(local_path, remote_path + ".tmp")

        # rename
        if self.remote_exists(remote_path):
            self.sftp.remove(remote_path)
        self.sftp.rename(remote_path + ".tmp", remote_path)

        # Check size
        local_size = os.path.getsize(local_path)
        rm_stat = self.sftp.stat(remote_path)
        if rm_stat.st_size != local_size:
            self.sftp.remove(remote_path)
            raise IOError(
                tr("err_size_mismatch_ssh", remote=rm_stat.st_size, local=local_size)
            )

    def delete_file(self, remote_path):
        if not self.sftp:
            return
        if self.remote_exists(remote_path):
            self.sftp.remove(remote_path)
            # Cleanup parent dirs
            parent = posixpath.dirname(remote_path)
            try:
                for _ in range(5):  # depth limit
                    if not self.sftp.listdir(parent):
                        self.sftp.rmdir(parent)
                        parent = posixpath.dirname(parent)
                    else:
                        break
            except IOError:
                pass

    def create_backup(self, src_remote_dir, dest_path):
        """Creates a backup via cp command on the remote shell."""
        cmd = f'cp -a "{src_remote_dir}" "{dest_path}"'
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode("utf8", errors="ignore")
            raise RuntimeError(f"Backup SSH failed ({exit_status}): {err}")


# ============================================================================
# DIALOGUE DE COMPARAISON (DIFF VISUEL)
# ============================================================================


class DiffDialog(QDialog):
    """Side-by-side visual comparison window between a local and remote file."""

    def __init__(self, parent=None, local_text="", remote_text="", file_name=""):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_diff_title", name=file_name))
        self.setMinimumSize(1100, 650)
        self.resize(1300, 750)
        self.setStyleSheet(STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Header ---
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(
            f"background-color: {COLORS['bg_card']}; border-bottom: 1px solid {COLORS['border']};"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel(tr("dlg_diff_header", name=file_name))
        title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_lbl.setStyleSheet("border: none;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        # Légende
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(15)
        for label_text, color in [
            (tr("dlg_diff_added"), COLORS["new_file"]),
            (tr("dlg_diff_deleted"), COLORS["deleted_file"]),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 16px; border: none;")
            legend_layout.addWidget(dot)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 12px; border: none;"
            )
            legend_layout.addWidget(lbl)
        h_layout.addLayout(legend_layout)

        layout.addWidget(header)

        # --- Labels colonnes ---
        col_labels = QWidget()
        col_labels.setFixedHeight(32)
        col_labels.setStyleSheet(
            f"background-color: {COLORS['bg_dark']}; border-bottom: 1px solid {COLORS['border']};"
        )
        cl_layout = QHBoxLayout(col_labels)
        cl_layout.setContentsMargins(0, 0, 0, 0)

        lbl_local = QLabel(tr("dlg_diff_col_local"))
        lbl_local.setStyleSheet(
            f"color: {COLORS['new_file']}; font-weight: 600; font-size: 12px;"
        )
        lbl_remote = QLabel(tr("dlg_diff_col_remote"))
        lbl_remote.setStyleSheet(
            f"color: {COLORS['accent_cyan']}; font-weight: 600; font-size: 12px;"
        )
        cl_layout.addWidget(lbl_local, 1)
        cl_layout.addWidget(lbl_remote, 1)
        layout.addWidget(col_labels)

        # --- Splitter avec 2 QTextBrowser ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {COLORS['border']}; width: 2px; }}"
        )

        self.left_browser = self._create_browser()
        self.right_browser = self._create_browser()
        splitter.addWidget(self.left_browser)
        splitter.addWidget(self.right_browser)
        splitter.setSizes([600, 600])

        layout.addWidget(splitter, 1)

        # --- Status bar ---
        status_frame = QFrame()
        status_frame.setFixedHeight(32)
        status_frame.setStyleSheet(
            f"background-color: {COLORS['bg_card']}; border-top: 1px solid {COLORS['border']};"
        )
        sf_layout = QHBoxLayout(status_frame)
        sf_layout.setContentsMargins(20, 0, 20, 0)

        local_lines = local_text.splitlines()
        remote_lines = remote_text.splitlines()
        self.stats_label = QLabel(
            tr("dlg_diff_stats", local=len(local_lines), remote=len(remote_lines))
        )
        self.stats_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; border: none;"
        )
        sf_layout.addWidget(self.stats_label)
        sf_layout.addStretch()

        btn_close = QPushButton(tr("dlg_close"))
        btn_close.setFixedSize(90, 24)
        btn_close.setStyleSheet(
            f"background-color: {COLORS['bg_card_hover']}; color: {COLORS['text']}; "
            f"font-size: 12px; border-radius: 4px; border: 1px solid {COLORS['border']};"
        )
        btn_close.clicked.connect(self.close)
        sf_layout.addWidget(btn_close)

        layout.addWidget(status_frame)

        # --- Synchronisation du scroll ---
        self.left_browser.verticalScrollBar().valueChanged.connect(
            self.right_browser.verticalScrollBar().setValue
        )
        self.right_browser.verticalScrollBar().valueChanged.connect(
            self.left_browser.verticalScrollBar().setValue
        )
        self.left_browser.horizontalScrollBar().valueChanged.connect(
            self.right_browser.horizontalScrollBar().setValue
        )
        self.right_browser.horizontalScrollBar().valueChanged.connect(
            self.left_browser.horizontalScrollBar().setValue
        )

        # --- Génération du diff ---
        self._generate_diff(local_text, remote_text)

    def _create_browser(self):
        browser = QTextEdit()
        browser.setReadOnly(True)
        browser.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        browser.setStyleSheet(
            f"QTextEdit {{ background-color: {COLORS['bg_dark']}; color: {COLORS['text']}; "
            f"border: none; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; "
            f"padding: 4px; }}"
        )
        return browser

    def _generate_diff(self, local_text, remote_text):
        local_lines = local_text.splitlines()
        remote_lines = remote_text.splitlines()

        matcher = difflib.SequenceMatcher(None, remote_lines, local_lines)

        left_html_lines = []
        right_html_lines = []
        add_count = 0
        del_count = 0

        # Couleurs
        bg_add = "rgba(16, 185, 129, 0.15)"      # vert translucide
        bg_del = "rgba(239, 68, 68, 0.15)"        # rouge translucide
        bg_change = "rgba(245, 158, 11, 0.12)"    # ambre translucide

        line_num_style = f"color: {COLORS['text_muted']}; user-select: none; min-width: 40px; display: inline-block; text-align: right; padding-right: 12px;"
        text_style_normal = f"color: {COLORS['text']};"
        text_style_add = f"color: {COLORS['new_file']};"
        text_style_del = f"color: {COLORS['deleted_file']};"

        local_line_num = 0
        remote_line_num = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    remote_line_num += 1
                    local_line_num += 1
                    escaped = self._escape_html(remote_lines[i1 + k])
                    line = (
                        f'<div style="padding: 1px 4px; white-space: pre;">'
                        f'<span style="{line_num_style}">{remote_line_num}</span>'
                        f'<span style="{text_style_normal}">{escaped}</span></div>'
                    )
                    left_html_lines.append(
                        f'<div style="padding: 1px 4px; white-space: pre;">'
                        f'<span style="{line_num_style}">{local_line_num}</span>'
                        f'<span style="{text_style_normal}">{escaped}</span></div>'
                    )
                    right_html_lines.append(line)

            elif tag == "replace":
                # Lignes supprimées du serveur (côté droit) puis ajoutées en local (côté gauche)
                max_lines = max(i2 - i1, j2 - j1)
                for k in range(max_lines):
                    # Côté local (gauche)
                    if j1 + k < j2:
                        local_line_num += 1
                        escaped = self._escape_html(local_lines[j1 + k])
                        left_html_lines.append(
                            f'<div style="background-color: {bg_add}; padding: 1px 4px; white-space: pre;">'
                            f'<span style="{line_num_style}">{local_line_num}</span>'
                            f'<span style="{text_style_add}">+ {escaped}</span></div>'
                        )
                        add_count += 1
                    else:
                        left_html_lines.append(
                            f'<div style="background-color: {bg_change}; padding: 1px 4px; white-space: pre;">'
                            f'<span style="{line_num_style}"> </span>'
                            f'<span style="color: {COLORS["text_muted"]};">  ~</span></div>'
                        )

                    # Côté serveur (droite)
                    if i1 + k < i2:
                        remote_line_num += 1
                        escaped = self._escape_html(remote_lines[i1 + k])
                        right_html_lines.append(
                            f'<div style="background-color: {bg_del}; padding: 1px 4px; white-space: pre;">'
                            f'<span style="{line_num_style}">{remote_line_num}</span>'
                            f'<span style="{text_style_del}">- {escaped}</span></div>'
                        )
                        del_count += 1
                    else:
                        right_html_lines.append(
                            f'<div style="background-color: {bg_change}; padding: 1px 4px; white-space: pre;">'
                            f'<span style="{line_num_style}"> </span>'
                            f'<span style="color: {COLORS["text_muted"]};">  ~</span></div>'
                        )

            elif tag == "insert":
                for k in range(j2 - j1):
                    local_line_num += 1
                    escaped = self._escape_html(local_lines[j1 + k])
                    left_html_lines.append(
                        f'<div style="background-color: {bg_add}; padding: 1px 4px; white-space: pre;">'
                        f'<span style="{line_num_style}">{local_line_num}</span>'
                        f'<span style="{text_style_add}">+ {escaped}</span></div>'
                    )
                    right_html_lines.append(
                        f'<div style="background-color: {bg_change}; padding: 1px 4px; white-space: pre;">'
                        f'<span style="{line_num_style}"> </span>'
                        f'<span style="color: {COLORS["text_muted"]};">  ~</span></div>'
                    )
                    add_count += 1

            elif tag == "delete":
                for k in range(i2 - i1):
                    remote_line_num += 1
                    escaped = self._escape_html(remote_lines[i1 + k])
                    right_html_lines.append(
                        f'<div style="background-color: {bg_del}; padding: 1px 4px; white-space: pre;">'
                        f'<span style="{line_num_style}">{remote_line_num}</span>'
                        f'<span style="{text_style_del}">- {escaped}</span></div>'
                    )
                    left_html_lines.append(
                        f'<div style="background-color: {bg_change}; padding: 1px 4px; white-space: pre;">'
                        f'<span style="{line_num_style}"> </span>'
                        f'<span style="color: {COLORS["text_muted"]};">  ~</span></div>'
                    )
                    del_count += 1

        wrapper = (
            f'<body style="margin: 0; padding: 0; background: {COLORS["bg_dark"]}; '
            f'font-family: Consolas, monospace; font-size: 13px;">'
        )

        self.left_browser.setHtml(wrapper + "\n".join(left_html_lines) + "</body>")
        self.right_browser.setHtml(wrapper + "\n".join(right_html_lines) + "</body>")

        # Mettre à jour les stats
        self.stats_label.setText(
            tr("dlg_diff_stats_full",
               local=len(local_lines),
               remote=len(remote_lines),
               color_new=COLORS["new_file"],
               add=add_count,
               color_del=COLORS["deleted_file"],
               del_c=del_count)
        )

    @staticmethod
    def _escape_html(text):
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;")


# ============================================================================
# INTERFACE GRAPHIQUE PYQT6
# ============================================================================
class DeployAppSMB(QMainWindow):
    """Main application window — orchestrates scanning, deployment, and UI.

    This is the central class that manages the entire DeployApp interface.
    It handles configuration loading, file scanning (SMB or SSH), deployment,
    server restart, database backup, diff viewing, and deployment history.
    """

    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load()
        self.history = HistoryManager()
        self.version_mgr = VersionManager()
        self.files: List[FileInfo] = []
        self.current_filter = "all"

        # Signals for thread-safe GUI updates
        self.signals = WorkerSignals()
        self.signals.log.connect(self._append_log)
        self.signals.progress.connect(self._set_progress)
        self.signals.status.connect(self._set_status)
        self.signals.ui_state.connect(self._set_ui_state)
        self.signals.refresh_tree.connect(self.refresh_treeview)
        self.signals.refresh_history.connect(self.refresh_history)
        self.signals.refresh_history.connect(self.refresh_changelog)
        self.signals.update_stats.connect(self._do_update_stats)

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — {tr('app_title')}")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 870)

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.create_widgets()

    # ----------------------------------------------------------------
    # CONSTRUCTION UI
    # ----------------------------------------------------------------
    def create_widgets(self):
        # ========== HEADER ==========
        header = QFrame()
        header.setObjectName("headerFrame")
        header.setFixedHeight(80)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(25, 0, 25, 0)

        # Title
        title = QLabel("🚀 DeployApp")
        title_font = QFont()
        title_font.setPointSizeF(20.0)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: white; background: transparent;")
        h_layout.addWidget(title)

        # App version badge
        badge = QLabel(f"v{APP_VERSION}")
        badge_font = QFont()
        badge_font.setPointSizeF(10.0)
        badge_font.setBold(True)
        badge.setFont(badge_font)
        badge.setStyleSheet(
            f"border: 1px solid {COLORS['border']}; color: {COLORS['text_muted']}; "
            f"border-radius: 6px; padding: 4px 8px; margin-left: 10px;"
        )
        h_layout.addWidget(badge)

        # Language Toggle Button
        lang_str = get_language().upper()
        self.btn_lang = QPushButton(f"🌐 {lang_str}")
        self.btn_lang.setFixedSize(60, 28)
        self.btn_lang.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; "
            f"color: {COLORS['text']}; font-size: 12px; border-radius: 4px; margin-left: 10px;"
        )
        self.btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lang.clicked.connect(self.switch_language)
        h_layout.addWidget(self.btn_lang)

        h_layout.addStretch()

        # Deploy version
        self.version_label = QLabel(self._get_version_display())
        v_font = QFont()
        v_font.setPointSizeF(14.0)
        v_font.setBold(True)
        self.version_label.setFont(v_font)
        self.version_label.setStyleSheet(
            f"color: {COLORS['text']}; background: transparent; margin-right: 15px;"
        )
        h_layout.addWidget(self.version_label)

        # Minor +1
        self.btn_minor = QPushButton(tr("btn_minor"))
        self.btn_minor.setObjectName("btnMinor")
        self.btn_minor.clicked.connect(self.bump_minor_version)
        h_layout.addWidget(self.btn_minor)

        # Major +1
        self.btn_major = QPushButton(tr("btn_major"))
        self.btn_major.setObjectName("btnMajor")
        self.btn_major.clicked.connect(self.bump_major_version)
        h_layout.addWidget(self.btn_major)

        self.main_layout.addWidget(header)

        # ========== CONTENT AREA ==========
        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(15, 10, 15, 10)
        c_layout.setSpacing(10)

        # ========== PATHS & METHOD ==========
        paths_frame = QFrame()
        paths_frame.setObjectName("pathsFrame")
        grid = QGridLayout(paths_frame)
        grid.setContentsMargins(15, 12, 15, 12)
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(10)

        # Deploy Method (Row 0, Col 0 & 1)
        self.lbl_method = QLabel(tr("deploy_method_box"))
        self.lbl_method.setStyleSheet(f"font-weight: 600; color: {COLORS['text_muted']};")
        grid.addWidget(self.lbl_method, 0, 0)

        self.combo_method = QComboBox()
        self.combo_method.addItems(["SMB / Local", "SSH / SFTP"])
        if self.config.get("deploy_method") == "ssh":
            self.combo_method.setCurrentIndex(1)
        self.combo_method.currentIndexChanged.connect(self.toggle_ssh_panel)
        grid.addWidget(self.combo_method, 0, 1)

        # Local dir (Row 0, Col 2 & 3)
        self.lbl_local = QLabel(tr("lbl_local_dir"))
        self.lbl_local.setStyleSheet(f"font-weight: 600; color: {COLORS['text_muted']};")
        grid.addWidget(self.lbl_local, 0, 2)

        local_row = QHBoxLayout()
        local_row.setSpacing(0)
        self.local_dir_input = QLineEdit(self.config["local_dir"])
        self.local_dir_input.setStyleSheet(
            "border-top-right-radius: 0; border-bottom-right-radius: 0;"
        )
        self.btn_browse_local = QPushButton(tr("btn_browse"))
        self.btn_browse_local.setStyleSheet(
            f"background-color: {COLORS['bg_card_hover']}; color: {COLORS['text_muted']}; "
            f"border: 1px solid {COLORS['border']}; border-left: none; "
            f"border-top-left-radius: 0; border-bottom-left-radius: 0; font-weight: normal; padding: 6px 10px;"
        )
        self.btn_browse_local.clicked.connect(self.browse_local)
        local_row.addWidget(self.local_dir_input)
        local_row.addWidget(self.btn_browse_local)
        grid.addLayout(local_row, 0, 3)

        # Remote dir (Row 1, Col 2 & 3) — hidden when SSH
        self.lbl_remote = QLabel(tr("lbl_remote_dir"))
        self.lbl_remote.setStyleSheet(f"font-weight: 600; color: {COLORS['text_muted']};")
        grid.addWidget(self.lbl_remote, 1, 2)

        self.remote_dir_widget = QWidget()
        remote_row = QHBoxLayout(self.remote_dir_widget)
        remote_row.setContentsMargins(0, 0, 0, 0)
        remote_row.setSpacing(0)
        self.remote_dir_input = QLineEdit(self.config["remote_dir"])
        self.remote_dir_input.setStyleSheet(
            "border-top-right-radius: 0; border-bottom-right-radius: 0;"
        )
        self.btn_browse_remote = QPushButton(tr("btn_browse"))
        self.btn_browse_remote.setStyleSheet(
            f"background-color: {COLORS['bg_card_hover']}; color: {COLORS['text_muted']}; "
            f"border: 1px solid {COLORS['border']}; border-left: none; "
            f"border-top-left-radius: 0; border-bottom-left-radius: 0; font-weight: normal; padding: 6px 10px;"
        )
        self.btn_browse_remote.clicked.connect(self.browse_remote)
        remote_row.addWidget(self.remote_dir_input)
        remote_row.addWidget(self.btn_browse_remote)
        grid.addWidget(self.remote_dir_widget, 1, 3)

        # SSH Configuration Panel (Row 2, spanning 4 cols)
        self.ssh_panel = QWidget()
        ssh_vlayout = QVBoxLayout(self.ssh_panel)
        ssh_vlayout.setContentsMargins(0, 5, 0, 0)
        ssh_vlayout.setSpacing(10)

        # Ligne 1 SSH: Hôte, Utilisateur, Port
        ssh_row1 = QHBoxLayout()
        ssh_row1.setSpacing(15)

        self.lbl_host = QLabel(tr("lbl_ssh_host"))
        self.lbl_host.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.ssh_host_input = QLineEdit(self.config.get("ssh_host", ""))
        ssh_row1.addWidget(self.lbl_host)
        ssh_row1.addWidget(self.ssh_host_input, stretch=2)

        self.lbl_user = QLabel(tr("lbl_ssh_user"))
        self.lbl_user.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.ssh_user_input = QLineEdit(self.config.get("ssh_user", ""))
        ssh_row1.addWidget(self.lbl_user)
        ssh_row1.addWidget(self.ssh_user_input, stretch=1)

        self.lbl_pw = QLabel(tr("lbl_ssh_password"))
        self.lbl_pw.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.ssh_pw_input = QLineEdit(self.config.get("ssh_password", ""))
        self.ssh_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        ssh_row1.addWidget(self.lbl_pw)
        ssh_row1.addWidget(self.ssh_pw_input, stretch=1)

        self.lbl_port = QLabel(tr("lbl_ssh_port"))
        self.lbl_port.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.ssh_port_input = QLineEdit(str(self.config.get("ssh_port", "22")))
        self.ssh_port_input.setFixedWidth(60)
        ssh_row1.addWidget(self.lbl_port)
        ssh_row1.addWidget(self.ssh_port_input)

        ssh_vlayout.addLayout(ssh_row1)

        # Ligne 2 SSH: Clé privée + Test Btn
        ssh_row2 = QHBoxLayout()
        ssh_row2.setSpacing(15)

        self.lbl_key = QLabel(tr("lbl_ssh_key"))
        self.lbl_key.setStyleSheet(f"color: {COLORS['text_muted']};")
        ssh_row2.addWidget(self.lbl_key)

        key_layout = QHBoxLayout()
        key_layout.setSpacing(0)
        self.ssh_key_input = QLineEdit(self.config.get("ssh_key_path", ""))
        self.ssh_key_input.setStyleSheet(
            "border-top-right-radius: 0; border-bottom-right-radius: 0;"
        )
        self.btn_browse_key = QPushButton(tr("btn_browse_key"))
        self.btn_browse_key.setStyleSheet(
            f"background-color: {COLORS['bg_card_hover']}; color: {COLORS['text_muted']}; "
            f"border: 1px solid {COLORS['border']}; border-left: none; "
            f"border-top-left-radius: 0; border-bottom-left-radius: 0; font-weight: normal; padding: 6px 10px;"
        )
        self.btn_browse_key.clicked.connect(self.browse_ssh_key)
        key_layout.addWidget(self.ssh_key_input)
        key_layout.addWidget(self.btn_browse_key)

        ssh_row2.addLayout(key_layout, stretch=1)

        self.btn_test_ssh = QPushButton(tr("btn_test_ssh"))
        self.btn_test_ssh.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['accent_cyan']}; "
            f"font-size: 12px; font-weight: 500; padding: 6px 12px; color: {COLORS['accent_cyan']}; "
            f"border-radius: 4px;"
        )
        self.btn_test_ssh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_ssh.clicked.connect(self.test_ssh_connection)
        ssh_row2.addWidget(self.btn_test_ssh)

        ssh_vlayout.addLayout(ssh_row2)

        # Add SSH panel to main grid
        grid.addWidget(self.ssh_panel, 2, 0, 1, 4)

        self.ssh_panel.setVisible(self.config.get("deploy_method") == "ssh")

        # Hide remote dir row when SSH is active (use default SSH path)
        is_ssh_init = self.config.get("deploy_method") == "ssh"
        self.lbl_remote.setVisible(not is_ssh_init)
        self.remote_dir_widget.setVisible(not is_ssh_init)

        # Set stretch factors for the grid
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(3, 1)

        c_layout.addWidget(paths_frame)

        # ========== OPTIONS + BUTTONS ==========
        opts_row = QHBoxLayout()
        opts_row.setContentsMargins(0, 5, 0, 5)

        self.btn_exclusions = QPushButton(tr("btn_exclusions"))
        self.btn_exclusions.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; "
            f"color: {COLORS['text_muted']}; padding: 10px 16px; font-weight: 500;"
        )
        self.btn_exclusions.clicked.connect(self.show_exclusions_dialog)
        opts_row.addWidget(self.btn_exclusions)

        opts_row.addSpacing(20)

        # Hash toggle
        hash_layout = QHBoxLayout()
        self.chk_hash = AnimatedToggle()
        self.chk_hash.setChecked(self.config["use_hash_comparison"])
        self.lbl_hash = QLabel(tr("lbl_hash_md5"))
        self.lbl_hash.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: 500;")
        hash_layout.addWidget(self.chk_hash)
        hash_layout.addWidget(self.lbl_hash)
        opts_row.addLayout(hash_layout)

        opts_row.addSpacing(20)

        # Backup toggle
        backup_layout = QHBoxLayout()
        self.chk_backup = AnimatedToggle()
        self.chk_backup.setChecked(self.config["auto_backup"])
        self.lbl_backup = QLabel(tr("lbl_auto_backup"))
        self.lbl_backup.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: 500;")
        backup_layout.addWidget(self.chk_backup)
        backup_layout.addWidget(self.lbl_backup)
        opts_row.addLayout(backup_layout)

        opts_row.addStretch()

        self.btn_restart_server = QPushButton(tr("btn_restart_server"))
        self.btn_restart_server.setFixedSize(140, 42)
        self.btn_restart_server.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; color: {COLORS['warning']}; "
            f"font-weight: 600; font-size: 13px;"
        )
        self.btn_restart_server.clicked.connect(self.restart_server)
        self.btn_restart_server.setVisible(self.config.get("deploy_method") == "ssh")
        opts_row.addWidget(self.btn_restart_server)

        self.btn_backup_db = QPushButton(tr("btn_backup_db"))
        self.btn_backup_db.setFixedSize(140, 42)
        self.btn_backup_db.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; color: {COLORS['accent_cyan']}; "
            f"font-weight: 600; font-size: 13px;"
        )
        self.btn_backup_db.clicked.connect(self.backup_database)
        self.btn_backup_db.setVisible(self.config.get("deploy_method") == "ssh")
        opts_row.addWidget(self.btn_backup_db)

        self.btn_scan = QPushButton(tr("btn_scan"))
        self.btn_scan.setFixedSize(140, 42)
        self.btn_scan.clicked.connect(self.start_scan)
        opts_row.addWidget(self.btn_scan)

        self.btn_deploy = QPushButton(tr("btn_deploy"))
        self.btn_deploy.setObjectName("btnDeploy")
        self.btn_deploy.setFixedSize(140, 42)
        self.btn_deploy.setEnabled(False)
        self.btn_deploy.clicked.connect(self.start_deploy)
        opts_row.addWidget(self.btn_deploy)

        c_layout.addLayout(opts_row)

        # ========== PROGRESS ==========
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        c_layout.addWidget(self.progress)

        # ========== STAT CARDS ==========
        stats_frame = QFrame()
        stats_frame.setObjectName("statsFrame")
        s_layout = QHBoxLayout(stats_frame)
        s_layout.setContentsMargins(10, 5, 10, 5)
        s_layout.setSpacing(15)

        self.stat_labels = {}
        self.stat_labels_title = {}
        stats_config = [
            ("total", tr("stat_total"), COLORS["accent_blue"]),
            ("new", tr("stat_new"), COLORS["new_file"]),
            ("modified", tr("stat_modified"), COLORS["modified_file"]),
            ("deleted", tr("stat_deleted"), COLORS["deleted_file"]),
            ("uptodate", tr("stat_uptodate"), COLORS["success"]),
        ]

        s_layout.addStretch()
        for key, title, color in stats_config:
            badge_widget = QWidget()
            badge_layout = QHBoxLayout(badge_widget)
            badge_layout.setContentsMargins(12, 6, 12, 6)
            badge_widget.setStyleSheet(
                f"background-color: transparent; border: 1px solid {color}; border-radius: 14px;"
            )

            lbl_title = QLabel(f"{title}:")
            lbl_title.setStyleSheet(
                f"color: {color}; font-weight: 500; font-size: 13px; border: none;"
            )
            badge_layout.addWidget(lbl_title)
            self.stat_labels_title[key] = lbl_title

            lbl_val = QLabel("0")
            lbl_val.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 14px; border: none;"
            )
            badge_layout.addWidget(lbl_val)
            self.stat_labels[key] = lbl_val

            s_layout.addWidget(badge_widget)
        s_layout.addStretch()

        c_layout.addWidget(stats_frame)

        # ========== TABS ==========
        self.tabs = QTabWidget()
        c_layout.addWidget(self.tabs, 1)

        # --- Corner Widget for Tabs ---
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 5, 0)

        self.btn_tab_refresh = QPushButton(tr("btn_tab_refresh"))
        self.btn_tab_refresh.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; "
            f"color: {COLORS['text_muted']}; font-size: 12px; padding: 4px 10px; border-radius: 4px; font-weight: normal;"
        )
        self.btn_tab_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_refresh.clicked.connect(self._on_tab_refresh)
        corner_layout.addWidget(self.btn_tab_refresh)

        self.btn_tab_export = QPushButton("📥 Exporter")
        self.btn_tab_export.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; "
            f"color: {COLORS['text_muted']}; font-size: 12px; padding: 4px 10px; border-radius: 4px; font-weight: normal;"
        )
        self.btn_tab_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_export.clicked.connect(self._on_tab_export)
        corner_layout.addWidget(self.btn_tab_export)

        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        self.tabs.currentChanged.connect(self._update_corner_buttons)

        # --- Files tab ---
        files_widget = QWidget()
        files_layout = QVBoxLayout(files_widget)
        files_layout.setContentsMargins(0, 8, 0, 0)

        # File filter buttons
        filter_row = QHBoxLayout()
        self.filter_buttons = {}
        for key, label in [
            ("all", tr("filter_all")),
            ("new", tr("filter_new")),
            ("modified", tr("filter_modified")),
            ("deleted", tr("filter_deleted")),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"background-color: {COLORS['primary'] if key == 'all' else 'transparent'}; "
                f"color: {'white' if key == 'all' else COLORS['text_muted']}; "
                f"border: 1px solid {COLORS['primary'] if key == 'all' else COLORS['border']}; "
                f"font-size: 13px; padding: 6px 16px; border-radius: 4px; font-weight: 500;"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.set_filter(k))
            filter_row.addWidget(btn)
            self.filter_buttons[key] = btn

        filter_row.addStretch()

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Rechercher...")
        self.search_input.setFixedWidth(260)
        self.search_input.textChanged.connect(self.refresh_treeview)
        filter_row.addWidget(self.search_input)

        files_layout.addLayout(filter_row)

        # Selection action buttons
        select_row = QHBoxLayout()
        select_row.setSpacing(6)

        self.btn_sel_all = QPushButton(tr("btn_sel_all"))
        self.btn_sel_all.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; "
            f"font-size: 12px; padding: 4px 10px; color: {COLORS['text_muted']}; border-radius: 4px; font-weight: normal;"
        )
        self.btn_sel_all.clicked.connect(self.select_all)
        select_row.addWidget(self.btn_sel_all)

        self.btn_desel_all = QPushButton(tr("btn_desel_all"))
        self.btn_desel_all.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; "
            f"font-size: 12px; padding: 4px 10px; color: {COLORS['text_muted']}; border-radius: 4px; font-weight: normal;"
        )
        self.btn_desel_all.clicked.connect(self.deselect_all)
        select_row.addWidget(self.btn_desel_all)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {COLORS['border']};")
        sep.setFixedHeight(24)
        select_row.addWidget(sep)

        self.btn_sel_new = QPushButton(tr("filter_new"))
        self.btn_sel_new.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['new_file']}; "
            f"font-size: 12px; padding: 4px 10px; color: {COLORS['new_file']}; border-radius: 4px; font-weight: normal;"
        )
        self.btn_sel_new.clicked.connect(
            lambda: self.toggle_select_by_status(FileStatus.NEW)
        )
        select_row.addWidget(self.btn_sel_new)

        self.btn_sel_mod = QPushButton(tr("filter_modified"))
        self.btn_sel_mod.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['modified_file']}; "
            f"font-size: 12px; padding: 4px 10px; color: {COLORS['modified_file']}; border-radius: 4px; font-weight: normal;"
        )
        self.btn_sel_mod.clicked.connect(
            lambda: self.toggle_select_by_status(FileStatus.MODIFIED)
        )
        select_row.addWidget(self.btn_sel_mod)

        self.btn_sel_del = QPushButton(tr("filter_deleted"))
        self.btn_sel_del.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['deleted_file']}; "
            f"font-size: 12px; padding: 4px 10px; color: {COLORS['deleted_file']}; border-radius: 4px; font-weight: normal;"
        )
        self.btn_sel_del.clicked.connect(
            lambda: self.toggle_select_by_status(FileStatus.DELETED)
        )
        select_row.addWidget(self.btn_sel_del)

        select_row.addStretch()
        files_layout.addLayout(select_row)

        # File tree
        self.file_tree = QTreeWidget()
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.setColumnCount(6)
        self.file_tree.setHeaderLabels(
            [tr("col_check"), tr("col_status"), tr("col_file"), tr("col_size"), tr("col_local"), tr("col_remote")]
        )
        header_view = self.file_tree.header()
        header_view.setStretchLastSection(True)
        header_view.resizeSection(0, 50)
        header_view.resizeSection(1, 100)
        header_view.resizeSection(2, 350)
        header_view.resizeSection(3, 100)
        header_view.resizeSection(4, 130)
        self.file_tree.itemClicked.connect(self.toggle_selection)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_file_context_menu)

        # Affecter le délégué customisé pour le Statut (colonne 1)
        self.badge_delegate_files = BadgeDelegate(self.file_tree)
        self.file_tree.setItemDelegateForColumn(1, self.badge_delegate_files)

        files_layout.addWidget(self.file_tree)

        self.tabs.addTab(files_widget, tr("tab_files"))

        # --- Logs tab ---
        logs_widget = QWidget()
        logs_layout = QVBoxLayout(logs_widget)
        logs_layout.setContentsMargins(0, 8, 0, 0)

        self.btn_clear_logs = QPushButton(tr("btn_clear_logs"))
        self.btn_clear_logs.setFixedWidth(180)
        self.btn_clear_logs.setStyleSheet(
            f"background-color: transparent; border: 1px solid {COLORS['border']}; font-size: 12px; border-radius: 4px; color: {COLORS['text_muted']}; font-weight: normal;"
        )
        self.btn_clear_logs.clicked.connect(self.clear_logs)
        logs_layout.addWidget(self.btn_clear_logs, alignment=Qt.AlignmentFlag.AlignLeft)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        logs_layout.addWidget(self.log_text)

        self.tabs.addTab(logs_widget, tr("tab_logs"))

        # --- History tab ---
        hist_widget = QWidget()
        hist_layout = QVBoxLayout(hist_widget)
        hist_layout.setContentsMargins(0, 8, 0, 0)

        self.hist_tree = QTreeWidget()
        self.hist_tree.setAlternatingRowColors(True)
        self.hist_tree.setRootIsDecorated(False)
        self.hist_tree.setColumnCount(7)
        self.hist_tree.setHeaderLabels(
            [tr("col_hist_version"), tr("col_hist_date"), tr("col_hist_status"), tr("col_hist_total"), tr("col_hist_success"), tr("col_hist_errors"), tr("col_hist_duration")]
        )
        h_header = self.hist_tree.header()
        h_header.setStretchLastSection(True)
        h_header.resizeSection(0, 90)
        h_header.resizeSection(1, 170)
        h_header.resizeSection(2, 110)
        h_header.resizeSection(3, 70)
        h_header.resizeSection(4, 70)
        h_header.resizeSection(5, 70)
        self.hist_tree.itemDoubleClicked.connect(self.show_deployment_detail)

        # Affecter le délégué customisé pour le Statut (colonne 2)
        self.badge_delegate_hist = BadgeDelegate(self.hist_tree)
        self.hist_tree.setItemDelegateForColumn(2, self.badge_delegate_hist)

        hist_layout.addWidget(self.hist_tree)

        self.tabs.addTab(hist_widget, tr("tab_history"))

        # --- Changelog tab ---
        changelog_widget = QWidget()
        cl_layout = QVBoxLayout(changelog_widget)
        cl_layout.setContentsMargins(0, 8, 0, 0)

        self.changelog_tree = QTreeWidget()
        self.changelog_tree.setAlternatingRowColors(True)
        self.changelog_tree.setRootIsDecorated(False)
        self.changelog_tree.setColumnCount(7)
        self.changelog_tree.setHeaderLabels(
            [
                tr("col_cl_version"),
                tr("col_cl_date"),
                tr("col_cl_added"),
                tr("col_cl_modified"),
                tr("col_cl_deleted"),
                tr("col_cl_result"),
                tr("col_cl_duration"),
            ]
        )
        cl_header = self.changelog_tree.header()
        cl_header.setStretchLastSection(True)
        cl_header.resizeSection(0, 90)
        cl_header.resizeSection(1, 170)
        cl_header.resizeSection(2, 90)
        cl_header.resizeSection(3, 90)
        cl_header.resizeSection(4, 90)
        cl_header.resizeSection(5, 120)
        self.changelog_tree.itemDoubleClicked.connect(self.show_changelog_detail)

        # Affecter le délégué customisé pour le Résultat (colonne 5)
        self.badge_delegate_cl = BadgeDelegate(self.changelog_tree)
        self.changelog_tree.setItemDelegateForColumn(5, self.badge_delegate_cl)

        cl_layout.addWidget(self.changelog_tree)

        self.tabs.addTab(changelog_widget, tr("tab_changelog"))

        self.main_layout.addWidget(content, 1)

        # ========== STATUS BAR ==========
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_bar.setFixedHeight(35)
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(20, 0, 20, 0)
        self.status_label = QLabel(tr("status_ready"))
        self.status_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 13px; background: transparent;"
        )
        sb_layout.addWidget(self.status_label)
        sb_layout.addStretch()
        lbl_v = QLabel(f"DeployApp v{APP_VERSION} © 2026")
        lbl_v.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; background: transparent;"
        )
        sb_layout.addWidget(lbl_v)
        self.main_layout.addWidget(status_bar)

        self._update_corner_buttons(0)
        self.refresh_history()
        self.refresh_changelog()
        
        # Apply initial translations
        self.retranslate_ui()

    def switch_language(self):
        current = get_language()
        new_lang = "en" if current == "fr" else "fr"
        set_language(new_lang)
        self.btn_lang.setText(f"🌐 {new_lang.upper()}")
        
        # Save to config
        self.config["language"] = new_lang
        ConfigManager.save(self.config)
        
        # Reload UI text
        self.retranslate_ui()

    def retranslate_ui(self):
        # Paths & Method
        self.btn_minor.setText(tr("btn_minor"))
        self.btn_major.setText(tr("btn_major"))
        self.lbl_method.setText(tr("deploy_method_box"))
        
        cur_idx = self.combo_method.currentIndex()
        self.combo_method.blockSignals(True)
        self.combo_method.clear()
        self.combo_method.addItems([tr("method_smb"), tr("method_ssh")])
        self.combo_method.setCurrentIndex(cur_idx)
        self.combo_method.blockSignals(False)
        
        self.lbl_local.setText(tr("lbl_local_dir"))
        self.btn_browse_local.setText(tr("btn_browse"))
        self.lbl_remote.setText(tr("lbl_remote_dir"))
        self.btn_browse_remote.setText(tr("btn_browse"))
        
        self.lbl_host.setText(tr("lbl_ssh_host"))
        self.lbl_user.setText(tr("lbl_ssh_user"))
        self.lbl_pw.setText(tr("lbl_ssh_password"))
        self.lbl_port.setText(tr("lbl_ssh_port"))
        self.lbl_key.setText(tr("lbl_ssh_key"))
        self.btn_browse_key.setText(tr("btn_browse_key"))
        
        if self.btn_test_ssh.isEnabled():
            self.btn_test_ssh.setText(tr("btn_test_ssh"))
            
        self.btn_exclusions.setText(tr("btn_exclusions"))
        self.lbl_hash.setText(tr("lbl_hash_md5"))
        self.lbl_backup.setText(tr("lbl_auto_backup"))
        
        if self.btn_restart_server.isEnabled():
            self.btn_restart_server.setText(tr("btn_restart_server"))
        if self.btn_backup_db.isEnabled():
            self.btn_backup_db.setText(tr("btn_backup_db"))
            
        self.btn_scan.setText(tr("btn_scan"))
        self.btn_deploy.setText(tr("btn_deploy"))

        self.stat_labels_title["total"].setText(f"{tr('stat_total')}:")
        self.stat_labels_title["new"].setText(f"{tr('stat_new')}:")
        self.stat_labels_title["modified"].setText(f"{tr('stat_modified')}:")
        self.stat_labels_title["deleted"].setText(f"{tr('stat_deleted')}:")
        self.stat_labels_title["uptodate"].setText(f"{tr('stat_uptodate')}:")
        
        self.tabs.setTabText(0, tr("tab_files"))
        self.tabs.setTabText(1, tr("tab_logs"))
        self.tabs.setTabText(2, tr("tab_history"))
        self.tabs.setTabText(3, tr("tab_changelog"))
        
        self.btn_tab_refresh.setText(tr("btn_tab_refresh"))
        self.btn_tab_export.setText(tr("btn_tab_export"))
        
        self.filter_buttons["all"].setText(tr("filter_all"))
        self.filter_buttons["new"].setText(tr("filter_new"))
        self.filter_buttons["modified"].setText(tr("filter_modified"))
        self.filter_buttons["deleted"].setText(tr("filter_deleted"))
        
        self.search_input.setPlaceholderText(tr("search_placeholder"))
        
        self.btn_sel_all.setText(tr("btn_sel_all"))
        self.btn_desel_all.setText(tr("btn_desel_all"))
        self.btn_sel_new.setText(tr("filter_new"))
        self.btn_sel_mod.setText(tr("filter_modified"))
        self.btn_sel_del.setText(tr("filter_deleted"))
        
        self.file_tree.setHeaderLabels([
            tr("col_check"), tr("col_status"), tr("col_file"), 
            tr("col_size"), tr("col_local"), tr("col_remote")
        ])
        
        self.btn_clear_logs.setText(tr("btn_clear_logs"))
        
        self.hist_tree.setHeaderLabels([
            tr("col_hist_version"), tr("col_hist_date"), tr("col_hist_status"),
            tr("col_hist_total"), tr("col_hist_success"), tr("col_hist_errors"),
            tr("col_hist_duration")
        ])
        
        self.changelog_tree.setHeaderLabels([
            tr("col_cl_version"), tr("col_cl_date"), tr("col_cl_added"),
            tr("col_cl_modified"), tr("col_cl_deleted"), tr("col_cl_result"),
            tr("col_cl_duration")
        ])
        
        # Trigger refresh on tables to update their contents
        self.refresh_treeview()
        self.refresh_history()
        self.refresh_changelog()
        
        if tr("status_ready") in self.status_label.text():
            if self.files and any(f.status != FileStatus.UPTODATE for f in self.files):
                c = sum(1 for f in self.files if f.status != FileStatus.UPTODATE)
                self.status_label.setText(tr("status_scan_ready", count=c))
            else:
                self.status_label.setText(tr("status_ready"))

    def _update_corner_buttons(self, index: int):
        if index in (2, 3):
            self.btn_tab_refresh.setVisible(True)
            self.btn_tab_export.setVisible(True)
        else:
            self.btn_tab_refresh.setVisible(False)
            self.btn_tab_export.setVisible(False)

    def _on_tab_refresh(self):
        index = self.tabs.currentIndex()
        if index == 2:
            self.refresh_history()
        elif index == 3:
            self.refresh_changelog()

    def _on_tab_export(self):
        index = self.tabs.currentIndex()
        if index == 2:
            self.export_history_csv()
        elif index == 3:
            self.export_changelog_md()

    # ----------------------------------------------------------------
    # VERSION DISPLAY
    # ----------------------------------------------------------------
    def _get_version_display(self) -> str:
        local_dir = (
            self.local_dir_input.text()
            if hasattr(self, "local_dir_input")
            else self.config["local_dir"]
        )
        v = self.version_mgr.read_version(local_dir)
        return f"🏷 v{v[0]}.{v[1]}.{v[2]}"

    def _update_version_label(self):
        self.version_label.setText(self._get_version_display())

    def bump_major_version(self):
        local_dir = self.local_dir_input.text()
        if not local_dir:
            return QMessageBox.warning(
                self, tr("msg_err_title"), tr("err_local_dir_missing")
            )
        current = self.version_mgr.read_version(local_dir)
        new_ver = (current[0] + 1, 0, 0)
        r = QMessageBox.question(
            self,
            tr("title_bump_major"),
            tr("question_bump_major", current=f"v{current[0]}.{current[1]}.{current[2]}", new_ver=f"v{new_ver[0]}.{new_ver[1]}.{new_ver[2]}")
        )
        if r == QMessageBox.StandardButton.Yes:
            self.version_mgr.write_version(local_dir, new_ver)
            self._update_version_label()
            self.log(tr("log_version_arrow_v", v=f"{new_ver[0]}.{new_ver[1]}.{new_ver[2]}"), "success")

    def bump_minor_version(self):
        local_dir = self.local_dir_input.text()
        if not local_dir:
            return QMessageBox.warning(
                self, tr("msg_err_title"), tr("err_local_dir_missing")
            )
        current = self.version_mgr.read_version(local_dir)
        new_ver = (current[0], current[1] + 1, 0)
        r = QMessageBox.question(
            self,
            tr("title_bump_minor"),
            tr("question_bump_minor", current=f"v{current[0]}.{current[1]}.{current[2]}", new_ver=f"v{new_ver[0]}.{new_ver[1]}.{new_ver[2]}")
        )
        if r == QMessageBox.StandardButton.Yes:
            self.version_mgr.write_version(local_dir, new_ver)
            self._update_version_label()
            self.log(tr("log_version_arrow_v", v=f"{new_ver[0]}.{new_ver[1]}.{new_ver[2]}"), "success")

    # ----------------------------------------------------------------
    # LOGS
    # ----------------------------------------------------------------
    def log(self, message, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.signals.log.emit(f"[{ts}] {message}", level)

    def _append_log(self, msg, level):
        color_map = {
            "info": COLORS["text"],
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "error": COLORS["error"],
            "header": COLORS["accent_cyan"],
        }
        color = color_map.get(level, COLORS["text"])
        self.log_text.append(f'<span style="color:{color}">{msg}</span>')

    def clear_logs(self):
        self.log_text.clear()

    # ----------------------------------------------------------------
    # PROGRESS & STATUS
    # ----------------------------------------------------------------
    def _set_progress(self, val):
        self.progress.setValue(int(val * 1000))

    def _set_status(self, msg):
        self.status_label.setText(msg)

    def _set_ui_state(self, enabled):
        self.btn_scan.setEnabled(enabled)
        self.btn_deploy.setEnabled(enabled and bool(self.files))

    def _do_update_stats(self, total, new, modified, deleted, uptodate):
        self.stat_labels["total"].setText(str(total))
        self.stat_labels["new"].setText(str(new))
        self.stat_labels["modified"].setText(str(modified))
        self.stat_labels["deleted"].setText(str(deleted))
        self.stat_labels["uptodate"].setText(str(uptodate))

    # ----------------------------------------------------------------
    # BROWSE
    # ----------------------------------------------------------------
    def browse_local(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("lbl_diff_local"), self.local_dir_input.text()
        )
        if d:
            self.local_dir_input.setText(os.path.normpath(d))
            self._update_version_label()

    def browse_remote(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("lbl_diff_remote"), self.remote_dir_input.text()
        )
        if d:
            self.remote_dir_input.setText(os.path.normpath(d))

    def toggle_ssh_panel(self, index):
        is_ssh = index == 1
        if is_ssh:
            self.ssh_panel.setVisible(True)
            if hasattr(self, "btn_restart_server"):
                self.btn_restart_server.setVisible(True)
            if hasattr(self, "btn_backup_db"):
                self.btn_backup_db.setVisible(True)
        else:
            self.ssh_panel.setVisible(False)
            if hasattr(self, "btn_restart_server"):
                self.btn_restart_server.setVisible(False)
            if hasattr(self, "btn_backup_db"):
                self.btn_backup_db.setVisible(False)
        # Show/hide remote dir row (SSH uses a fixed path)
        self.lbl_remote.setVisible(not is_ssh)
        self.remote_dir_widget.setVisible(not is_ssh)
        self.config["deploy_method"] = "ssh" if is_ssh else "smb"
        ConfigManager.save(self.config)

    def browse_ssh_key(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("title_select_ssh_key"), "")
        if f:
            self.ssh_key_input.setText(f)

    def test_ssh_connection(self):
        ssh_cfg = {
            "host": self.ssh_host_input.text().strip(),
            "port": self.ssh_port_input.text().strip() or "22",
            "user": self.ssh_user_input.text().strip(),
            "password": self.ssh_pw_input.text().strip(),
            "key_path": self.ssh_key_input.text().strip(),
        }
        if not ssh_cfg["host"]:
            QMessageBox.warning(self, tr("msg_err_title"), tr("err_ssh_host_missing"))
            return

        self.btn_test_ssh.setEnabled(False)
        self.btn_test_ssh.setText(tr("btn_test_ssh_loading"))
        self.status_label.setText(tr("status_ssh_test"))
        QApplication.processEvents()

        try:
            deployer = SSHDeployer(**ssh_cfg)
            deployer.connect()
            deployer.disconnect()
            QMessageBox.information(self, tr("msg_success_title"), tr("msg_ssh_success"))
            self.log(tr("msg_ssh_success"), "success")
        except Exception as e:
            QMessageBox.critical(self, tr("msg_err_title"), tr("msg_ssh_fail", err=e))
            self.log(tr("msg_ssh_fail", err=e), "error")
        finally:
            self.btn_test_ssh.setEnabled(True)
            self.btn_test_ssh.setText(tr("btn_test_ssh"))
            self.status_label.setText(tr("status_ready"))

    def restart_server(self):
        ssh_cfg = {
            "host": self.ssh_host_input.text().strip(),
            "port": self.ssh_port_input.text().strip() or "22",
            "user": self.ssh_user_input.text().strip(),
            "password": self.ssh_pw_input.text().strip(),
            "key_path": self.ssh_key_input.text().strip(),
        }
        if not ssh_cfg["host"]:
            QMessageBox.warning(self, tr("msg_err_title"), tr("err_ssh_host_missing"))
            return

        reply = QMessageBox.question(
            self,
            tr("msg_warn_title"),
            tr("question_restart"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_restart_server.setEnabled(False)
        self.btn_restart_server.setText(tr("btn_restart_server_loading"))
        self.status_label.setText(tr("status_restarting"))
        QApplication.processEvents()

        def _do_restart():
            deployer = None
            try:
                deployer = SSHDeployer(**ssh_cfg)
                deployer.connect()

                self.log(tr("status_restarting"), "info")

                srv_cfg = self.config.get("server", {})
                app_port = srv_cfg.get("app_port", 8080)
                app_entry = srv_cfg.get("app_entry", "app:app")
                w_threads = srv_cfg.get("waitress_threads", 4)
                w_max_body = srv_cfg.get("waitress_max_body_size", 52428800)
                task_name = srv_cfg.get("task_name", "StartWaitress")
                use_nginx = srv_cfg.get("use_nginx", True)
                nginx_reload = srv_cfg.get("nginx_reload_cmd", "nginx -s reload")
                nginx_start = srv_cfg.get("nginx_start_cmd", "start nginx")

                # 1. Kill app (trouver PID sur le port puis taskkill, en ignorant PID 0)
                kill_cmd = f'cmd /c "for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{app_port} ^| findstr LISTENING\') do if not "%a"=="0" taskkill /f /pid %a"'
                self.log(tr("log_svc_stop_port", port=app_port), "info")
                exit_code, out, err = deployer.execute_command(kill_cmd)
                if (
                    err
                    and "not found" not in err.lower()
                    and "introuvable" not in err.lower()
                ):
                    self.log(tr("log_svc_stop_warn", err=err), "warning")

                # 2. Start Waitress (en tâche de fond pour que SSH ne bloque pas)
                remote_dir = self.config.get("ssh_remote_dir", "")
                if not remote_dir:
                    remote_dir = self.remote_dir_input.text()
                
                self.log(tr("log_svc_write_scripts", rdir=remote_dir), "info")
                
                # Écrire le .bat directement via SFTP (mode binaire pour contrôler exactement les octets)
                bat_content = f'cd /d "{remote_dir}"\r\nwaitress-serve --threads={w_threads} --listen=0.0.0.0:{app_port} --max-request-body-size={w_max_body} {app_entry} > waitress_error.log 2>&1\r\n'
                bat_path = remote_dir.replace("\\", "/") + "/start_waitress.bat"
                with deployer.sftp.open(bat_path, 'wb') as f:
                    f.write(bat_content.encode('ascii'))
                
                # Écrire le .vbs directement via SFTP
                bat_win_path = remote_dir + "\\start_waitress.bat"
                vbs_line1 = 'Set WshShell = CreateObject("WScript.Shell")'
                vbs_line2 = f'WshShell.Run """" & "{bat_win_path}" & """", 0, False'
                vbs_content = vbs_line1 + "\r\n" + vbs_line2 + "\r\n"
                vbs_path = remote_dir.replace("\\", "/") + "/start_waitress.vbs"
                with deployer.sftp.open(vbs_path, 'wb') as f:
                    f.write(vbs_content.encode('ascii'))
                
                self.log(tr("log_svc_config_task"), "info")
                
                bat_win_path = remote_dir + "\\start_waitress.bat"
                
                # Écrire un script PowerShell complet via SFTP pour configurer la tâche
                ps1_content = f"""
                                # Remove old task if exists
                                Unregister-ScheduledTask -TaskName '{task_name}' -Confirm:$false -ErrorAction SilentlyContinue

                                # Action: launch bat
                                $action = New-ScheduledTaskAction -Execute '{bat_win_path}'

                                # Trigger: at startup
                                $trigger = New-ScheduledTaskTrigger -AtStartup

                                # Settings: restart every 1 min on failure, max 3 retries, no time limit
                                $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 0)

                                # Register task under SYSTEM account (runs without user login)
                                Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force

                                # Start immediately
                                Start-ScheduledTask -TaskName '{task_name}'

                                Write-Output 'OK'
                                """
                ps1_path = remote_dir.replace("\\", "/") + "/setup_waitress_task.ps1"
                with deployer.sftp.open(ps1_path, 'wb') as f:
                    f.write(ps1_content.encode('utf-8'))
                
                # Exécuter le script via SSH
                launch_cmd = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{remote_dir}\\setup_waitress_task.ps1"'
                exit_code, out, err = deployer.execute_command(launch_cmd)
                self.log(tr("log_svc_setup_task", exit=exit_code, out=out[:200] if out else 'vide', err=err[:200] if err else 'vide'), "info")
                
                if exit_code == 0 and 'OK' in out:
                    self.log(tr("log_svc_started", task=task_name), "success")
                else:
                    self.log(tr("log_svc_task_err", err=err[:300] if err else out[:300] if out else 'inconnu'), "error")

                # 3. Reload ou Start Nginx (si activé)
                if use_nginx:
                    self.log(tr("log_svc_nginx_restart"), "info")
                    exit_code, out, err = deployer.execute_command(nginx_reload)
                    if exit_code != 0:
                        deployer.execute_command(nginx_start)

                self.log(tr("log_svc_all_ok"), "success")
                QMetaObject.invokeMethod(
                    self, "_on_restart_success", Qt.ConnectionType.QueuedConnection
                )

            except Exception as e:
                self.log(f"{tr('status_restart_error')} : {e}", "error")
                QMetaObject.invokeMethod(
                    self,
                    "_on_restart_error",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, str(e)),
                )

            finally:
                if deployer:
                    deployer.disconnect()

        from PyQt6.QtCore import QMetaObject, Q_ARG

        threading.Thread(target=_do_restart, daemon=True).start()

    from PyQt6.QtCore import pyqtSlot

    @pyqtSlot()
    def _on_restart_success(self):
        self.btn_restart_server.setEnabled(True)
        self.btn_restart_server.setText(tr("btn_restart_server"))
        self.status_label.setText(tr("status_ready"))
        QMessageBox.information(
            self, tr("msg_success_title"), tr("msg_restart_success")
        )

    @pyqtSlot(str)
    def _on_restart_error(self, err_msg):
        self.btn_restart_server.setEnabled(True)
        self.btn_restart_server.setText(tr("btn_restart_server"))
        self.status_label.setText(tr("status_restart_error"))
        QMessageBox.critical(self, tr("msg_err_title"), tr("msg_restart_fail", err=err_msg))

    def backup_database(self):
        ssh_cfg = {
            "host": self.ssh_host_input.text().strip(),
            "port": self.ssh_port_input.text().strip() or "22",
            "user": self.ssh_user_input.text().strip(),
            "password": self.ssh_pw_input.text().strip(),
            "key_path": self.ssh_key_input.text().strip(),
        }
        if not ssh_cfg["host"]:
            QMessageBox.warning(self, tr("msg_err_title"), tr("err_ssh_host_missing"))
            return

        reply = QMessageBox.question(
            self,
            tr("msg_confirm_title"),
            tr("question_backup"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_backup_db.setEnabled(False)
        self.btn_backup_db.setText(tr("btn_backup_db_loading"))
        self.status_label.setText(tr("status_backup"))
        QApplication.processEvents()

        ps_script = """
            $BackupDir = "{backup_dir}"
            $BackupDir2 = "{backup_nas_dir}"
            $MySqlDumpPath = "{mysqldump_path}"
            $DbUser = "{db_user}"
            $DbPass = "{db_password}"
            $DateStr = Get-Date -Format "yyyy-MM-dd_HH-mm"
            $RetentionDays = {retention_days}

            if (!(Test-Path -Path $BackupDir)) {{
                New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
            }}

            $BackupFile = "$BackupDir\\backup_$DateStr.sql"

            # Use --force to ignore invalid views
            & $MySqlDumpPath -u $DbUser -p"$DbPass" --all-databases --single-transaction --force > $BackupFile

            if (Test-Path $BackupFile) {{
                Compress-Archive -Path $BackupFile -DestinationPath "$BackupFile.zip" -Force
                Remove-Item -Path $BackupFile
                
                # Try copying to NAS, catch error if authentication fails over SSH
                try {{
                    if (!(Test-Path -Path $BackupDir2 -ErrorAction Stop)) {{
                        New-Item -ItemType Directory -Path $BackupDir2 -ErrorAction Stop | Out-Null
                    }}
                    Copy-Item -Path "$BackupFile.zip" -Destination "$BackupDir2\\backup_$DateStr.zip" -Force -ErrorAction Stop
                    Get-ChildItem -Path $BackupDir2 -Filter "backup_*.zip" -ErrorAction SilentlyContinue | Where-Object {{ $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) }} | Remove-Item -ErrorAction SilentlyContinue
                }} catch {{
                    Write-Output "Warning: Error copying to NAS (likely authentication): $($_.Exception.Message)"
                }}
            }}

            Get-ChildItem -Path $BackupDir -Filter "backup_*.zip" | Where-Object {{ $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) }} | Remove-Item
        """

        bkp_cfg = self.config.get("backup", {})
        ps_script = ps_script.format(
            backup_dir=bkp_cfg.get("backup_dir", "C:\\Backups").replace("\\", "\\\\"),
            backup_nas_dir=bkp_cfg.get("backup_nas_dir", "").replace("\\", "\\\\"),
            mysqldump_path=bkp_cfg.get("mysqldump_path", "mysqldump.exe").replace("\\", "\\\\"),
            db_user=bkp_cfg.get("db_user", "root"),
            db_password=bkp_cfg.get("db_password", ""),
            retention_days=bkp_cfg.get("retention_days", 30),
        )

        encoded_script = base64.b64encode(ps_script.encode("utf-16le")).decode("utf-8")
        cmd = f"powershell.exe -NonInteractive -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded_script}"

        def _do_backup():
            deployer = None
            try:
                deployer = SSHDeployer(**ssh_cfg)
                deployer.connect()

                self.log(tr("status_backup"), "info")
                exit_code, out, err = deployer.execute_command(cmd)

                if exit_code != 0:
                    raise Exception(f"Exit {exit_code}\n{err}")

                self.log(tr("log_backup_db_ok"), "success")
                QMetaObject.invokeMethod(
                    self, "_on_backup_success", Qt.ConnectionType.QueuedConnection
                )

            except Exception as e:
                self.log(f"{tr('status_backup_error')} : {e}", "error")
                QMetaObject.invokeMethod(
                    self,
                    "_on_backup_error",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, str(e)),
                )

            finally:
                if deployer:
                    deployer.disconnect()

        from PyQt6.QtCore import QMetaObject, Q_ARG

        threading.Thread(target=_do_backup, daemon=True).start()

    @pyqtSlot()
    def _on_backup_success(self):
        self.btn_backup_db.setEnabled(True)
        self.btn_backup_db.setText(tr("btn_backup_db"))
        self.status_label.setText(tr("status_ready"))
        QMessageBox.information(
            self, tr("msg_success_title"), tr("msg_backup_success")
        )

    @pyqtSlot(str)
    def _on_backup_error(self, err_msg):
        self.btn_backup_db.setEnabled(True)
        self.btn_backup_db.setText(tr("btn_backup_db"))
        self.status_label.setText(tr("msg_err_title"))
        QMessageBox.critical(self, tr("msg_err_title"), tr("msg_backup_fail", err=err_msg))

    def show_exclusions_dialog(self):
        # Pass the config dictionary so the dialog can read and update "ignore_patterns"
        dlg = IgnorePatternsDialog(self, self.config)
        dlg.exec()

    def _show_file_context_menu(self, pos):
        item = self.file_tree.itemAt(pos)
        if not item:
            return
        rel_path = item.text(2)
        if not rel_path:
            return

        file_name = os.path.basename(rel_path)
        # Use the top-level folder as the exclusion target
        parent_parts = rel_path.replace("/", os.sep).split(os.sep)
        immediate_folder = parent_parts[0] if len(parent_parts) > 1 else None

        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self)
        menu.setStyleSheet(STYLESHEET)

        # Option: Diff visuel (uniquement pour les fichiers modifiés)
        file_status = item.text(1)
        if file_status in (tr("fs_modified"), FileStatus.MODIFIED.value):
            act_diff = QAction(tr("ctx_diff"), self)
            act_diff.triggered.connect(lambda: self._show_diff_for_file(rel_path))
            menu.addAction(act_diff)
            menu.addSeparator()

        # Option: exclude this specific file
        act_file = QAction(tr("ctx_exclude_file", name=file_name), self)
        act_file.triggered.connect(lambda: self._add_exclusion(file_name))
        menu.addAction(act_file)

        # Option: exclude the parent folder (only if file is inside a subfolder)
        if immediate_folder:
            act_folder = QAction(tr("ctx_exclude_folder", name=immediate_folder), self)
            act_folder.triggered.connect(lambda: self._add_exclusion(immediate_folder))
            menu.addAction(act_folder)

        menu.exec(self.file_tree.viewport().mapToGlobal(pos))

    def _add_exclusion(self, pattern):
        """Add a pattern to the ignore list, save config, and refresh the tree."""
        ignore_patterns = self.config.get("ignore_patterns", [])
        all_patterns = self.config.get("all_ignore_patterns", [])

        if pattern not in ignore_patterns:
            ignore_patterns.append(pattern)
        if pattern not in all_patterns:
            all_patterns.append(pattern)

        self.config["ignore_patterns"] = ignore_patterns
        self.config["all_ignore_patterns"] = all_patterns
        ConfigManager.save(self.config)

        # Remove matching files from the current scan results
        self.files = [
            f for f in self.files
            if not fnmatch.fnmatch(os.path.basename(f.relative_path), pattern)
            and not any(part == pattern for part in f.relative_path.replace('/', os.sep).split(os.sep))
        ]
        self.update_stats()
        self.refresh_treeview()
        self.log(tr("log_exclusion_added", pat=pattern), "info")

    # ----------------------------------------------------------------
    # DIFF VISUEL
    # ----------------------------------------------------------------
    def _read_local_file_content(self, file_path):
        """Reads the text content of a local file with encoding management.
        Returns the content (str) or None if binary/unreadable."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            pass
        try:
            with open(file_path, "r", encoding="iso-8859-1") as f:
                return f.read()
        except UnicodeDecodeError:
            pass
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                # Vérification heuristique : si trop de caractères de remplacement, c'est probablement du binaire
                if content.count("\ufffd") > len(content) * 0.1:
                    return None
                return content
        except Exception:
            return None

    def _read_remote_file_content(self, remote_path):
        """Reads the text content of a remote file.
        Handles SMB (network path) and SSH/SFTP.
        Returns the content (str) or None if binary/unreadable."""
        method = self.config.get("deploy_method", "smb")

        if method == "smb":
            # Lecture via chemin réseau classique
            return self._read_local_file_content(remote_path)
        else:
            # Lecture via SSH/SFTP
            ssh_cfg = {
                "host": self.ssh_host_input.text().strip(),
                "port": self.ssh_port_input.text().strip() or "22",
                "user": self.ssh_user_input.text().strip(),
                "password": self.ssh_pw_input.text().strip(),
                "key_path": self.ssh_key_input.text().strip(),
            }
            deployer = None
            try:
                deployer = SSHDeployer(**ssh_cfg)
                deployer.connect()
                with deployer.sftp.open(remote_path, "rb") as f:
                    raw_data = f.read()
                deployer.disconnect()

                # Tenter les décodages
                for encoding in ["utf-8", "iso-8859-1"]:
                    try:
                        return raw_data.decode(encoding)
                    except (UnicodeDecodeError, AttributeError):
                        continue
                # Fallback avec remplacement
                content = raw_data.decode("utf-8", errors="replace")
                if content.count("\ufffd") > len(content) * 0.1:
                    return None
                return content

            except Exception as e:
                self.log(tr("err_read_remote", err=e), "error")
                return None
            finally:
                if deployer:
                    try:
                        deployer.disconnect()
                    except Exception:
                        pass

    def _show_diff_for_file(self, rel_path):
        """Opens the DiffDialog to compare a local file with its server version."""
        # Retrouver le FileInfo
        file_info = None
        for f in self.files:
            if f.relative_path == rel_path:
                file_info = f
                break

        if not file_info:
            QMessageBox.warning(self, tr("msg_err_title"), f"{tr('msg_file_not_found')}{rel_path}")
            return

        self.status_label.setText(f"Chargement du diff pour {rel_path}...")
        QApplication.processEvents()

        # Lire le contenu local
        local_content = self._read_local_file_content(file_info.local_path)
        if local_content is None:
            QMessageBox.information(
                self,
                tr("msg_bin_title"),
                tr("msg_binary_local") + rel_path,
            )
            self.status_label.setText(tr("status_ready"))
            return

        # Lire le contenu distant
        remote_content = self._read_remote_file_content(file_info.remote_path)
        if remote_content is None:
            QMessageBox.information(
                self,
                tr("msg_bin_title"),
                tr("msg_binary_remote") + rel_path,
            )
            self.status_label.setText(tr("status_ready"))
            return

        self.status_label.setText(tr("status_ready"))

        # Ouvrir le dialogue de diff
        dlg = DiffDialog(
            parent=self,
            local_text=local_content,
            remote_text=remote_content,
            file_name=rel_path,
        )
        dlg.exec()

    # ----------------------------------------------------------------
    # FILTERS & SELECTION
    # ----------------------------------------------------------------
    def set_filter(self, filter_key):
        self.current_filter = filter_key
        for key, btn in self.filter_buttons.items():
            btn.setStyleSheet(
                f"background-color: {COLORS['primary'] if key == filter_key else COLORS['bg_card']}; "
                f"font-size: 13px; padding: 6px 16px;"
            )
        self.refresh_treeview()

    def toggle_selection(self, item, column):
        rel_path = item.text(2)
        for f in self.files:
            if f.relative_path == rel_path:
                f.selected = not f.selected
                break
        self.refresh_treeview()

    def select_all(self):
        for f in self.files:
            if f.status != FileStatus.UPTODATE:
                f.selected = True
        self.refresh_treeview()

    def deselect_all(self):
        for f in self.files:
            f.selected = False
        self.refresh_treeview()

    def toggle_select_by_status(self, status: FileStatus):
        """Toggle selection for all files of a given status.
        If all are selected → deselect all. Otherwise → select all."""
        matching = [f for f in self.files if f.status == status]
        if not matching:
            return
        all_selected = all(f.selected for f in matching)
        for f in matching:
            f.selected = not all_selected
        self.refresh_treeview()

    def refresh_treeview(self):
        self.file_tree.clear()
        search_term = (
            self.search_input.text().lower().strip()
            if hasattr(self, "search_input")
            else ""
        )

        for f in self.files:
            if f.status == FileStatus.UPTODATE:
                continue
            if self.current_filter == "new" and f.status != FileStatus.NEW:
                continue
            if self.current_filter == "modified" and f.status != FileStatus.MODIFIED:
                continue
            if self.current_filter == "deleted" and f.status != FileStatus.DELETED:
                continue
            if search_term and search_term not in f.relative_path.lower():
                continue

            select_mark = "☑" if f.selected else "☐"
            loc_t = f.local_mtime.strftime("%d/%m/%y %H:%M") if f.local_mtime else "—"
            rem_t = f.remote_mtime.strftime("%d/%m/%y %H:%M") if f.remote_mtime else "—"

            item = QTreeWidgetItem(
                [
                    select_mark,
                    f.status.value,
                    f.relative_path,
                    f.size_display,
                    loc_t,
                    rem_t,
                ]
            )

            if f.status == FileStatus.NEW:
                for col in range(6):
                    item.setForeground(col, QColor(COLORS["new_file"]))
            elif f.status == FileStatus.DELETED:
                for col in range(6):
                    item.setForeground(col, QColor(COLORS["deleted_file"]))
            else:
                for col in range(6):
                    item.setForeground(col, QColor(COLORS["modified_file"]))

            self.file_tree.addTopLevelItem(item)

        self.btn_deploy.setEnabled(
            any(f.selected and f.status != FileStatus.UPTODATE for f in self.files)
        )

    def update_stats(self):
        total = len(self.files)
        new_c = sum(1 for f in self.files if f.status == FileStatus.NEW)
        mod_c = sum(1 for f in self.files if f.status == FileStatus.MODIFIED)
        del_c = sum(1 for f in self.files if f.status == FileStatus.DELETED)
        up_c = sum(1 for f in self.files if f.status == FileStatus.UPTODATE)
        self.signals.update_stats.emit(total, new_c, mod_c, del_c, up_c)

    # ----------------------------------------------------------------
    # HISTORY
    # ----------------------------------------------------------------
    def refresh_history(self):
        self.hist_tree.clear()
        deployments = self.history.get_deployments()
        for dep in deployments:
            try:
                dt = datetime.fromisoformat(dep["timestamp"])
                date_str = dt.strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                date_str = dep["timestamp"]

            status_display = {
                "success": tr("hist_status_success"),
                "partial": tr("hist_status_partial"),
                "failed": tr("hist_status_failed"),
                "in_progress": tr("hist_status_ip"),
            }.get(dep["status"], dep["status"])

            duration = (
                f"{dep['duration_seconds']:.1f}s" if dep["duration_seconds"] else "—"
            )

            item = QTreeWidgetItem(
                [
                    dep["version"],
                    date_str,
                    status_display,
                    str(dep["total_files"]),
                    str(dep["success_count"]),
                    str(dep["error_count"]),
                    duration,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, dep["id"])

            # Color by status
            color_map = {
                "success": COLORS["success"],
                "partial": COLORS["warning"],
                "failed": COLORS["error"],
            }
            if dep["status"] in color_map:
                for col in range(7):
                    item.setForeground(col, QColor(color_map[dep["status"]]))

            self.hist_tree.addTopLevelItem(item)

        if hasattr(self, "version_label"):
            self._update_version_label()

    def show_deployment_detail(self, item, column=None):
        dep_id = item.data(0, Qt.ItemDataRole.UserRole)
        if dep_id is None:
            return
        files = self.history.get_deployment_files(dep_id)
        if not files:
            QMessageBox.information(
                self, tr("msg_info_title"), tr("msg_no_hist_files")
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("dlg_hist_title", id=dep_id))
        dlg.resize(750, 500)
        dlg.setStyleSheet(STYLESHEET)
        layout = QVBoxLayout(dlg)

        title = QLabel(tr("dlg_hist_header", id=dep_id, count=len(files)))
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        detail = QTextEdit()
        detail.setReadOnly(True)
        for f_rec in files:
            icon = "✅" if f_rec["result"] == "success" else "❌"
            status_icon = {"new": "🆕", "modified": "📝", "deleted": "🗑"}.get(
                f_rec["file_status"], "📝"
            )
            size_kb = f_rec["file_size"] / 1024 if f_rec["file_size"] else 0
            line = f"{icon} {status_icon} {f_rec['file_path']}  ({size_kb:.1f} Ko)"
            color = (
                COLORS["success"] if f_rec["result"] == "success" else COLORS["error"]
            )
            detail.append(f'<span style="color:{color}">{line}</span>')
            if f_rec["error_message"]:
                detail.append(
                    f'<span style="color:{COLORS["warning"]}">     ⚠ {f_rec["error_message"]}</span>'
                )
        layout.addWidget(detail)
        dlg.exec()

    def export_history_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_export_hist"), "", "CSV (*.csv)"
        )
        if not file_path:
            return
        deployments = self.history.get_deployments(limit=1000)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(tr("csv_header"))
                for dep in deployments:
                    f.write(
                        f"{dep['version']},{dep['timestamp']},{dep['status']},"
                        f"{dep['total_files']},{dep['success_count']},{dep['error_count']},"
                        f"{dep['duration_seconds']},{dep['local_dir']},{dep['remote_dir']}\n"
                    )
            QMessageBox.information(
                self, "Export", tr("msg_export_hist_success", path=file_path)
            )
        except Exception as e:
            QMessageBox.critical(self, tr("msg_err_title"), tr("msg_export_fail", err=e))

    # ----------------------------------------------------------------
    # CHANGELOG
    # ----------------------------------------------------------------
    def refresh_changelog(self):
        self.changelog_tree.clear()
        entries = self.history.get_changelogs()
        for entry in entries:
            try:
                dt = datetime.fromisoformat(entry["timestamp"])
                date_str = dt.strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                date_str = entry["timestamp"]

            total_changes = (
                entry["added_count"] + entry["modified_count"] + entry["deleted_count"]
            )
            result = (
                f"✅ {entry['success_count']}/{total_changes}"
                if entry["error_count"] == 0
                else f"⚠ {entry['success_count']}/{total_changes}"
            )
            duration = (
                f"{entry['duration_seconds']:.1f}s"
                if entry["duration_seconds"]
                else "—"
            )

            item = QTreeWidgetItem(
                [
                    entry["version"],
                    date_str,
                    str(entry["added_count"]),
                    str(entry["modified_count"]),
                    str(entry["deleted_count"]),
                    result,
                    duration,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry["id"])

            # Color counts
            item.setForeground(2, QColor(COLORS["new_file"]))
            item.setForeground(3, QColor(COLORS["modified_file"]))
            item.setForeground(4, QColor(COLORS["deleted_file"]))
            if entry["error_count"] > 0:
                item.setForeground(5, QColor(COLORS["warning"]))
            else:
                item.setForeground(5, QColor(COLORS["success"]))

            self.changelog_tree.addTopLevelItem(item)

    def show_changelog_detail(self, item, column=None):
        cl_id = item.data(0, Qt.ItemDataRole.UserRole)
        if cl_id is None:
            return
        version = item.text(0)
        date_str = item.text(1)
        files = self.history.get_changelog_files(cl_id)
        if not files:
            QMessageBox.information(
                self, tr("msg_info_title"), tr("msg_no_cl_files")
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("dlg_cl_title", version=version))
        dlg.resize(800, 550)
        dlg.setStyleSheet(STYLESHEET)
        layout = QVBoxLayout(dlg)

        # Header
        header_lbl = QLabel(tr("dlg_cl_header", version=version, date=date_str))
        header_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(header_lbl)

        # Stats
        added = [f for f in files if f["change_type"] == "added"]
        modified = [f for f in files if f["change_type"] == "modified"]
        deleted = [f for f in files if f["change_type"] == "deleted"]

        stats_lbl = QLabel(
            tr("dlg_cl_stats", add=len(added), mod=len(modified), del_c=len(deleted))
        )
        stats_lbl.setFont(QFont("Segoe UI", 13))
        stats_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; padding: 4px 0;")
        layout.addWidget(stats_lbl)

        detail = QTextEdit()
        detail.setReadOnly(True)

        if added:
            detail.append(
                f'<span style="color:{COLORS["accent_cyan"]}; font-size:15px; font-weight:bold;">{tr("dlg_cl_added")}</span>'
            )
            detail.append("")
            for f_rec in added:
                detail.append(
                    f'<span style="color:{COLORS["new_file"]};">  + {f_rec["file_path"]}</span>'
                )
            detail.append("")

        if modified:
            detail.append(
                f'<span style="color:{COLORS["accent_cyan"]}; font-size:15px; font-weight:bold;">{tr("dlg_cl_modified")}</span>'
            )
            detail.append("")
            for f_rec in modified:
                detail.append(
                    f'<span style="color:{COLORS["modified_file"]};">  ~ {f_rec["file_path"]}</span>'
                )
            detail.append("")

        if deleted:
            detail.append(
                f'<span style="color:{COLORS["accent_cyan"]}; font-size:15px; font-weight:bold;">{tr("dlg_cl_deleted")}</span>'
            )
            detail.append("")
            for f_rec in deleted:
                detail.append(
                    f'<span style="color:{COLORS["deleted_file"]};">  - {f_rec["file_path"]}</span>'
                )

        layout.addWidget(detail)
        dlg.exec()

    def export_changelog_md(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_export_cl"), "CHANGELOG.md", "Markdown (*.md)"
        )
        if not file_path:
            return

        entries = self.history.get_changelogs(limit=1000)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# 📋 Changelog\n\n")
                f.write(tr("changelog_desc") + "\n\n")

                for entry in entries:
                    try:
                        dt = datetime.fromisoformat(entry["timestamp"])
                        date_str = dt.strftime(tr("date_format_long"))
                        date_short = dt.strftime("%Y-%m-%d")
                    except Exception:
                        date_str = entry["timestamp"]
                        date_short = entry["timestamp"]

                    f.write(f"## [{entry['version']}] - {date_short}\n\n")
                    f.write(
                        f"> {tr('log_deployed_on')} {date_str} — "
                        f"✅ {entry['success_count']} {tr('stat_success').lower()}(s), "
                        f"❌ {entry['error_count']} {tr('stat_errors').lower()}(s), "
                        f"⏱ {entry['duration_seconds']:.1f}s\n\n"
                    )

                    files = self.history.get_changelog_files(entry["id"])
                    added = [fi for fi in files if fi["change_type"] == "added"]
                    modified = [fi for fi in files if fi["change_type"] == "modified"]
                    deleted = [fi for fi in files if fi["change_type"] == "deleted"]

                    if added:
                        f.write(f"### {tr('dlg_cl_added')}\n\n")
                        for fi in added:
                            f.write(f"- `{fi['file_path']}`\n")
                        f.write("\n")

                    if modified:
                        f.write(f"### {tr('dlg_cl_modified')}\n\n")
                        for fi in modified:
                            f.write(f"- `{fi['file_path']}`\n")
                        f.write("\n")

                    if deleted:
                        f.write(f"### {tr('dlg_cl_deleted')}\n\n")
                        for fi in deleted:
                            f.write(f"- `{fi['file_path']}`\n")
                        f.write("\n")

                    f.write("---\n\n")

            QMessageBox.information(
                self, "Export", tr("msg_export_cl_success", path=file_path)
            )
        except Exception as e:
            QMessageBox.critical(self, tr("msg_err_title"), tr("msg_export_fail", err=e))

    # ----------------------------------------------------------------
    # SCAN LOGIC
    # ----------------------------------------------------------------
    def start_scan(self):
        loc = self.local_dir_input.text()
        if not os.path.isdir(loc):
            return QMessageBox.critical(self, tr("msg_err_title"), tr("err_local_invalid"))
        method = self.config.get("deploy_method", "smb")
        rem = self.config.get("ssh_remote_dir", "") if method == "ssh" else self.remote_dir_input.text()

        if method == "smb" and not rem.startswith("\\\\"):
            r = QMessageBox.question(
                self,
                tr("msg_warn_title"),
                tr("warn_smb_path", path=rem),
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        self.files.clear()
        self.refresh_treeview()
        self.signals.ui_state.emit(False)
        self.tabs.setCurrentIndex(0)

        use_hash = self.chk_hash.isChecked()
        ignores = self.config.get("ignore_patterns", [])
        ssh_cfg = (
            {
                "host": self.ssh_host_input.text().strip(),
                "port": self.ssh_port_input.text().strip() or "22",
                "user": self.ssh_user_input.text().strip(),
                "password": self.ssh_pw_input.text().strip(),
                "key_path": self.ssh_key_input.text().strip(),
            }
            if method == "ssh"
            else None
        )

        threading.Thread(
            target=self._scan_process,
            args=(loc, rem, use_hash, method, ignores, ssh_cfg),
            daemon=True,
        ).start()

    def _scan_process(
        self, local_dir, remote_dir, use_hash, method, ignore_patterns, ssh_cfg
    ):
        self.log("━" * 50, "header")
        self.log(tr("log_scan_start", method=method.upper()), "header")
        self.log("━" * 50, "header")
        self.log(tr("log_scan_local", path=local_dir), "info")
        self.log(tr("log_scan_remote", path=remote_dir), "info")
        self.signals.status.emit("Analyse en cours...")

        ssh_deployer = None
        if method == "ssh":
            self.log(tr("log_ssh_connecting", host=ssh_cfg['host']), "info")
            try:
                ssh_deployer = SSHDeployer(**ssh_cfg)
                ssh_deployer.connect()
                self.log(tr("log_ssh_connected"), "success")
            except Exception as e:
                self.log(tr("log_ssh_error", err=e), "error")
                self.signals.ui_state.emit(True)
                self.signals.status.emit(tr("log_ssh_fail"))
                return

        def is_ignored(name):
            for pat in ignore_patterns:
                if fnmatch.fnmatch(name, pat):
                    return True
            return False

        all_files = []
        for root, dirs, files in os.walk(local_dir):
            dirs[:] = [d for d in dirs if not is_ignored(d)]
            for file in files:
                if not is_ignored(file):
                    all_files.append(os.path.join(root, file))

        total = len(all_files)
        self.log(f"📂 {tr('log_files_found', count=total)}", "info")

        def scan_one(local_path):
            rel_path = os.path.relpath(local_path, local_dir)

            if method == "ssh":
                remote_path = remote_dir + "/" + rel_path.replace("\\", "/")
                status = ssh_deployer.compare_file(local_path, remote_path, use_hash)
                try:
                    rm_stat = ssh_deployer.sftp.stat(remote_path)
                    r_size = rm_stat.st_size
                    r_mtime = datetime.fromtimestamp(rm_stat.st_mtime)
                except IOError:
                    r_size = None
                    r_mtime = None
            else:
                remote_path = os.path.join(remote_dir, rel_path)
                status = FileComparator.compare_files(local_path, remote_path, use_hash)
                r_size = (
                    os.path.getsize(remote_path)
                    if os.path.exists(remote_path)
                    else None
                )
                r_mtime = (
                    datetime.fromtimestamp(os.path.getmtime(remote_path))
                    if os.path.exists(remote_path)
                    else None
                )

            return FileInfo(
                relative_path=rel_path,
                local_path=local_path,
                remote_path=remote_path,
                status=status,
                local_size=os.path.getsize(local_path),
                remote_size=r_size,
                local_mtime=datetime.fromtimestamp(os.path.getmtime(local_path)),
                remote_mtime=r_mtime,
                selected=(status != FileStatus.UPTODATE),
            )

        completed = 0
        max_workers = 1 if method == "ssh" else min(8, max(1, os.cpu_count() or 4))
        self.log(f"⚡ {tr('log_threads', count=max_workers)}", "info")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(scan_one, fp): fp for fp in all_files}
            for future in as_completed(futures):
                completed += 1
                try:
                    f_info = future.result()
                    self.files.append(f_info)
                    if f_info.status != FileStatus.UPTODATE:
                        icon = "🆕" if f_info.status == FileStatus.NEW else "📝"
                        self.log(
                            f"  {icon} [{f_info.status_value}] {f_info.relative_path}",
                            "success" if f_info.status == FileStatus.NEW else "warning",
                        )
                except Exception as e:
                    self.log(tr("log_scan_err", err=e), "error")
                self.signals.progress.emit(completed / total if total > 0 else 1)

        # --- Detect deleted files (exist on server but not locally) ---
        self.log(tr("log_search_deleted"), "info")
        if method == "ssh":
            remote_files_list = ssh_deployer.list_remote_files(
                remote_dir, ignore_patterns
            )
            for rm_path, rm_size, rm_mtime in remote_files_list:
                rel_path = posixpath.relpath(rm_path, remote_dir)
                local_path = os.path.join(local_dir, os.path.normpath(rel_path))
                if not os.path.exists(local_path):
                    f_del = FileInfo(
                        relative_path=os.path.normpath(rel_path),
                        local_path=local_path,
                        remote_path=rm_path,
                        status=FileStatus.DELETED,
                        local_size=0,
                        remote_size=rm_size,
                        local_mtime=None,
                        remote_mtime=datetime.fromtimestamp(rm_mtime),
                        selected=True,
                    )
                    self.files.append(f_del)
                    self.log(tr("log_deleted_file", file=f_del.relative_path), "error")
        else:
            if os.path.isdir(remote_dir):
                for root, dirs, files in os.walk(remote_dir):
                    dirs[:] = [d for d in dirs if not is_ignored(d)]
                    for file in files:
                        if file == VERSION_FILENAME or is_ignored(file):
                            continue
                        remote_path = os.path.join(root, file)
                        rel_path = os.path.relpath(remote_path, remote_dir)
                        local_path = os.path.join(local_dir, rel_path)
                        if not os.path.exists(local_path):
                            try:
                                remote_size = os.path.getsize(remote_path)
                                remote_mtime = datetime.fromtimestamp(
                                    os.path.getmtime(remote_path)
                                )
                            except (IOError, OSError):
                                remote_size = 0
                                remote_mtime = None
                            f_del = FileInfo(
                                relative_path=rel_path,
                                local_path=local_path,
                                remote_path=remote_path,
                                status=FileStatus.DELETED,
                                local_size=0,
                                remote_size=remote_size,
                                local_mtime=None,
                                remote_mtime=remote_mtime,
                                selected=True,
                            )
                            self.files.append(f_del)
                            self.log(tr("log_deleted_file", file=rel_path), "error")

        if ssh_deployer:
            ssh_deployer.disconnect()

        new_c = sum(1 for f in self.files if f.status == FileStatus.NEW)
        mod_c = sum(1 for f in self.files if f.status == FileStatus.MODIFIED)
        del_c = sum(1 for f in self.files if f.status == FileStatus.DELETED)
        up_c = sum(1 for f in self.files if f.status == FileStatus.UPTODATE)

        self.log("", "info")
        self.log(
            tr("log_scan_done", new=new_c, mod=mod_c, del_c=del_c, upd=up_c),
            "success",
        )
        self.update_stats()
        self.signals.refresh_tree.emit()
        self.signals.status.emit(
            tr("status_scan_ready", count=new_c + mod_c + del_c)
        )
        self.signals.ui_state.emit(True)
        self.signals.progress.emit(0)

    # ----------------------------------------------------------------
    # DEPLOY LOGIC
    # ----------------------------------------------------------------
    def start_deploy(self):
        to_deploy = [
            f for f in self.files if f.selected and f.status != FileStatus.UPTODATE
        ]
        if not to_deploy:
            return QMessageBox.information(self, tr("msg_info_title"), tr("msg_no_file_selected"))

        to_copy = [f for f in to_deploy if f.status != FileStatus.DELETED]
        to_delete = [f for f in to_deploy if f.status == FileStatus.DELETED]

        total_size = sum(f.local_size for f in to_copy)
        size_display = (
            f"{total_size / 1024:.1f} Ko"
            if total_size < 1048576
            else f"{total_size / 1048576:.1f} Mo"
        )
        new_c = sum(1 for f in to_copy if f.status == FileStatus.NEW)
        mod_c = sum(1 for f in to_copy if f.status == FileStatus.MODIFIED)
        del_c = len(to_delete)

        method = self.config.get("deploy_method", "smb")
        method_name = method.upper()

        remote_dir = self.config.get("ssh_remote_dir", "") if method == "ssh" else self.remote_dir_input.text()

        msg = tr("confirm_deploy_msg",
            count=len(to_deploy),
            method=method_name,
            new=new_c,
            mod=mod_c,
            del_c=del_c,
            size=size_display,
            dest=remote_dir
        )
        r = QMessageBox.question(self, tr("msg_confirm_title"), msg)
        if r != QMessageBox.StandardButton.Yes:
            return

        self.signals.ui_state.emit(False)
        self.tabs.setCurrentIndex(1)

        ssh_cfg = (
            {
                "host": self.ssh_host_input.text().strip(),
                "port": self.ssh_port_input.text().strip() or "22",
                "user": self.ssh_user_input.text().strip(),
                "password": self.ssh_pw_input.text().strip(),
                "key_path": self.ssh_key_input.text().strip(),
            }
            if method == "ssh"
            else None
        )

        threading.Thread(
            target=self._deploy_process,
            args=(
                to_deploy,
                remote_dir,
                self.chk_backup.isChecked(),
                method,
                ssh_cfg,
            ),
            daemon=True,
        ).start()

    def _deploy_process(self, to_deploy, remote_dir, do_backup, method, ssh_cfg):
        start_time = time.time()
        local_dir = self.local_dir_input.text()

        # Bump PATCH version
        current_ver = self.version_mgr.read_version(local_dir)
        new_ver = (current_ver[0], current_ver[1], current_ver[2] + 1)
        deploy_version = f"v{new_ver[0]}.{new_ver[1]}.{new_ver[2]}"
        prev_version_str = f"v{current_ver[0]}.{current_ver[1]}.{current_ver[2]}"

        deployment_id = self.history.create_deployment(
            deploy_version, local_dir, remote_dir
        )

        self.signals.status.emit(tr("status_deploy_in_progress", version=deploy_version))
        self.log("━" * 50, "header")
        self.log(f"  {tr('btn_deploy').upper()} {deploy_version} ({method.upper()})", "header")
        self.log("━" * 50, "header")

        ssh_deployer = None
        if method == "ssh":
            self.log(tr("log_ssh_connecting", host=ssh_cfg['host']), "info")
            try:
                ssh_deployer = SSHDeployer(**ssh_cfg)
                ssh_deployer.connect()
                self.log(tr("log_ssh_connected"), "success")
            except Exception as e:
                self.log(tr("log_ssh_error", err=e), "error")
                self.log(tr("log_deploy_cancel"), "error")
                self.history.finalize_deployment(
                    deployment_id, 0, 0, 1, time.time() - start_time
                )
                self.signals.refresh_history.emit()
                return self._deploy_cleanup()

        # --- BACKUP ---
        if do_backup:
            if method == "ssh":
                b_path = f"{remote_dir.rstrip('/')}_backup_{prev_version_str}_{datetime.now().strftime('%Y-%m-%d_%Hh%Mm%Ss')}"
            else:
                b_path = os.path.join(
                    os.path.dirname(remote_dir),
                    f"backup_{prev_version_str}_{datetime.now().strftime('%Y-%m-%d_%Hh%Mm%Ss')}",
                )

            # Check existance first
            exists = False
            if method == "ssh":
                try:
                    ssh_deployer.sftp.stat(remote_dir)
                    exists = True
                except IOError:
                    exists = False
            else:
                exists = os.path.exists(remote_dir)

            if exists:
                self.log(tr("log_create_backup", path=b_path), "info")
                try:
                    if method == "ssh":
                        exit_code, out, err = ssh_deployer.execute_command(
                            f'xcopy "{remote_dir}" "{b_path}\\" /E /I /H /Y /Q'
                        )
                        if exit_code == 0:
                            self.log(tr("log_backup_ssh_ok"), "success")
                        else:
                            raise Exception(f"Exit code {exit_code}, {err}")
                    else:
                        shutil.copytree(remote_dir, b_path)
                        self.log(tr("log_backup_ok"), "success")
                except Exception as e:
                    self.log(tr("log_backup_err", err=e), "error")
                    self.log(tr("log_deploy_cancel"), "error")
                    duration = time.time() - start_time
                    self.history.finalize_deployment(deployment_id, 0, 0, 1, duration)
                    self.signals.refresh_history.emit()
                    if ssh_deployer:
                        ssh_deployer.disconnect()
                    return self._deploy_cleanup()

        # --- FILE COPY (multi-thread) ---
        total = len(to_deploy)
        success_count = 0
        error_count = 0
        count_lock = threading.Lock()
        completed = 0

        max_workers = 1 if method == "ssh" else min(4, max(1, os.cpu_count() or 2))
        self.log(f"\n⚡ Copie de {total} fichiers ({max_workers} threads)...\n", "info")

        def deploy_one(f):
            if f.status == FileStatus.DELETED:
                # Delete file from server
                if method == "ssh":
                    try:
                        ssh_deployer.delete_file(f.remote_path)
                    except Exception:
                        pass
                else:
                    if os.path.exists(f.remote_path):
                        os.remove(f.remote_path)
                        # Clean up empty parent directories
                        parent = os.path.dirname(f.remote_path)
                        try:
                            while parent and parent != remote_dir:
                                if os.path.isdir(parent) and not os.listdir(parent):
                                    os.rmdir(parent)
                                    parent = os.path.dirname(parent)
                                else:
                                    break
                        except (IOError, OSError):
                            pass
                return f
            else:
                if method == "ssh":
                    ssh_deployer.upload_file(f.local_path, f.remote_path)
                else:
                    dest_dir = os.path.dirname(f.remote_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    tmp_path = f.remote_path + ".tmp"
                    shutil.copy2(f.local_path, tmp_path)
                    copied_size = os.path.getsize(tmp_path)
                    if copied_size != f.local_size:
                        os.remove(tmp_path)
                        raise IOError(
                            tr("err_size_mismatch", copied=copied_size, local=f.local_size)
                        )
                    if os.path.exists(f.remote_path):
                        os.replace(tmp_path, f.remote_path)
                    else:
                        os.rename(tmp_path, f.remote_path)
                return f

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(deploy_one, f): f for f in to_deploy}
            for future in as_completed(futures):
                f = futures[future]
                completed += 1
                try:
                    future.result()
                    if f.status == FileStatus.DELETED:
                        self.log(
                            f"  🗑 {f.relative_path} {tr('log_deleted_from_server')}", "warning"
                        )
                    else:
                        icon = "🆕" if f.status == FileStatus.NEW else "📝"
                        self.log(
                            f"  ✅ {icon} {f.relative_path} ({f.size_display})",
                            "success",
                        )
                    with count_lock:
                        success_count += 1
                    status_label = {
                        FileStatus.NEW: "new",
                        FileStatus.MODIFIED: "modified",
                        FileStatus.DELETED: "deleted",
                    }.get(f.status, "modified")
                    self.history.add_file_record(
                        deployment_id,
                        f.relative_path,
                        status_label,
                        (
                            f.local_size
                            if f.status != FileStatus.DELETED
                            else (f.remote_size or 0)
                        ),
                        "success",
                    )
                except Exception as e:
                    self.log(f"  ❌ {f.relative_path} : {e}", "error")
                    with count_lock:
                        error_count += 1
                    status_label = {
                        FileStatus.NEW: "new",
                        FileStatus.MODIFIED: "modified",
                        FileStatus.DELETED: "deleted",
                    }.get(f.status, "modified")
                    self.history.add_file_record(
                        deployment_id,
                        f.relative_path,
                        status_label,
                        (
                            f.local_size
                            if f.status != FileStatus.DELETED
                            else (f.remote_size or 0)
                        ),
                        "error",
                        str(e),
                    )
                    if f.status != FileStatus.DELETED and method != "ssh":
                        tmp_path = f.remote_path + ".tmp"
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass
                self.signals.progress.emit(completed / total if total else 1)

        # --- SUMMARY ---
        duration = time.time() - start_time
        self.history.finalize_deployment(
            deployment_id, total, success_count, error_count, duration
        )

        self.log("", "info")
        self.log("━" * 50, "header")
        if error_count == 0:
            self.log(
                tr("log_deploy_success", version=deploy_version), "success"
            )
        else:
            self.log(
                tr("log_deploy_partial", version=deploy_version), "warning"
            )
        self.log(
            tr("log_deploy_stats", success=success_count, err=error_count, duration=duration),
            "info",
        )
        self.log("━" * 50, "header")

        # --- WRITE VERSION ---
        self.version_mgr.write_version(local_dir, new_ver)
        self.version_mgr.write_version(remote_dir, new_ver)
        self.log(
            f"🏷 {tr('log_version_bumped')} {new_ver[0]}.{new_ver[1]}.{new_ver[2]} {tr('log_written_both')}",
            "info",
        )

        # --- GENERATE CHANGELOG ---
        self._generate_changelog(
            local_dir,
            remote_dir,
            deploy_version,
            to_deploy,
            success_count,
            error_count,
            duration,
            method,
            ssh_deployer,
        )

        if ssh_deployer:
            ssh_deployer.disconnect()

        self.files.clear()
        self.signals.refresh_tree.emit()
        self.signals.refresh_history.emit()
        self.signals.update_stats.emit(0, 0, 0, 0, 0)
        self._deploy_cleanup()

    def _deploy_cleanup(self):
        self.signals.ui_state.emit(True)
        self.signals.status.emit(tr("status_ready"))
        self.signals.progress.emit(0)

    def _generate_changelog(
        self,
        local_dir,
        remote_dir,
        version,
        deployed_files,
        success_count,
        error_count,
        duration,
        method="smb",
        ssh_deployer=None,
    ):
        """Generates / updates CHANGELOG.md in local and server folders + SQLite."""
        now = datetime.now()
        date_str = now.strftime(tr("date_format_long"))

        # Categorize files
        added = [f for f in deployed_files if f.status == FileStatus.NEW]
        modified = [f for f in deployed_files if f.status == FileStatus.MODIFIED]
        deleted = [f for f in deployed_files if f.status == FileStatus.DELETED]

        # --- Save to SQLite ---
        try:
            self.history.save_changelog(
                version=version,
                timestamp=now.isoformat(),
                added_files=[f.relative_path for f in added],
                modified_files=[f.relative_path for f in modified],
                deleted_files=[f.relative_path for f in deleted],
                success_count=success_count,
                error_count=error_count,
                duration=duration,
            )
            self.log(tr("log_changelog_saved"), "success")
            self.signals.refresh_history.emit()  # will also refresh changelog tab
        except Exception as e:
            self.log(tr("err_changelog_sqlite", err=e), "warning")

        # Build markdown entry
        lines = []
        lines.append(f"## [{version}] - {now.strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append(
            f"> " + tr("log_deploy_stats", success=success_count, err=error_count, duration=duration)
        )
        lines.append("")

        if added:
            lines.append(f"### {tr('dlg_cl_added')}")
            lines.append("")
            for f in sorted(added, key=lambda x: x.relative_path):
                lines.append(f"- `{f.relative_path}`")
            lines.append("")

        if modified:
            lines.append(f"### {tr('dlg_cl_modified')}")
            lines.append("")
            for f in sorted(modified, key=lambda x: x.relative_path):
                lines.append(f"- `{f.relative_path}`")
            lines.append("")

        if deleted:
            lines.append(f"### {tr('dlg_cl_deleted')}")
            lines.append("")
            for f in sorted(deleted, key=lambda x: x.relative_path):
                lines.append(f"- `{f.relative_path}`")
            lines.append("")

        lines.append("---")
        lines.append("")
        new_entry = "\n".join(lines)

        # Write to both local and remote
        dirs_to_write = [(local_dir, "smb")]
        if method == "smb":
            dirs_to_write.append((remote_dir, "smb"))
        else:
            dirs_to_write.append((remote_dir, "ssh"))

        for directory, dir_method in dirs_to_write:
            try:
                if dir_method == "ssh":
                    changelog_path = directory + "/CHANGELOG.md"
                    existing = ""
                    try:
                        with ssh_deployer.sftp.file(changelog_path, "r") as f:
                            existing = f.read().decode("utf-8")
                    except IOError:
                        pass
                else:
                    changelog_path = os.path.join(directory, "CHANGELOG.md")
                    existing = ""
                    if os.path.isfile(changelog_path):
                        with open(changelog_path, "r", encoding="utf-8") as f:
                            existing = f.read()

                # If file doesn't have a header yet, add one
                if not existing.strip():
                    header = f"# 📋 Changelog\n\n{tr('changelog_desc')}\n\n"
                    content = header + new_entry
                else:
                    # Insert after the header (first two lines: # title + blank)
                    # Find position after the header block
                    marker = "\n---\n"
                    # Find first ## or --- to know where entries start
                    header_end = 0
                    for i, line in enumerate(existing.split("\n")):
                        if line.startswith("## ["):
                            header_end = sum(
                                len(l) + 1 for l in existing.split("\n")[:i]
                            )
                            break
                        if line.startswith("---") and i > 0:
                            header_end = sum(
                                len(l) + 1 for l in existing.split("\n")[:i]
                            )
                            break
                    if header_end == 0:
                        # Fallback
                        header_end = existing.find("\n\n") + 2

                    content = (
                        existing[:header_end].rstrip()
                        + "\n\n"
                        + new_entry
                        + existing[header_end:].lstrip()
                    )

                if dir_method == "ssh":
                    with ssh_deployer.sftp.file(changelog_path, "w") as f:
                        f.write(content.encode("utf-8"))
                else:
                    with open(changelog_path, "w", encoding="utf-8") as f:
                        f.write(content)
            except Exception as e:
                self.log(tr("err_changelog_write", dir=directory, err=e), "warning")

    # ----------------------------------------------------------------
    # CLOSE
    # ----------------------------------------------------------------
    def closeEvent(self, event):
        self.config.update(
            {
                "local_dir": self.local_dir_input.text(),
                "remote_dir": self.remote_dir_input.text(),
                "use_hash_comparison": self.chk_hash.isChecked(),
                "auto_backup": self.chk_backup.isChecked(),
                "ssh_host": self.ssh_host_input.text(),
                "ssh_user": self.ssh_user_input.text(),
                "ssh_password": self.ssh_pw_input.text(),
                "ssh_port": int(self.ssh_port_input.text() or 22),
                "ssh_key_path": self.ssh_key_input.text(),
            }
        )
        ConfigManager.save(self.config)
        event.accept()


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    icon_path = str(APP_DIR / "icon.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = DeployAppSMB()
    window.show()
    sys.exit(app.exec())
