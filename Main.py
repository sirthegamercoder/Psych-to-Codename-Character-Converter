import sys
import os
import json
import re
from typing import Dict, List, Optional, Any, Tuple

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QLabel,
    QGroupBox,
    QGridLayout,
    QProgressBar,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QSplitter,
    QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QMutex, QMutexLocker
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QAction
from PySide6.QtCore import QSettings

from lxml import etree
import webbrowser

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class ConversionWorker(QThread):
    finished = Signal(dict, str)
    error = Signal(str, str)
    progress = Signal(str, str)

    def __init__(self, xml_content: str, input_path: str, output_path: str = None):
        super().__init__()
        self.xml_content = xml_content
        self.input_path = input_path
        self.output_path = output_path

    def run(self):
        try:
            self.progress.emit(f"Parsing XML file...", self.input_path)
            result = self.convert_to_psych(self.xml_content)

            if result:
                if self.output_path:
                    self.progress.emit(f"Saving to {self.output_path}...", self.input_path)
                    with open(self.output_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    self.progress.emit(f"Completed: {os.path.basename(self.input_path)}", self.input_path)
                self.finished.emit(result, self.output_path)
            else:
                self.error.emit("Failed to convert XML to Psych format", self.input_path)
        except Exception as e:
            self.error.emit(f"Conversion error: {str(e)}", self.input_path)

    def get_float_att(self, element, name: str, default: float) -> float:
        value = element.get(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    def get_string_att(self, element, name: str, default: str) -> str:
        return element.get(name, default)

    def get_bool_att(self, element, name: str, default: bool) -> bool:
        value = element.get(name)
        if value is None:
            return default
        return value.lower() in ["true", "1", "yes"]

    def parse_indices(self, indices_str: str) -> List[int]:
        result = []

        if not indices_str:
            return result

        if ".." in indices_str:
            parts = indices_str.split("..")
            if len(parts) == 2:
                try:
                    start = int(parts[0].strip())
                    end = int(parts[1].strip())
                    result.extend(range(start, end + 1))
                except ValueError:
                    pass
        elif "," in indices_str:
            parts = indices_str.split(",")
            for part in parts:
                try:
                    num = int(part.strip())
                    result.append(num)
                except ValueError:
                    pass
        else:
            try:
                num = int(indices_str.strip())
                result.append(num)
            except ValueError:
                pass

        return result

    def hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")

        if len(hex_color) == 3:
            hex_color = "".join([c * 2 for c in hex_color])

        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r, g, b)
        except (ValueError, IndexError):
            return (161, 161, 161)

    def convert_to_psych(self, xml_content: str) -> Optional[Dict[str, Any]]:
        try:
            root = etree.fromstring(xml_content.encode("utf-8"))

            if root.tag != "character":
                self.error.emit(
                    "Invalid Codename Engine character XML: root element must be 'character'",
                    self.input_path
                )
                return None

            char_data = {
                "x": self.get_float_att(root, "x", 0),
                "y": self.get_float_att(root, "y", 0),
                "sprite": self.get_string_att(root, "sprite", "characters/BOYFRIEND"),
                "scale": self.get_float_att(root, "scale", 1),
                "camx": self.get_float_att(root, "camx", 0),
                "camy": self.get_float_att(root, "camy", 0),
                "icon": self.get_string_att(root, "icon", "face"),
                "holdTime": self.get_float_att(root, "holdTime", 4),
                "isGF": self.get_bool_att(root, "isGF", False),
                "flipX": self.get_bool_att(root, "flipX", False),
                "animations": [],
            }

            color_hex = self.get_string_att(root, "color", "#A1A1A1")
            rgb_color = self.hex_to_rgb(color_hex)

            for anim_node in root.findall("anim"):
                anim_name = self.get_string_att(anim_node, "name", "")
                anim_anim = self.get_string_att(anim_node, "anim", "")
                anim_x = self.get_float_att(anim_node, "x", 0)
                anim_y = self.get_float_att(anim_node, "y", 0)
                anim_fps = int(self.get_float_att(anim_node, "fps", 24))
                anim_loop = self.get_bool_att(anim_node, "loop", False)
                indices_str = self.get_string_att(anim_node, "indices", None)

                char_data["animations"].append(
                    {
                        "name": anim_name,
                        "anim": anim_anim,
                        "x": anim_x,
                        "y": anim_y,
                        "fps": anim_fps,
                        "loop": anim_loop,
                        "indices": indices_str,
                    }
                )

            return self.convert_codename_data(char_data, rgb_color)

        except etree.XMLSyntaxError as e:
            self.error.emit(f"XML parsing error: {str(e)}", self.input_path)
            return None

    def convert_codename_data(
        self, data: Dict, rgb_color: Tuple[int, int, int]
    ) -> Dict[str, Any]:
        psych_anims = []

        for anim in data["animations"]:
            indices = []
            if anim.get("indices"):
                indices = self.parse_indices(anim["indices"])

            psych_anims.append(
                {
                    "anim": anim["name"],
                    "name": anim["anim"],
                    "fps": anim["fps"],
                    "loop": anim["loop"],
                    "indices": indices,
                    "offsets": [int(anim["x"]), int(anim["y"])],
                }
            )

        psych_char = {
            "animations": psych_anims,
            "image": "characters/" + data["sprite"],
            "scale": data["scale"],
            "sing_duration": data["holdTime"],
            "healthicon": data["icon"],
            "position": [data["x"], data["y"]],
            "camera_position": [data["camx"], data["camy"]],
            "flip_x": data["flipX"],
            "no_antialiasing": False,
            "healthbar_colors": list(rgb_color),
            "vocals_file": None,
        }

        return psych_char


class BatchConversionManager(QThread):
    progress_updated = Signal(int, int, str)
    file_completed = Signal(str, bool, str)
    batch_finished = Signal(int, int)
    log_message = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.files_to_process = []
        self.output_directory = ""
        self.is_running = False
        self.mutex = QMutex()

    def setup_batch(self, files: List[Tuple[str, str]], output_dir: str):
        self.files_to_process = files
        self.output_directory = output_dir
        self.is_running = True

    def stop(self):
        with QMutexLocker(self.mutex):
            self.is_running = False

    def run(self):
        success_count = 0
        fail_count = 0
        total = len(self.files_to_process)

        for idx, (input_path, output_path) in enumerate(self.files_to_process):
            if not self.is_running:
                self.log_message.emit("Batch processing stopped by user", "warning")
                break

            self.progress_updated.emit(idx + 1, total, os.path.basename(input_path))
            self.log_message.emit(f"Processing: {os.path.basename(input_path)}", "info")

            try:
                with open(input_path, "r", encoding="utf-8") as f:
                    xml_content = f.read()

                worker = ConversionWorker(xml_content, input_path, output_path)

                worker_finished = False
                worker_success = False
                worker_error_msg = ""

                def on_finished(result, out_path):
                    nonlocal worker_finished, worker_success
                    worker_finished = True
                    worker_success = True

                def on_error(error_msg, in_path):
                    nonlocal worker_finished, worker_success, worker_error_msg
                    worker_finished = True
                    worker_success = False
                    worker_error_msg = error_msg

                worker.finished.connect(on_finished)
                worker.error.connect(on_error)

                worker.run()

                while not worker_finished and self.is_running:
                    self.msleep(10)
                
                if worker_success:
                    success_count += 1
                    self.file_completed.emit(input_path, True, "Successfully converted")
                    self.log_message.emit(f"Success: {os.path.basename(input_path)}", "success")
                else:
                    fail_count += 1
                    self.file_completed.emit(input_path, False, worker_error_msg)
                    self.log_message.emit(f"Failed: {os.path.basename(input_path)} - {worker_error_msg}", "error")
                    
            except Exception as e:
                fail_count += 1
                error_msg = str(e)
                self.file_completed.emit(input_path, False, error_msg)
                self.log_message.emit(f"Error: {os.path.basename(input_path)} - {error_msg}", "error")

            if not self.is_running:
                break

        self.batch_finished.emit(success_count, fail_count)
        self.log_message.emit(f"Batch processing completed: {success_count} succeeded, {fail_count} failed", 
                              "success" if fail_count == 0 else "warning")


class PsychToCodenameConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_xml_path = None
        self.current_json_path = None
        self.current_xml_content = None
        self.batch_files = []
        self.batch_manager = None
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        self.setMinimumSize(950, 700)
        self.resize(950, 700)
        self.center()
        self.create_toolbar()

        xml_icon_path = resource_path("icons/xml.png")
        output_icon_path = resource_path("icons/output.png")
        convert_icon_path = resource_path("icons/convert.png")
        folder_icon_path = resource_path("icons/folder.png")
        clear_icon_path = resource_path("icons/clear.png")
        output_directory_icon_path = resource_path("icons/output-directory.png")
        start_icon_path = resource_path("icons/start.png")
        stop_icon_path = resource_path("icons/stop.png")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel("Psych to Codename Character Converter")
        title_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 5, 0)
        
        single_group = QGroupBox("Single File Conversion")
        single_layout = QVBoxLayout(single_group)

        file_layout = QHBoxLayout()
        self.input_path_label = QLabel("No file selected")
        self.input_path_label.setWordWrap(True)
        self.input_path_label.setStyleSheet("color: #888888;")

        self.select_file_btn = QPushButton("Select XML File")
        self.select_file_btn.clicked.connect(self.select_xml_file)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.select_file_btn.setIcon(QIcon(xml_icon_path))
        else:
            self.select_file_btn.setIcon(QIcon("icons/xml.png"))

        file_layout.addWidget(self.select_file_btn)
        file_layout.addWidget(self.input_path_label, 1)
        single_layout.addLayout(file_layout)

        output_file_layout = QHBoxLayout()
        self.output_path_label = QLabel("No output path selected")
        self.output_path_label.setWordWrap(True)
        self.output_path_label.setStyleSheet("color: #888888;")

        self.select_output_btn = QPushButton("Select Output Path")
        self.select_output_btn.clicked.connect(self.select_output_path)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.select_output_btn.setIcon(QIcon(output_icon_path))
        else:
            self.select_output_btn.setIcon(QIcon("icons/output.png"))

        output_file_layout.addWidget(self.select_output_btn)
        output_file_layout.addWidget(self.output_path_label, 1)
        single_layout.addLayout(output_file_layout)
        
        self.convert_btn = QPushButton("Convert to JSON")
        self.convert_btn.setMinimumHeight(40)
        self.convert_btn.clicked.connect(self.start_conversion)
        convert_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        self.convert_btn.setFont(convert_font)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.convert_btn.setIcon(QIcon(convert_icon_path))
        else:
            self.convert_btn.setIcon(QIcon("icons/convert.png"))
        
        single_layout.addWidget(self.convert_btn)
        
        left_layout.addWidget(single_group)
        left_layout.addStretch()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 0, 0, 0)
        
        batch_group = QGroupBox("Batch Conversion")
        batch_layout = QVBoxLayout(batch_group)

        batch_controls = QHBoxLayout()
        self.add_files_btn = QPushButton("Add XML Files")
        self.add_files_btn.clicked.connect(self.add_batch_files)
        
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.clicked.connect(self.add_batch_folder)
        
        self.clear_files_btn = QPushButton("Clear All")
        self.clear_files_btn.clicked.connect(self.clear_batch_files)
        
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.add_files_btn.setIcon(QIcon(xml_icon_path))
            self.add_folder_btn.setIcon(QIcon(folder_icon_path))
            self.clear_files_btn.setIcon(QIcon(clear_icon_path))
        else:
            self.add_files_btn.setIcon(QIcon("icons/xml.png"))
            self.add_folder_btn.setIcon(QIcon("icons/folder.png"))
            self.clear_files_btn.setIcon(QIcon("icons/clear.png"))
        
        batch_controls.addWidget(self.add_files_btn)
        batch_controls.addWidget(self.add_folder_btn)
        batch_controls.addWidget(self.clear_files_btn)
        batch_controls.addStretch()
        batch_layout.addLayout(batch_controls)

        output_dir_layout = QHBoxLayout()
        self.output_dir_label = QLabel("No output directory selected")
        self.output_dir_label.setWordWrap(True)
        self.output_dir_label.setStyleSheet("color: #888888;")
        
        self.select_output_dir_btn = QPushButton("Select Output Directory")
        self.select_output_dir_btn.clicked.connect(self.select_output_directory)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.select_output_dir_btn.setIcon(QIcon(output_directory_icon_path))
        else:
            self.select_output_dir_btn.setIcon(QIcon("icons/output-directory.png"))
        
        output_dir_layout.addWidget(self.select_output_dir_btn)
        output_dir_layout.addWidget(self.output_dir_label, 1)
        batch_layout.addLayout(output_dir_layout)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list_widget.setAlternatingRowColors(True)
        batch_layout.addWidget(QLabel("Files to convert:"))
        batch_layout.addWidget(self.file_list_widget)

        batch_action_layout = QHBoxLayout()
        self.remove_selected_btn = QPushButton("Remove Selected")
        self.remove_selected_btn.clicked.connect(self.remove_selected_files)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.remove_selected_btn.setIcon(QIcon(clear_icon_path))
        else:
            self.remove_selected_btn.setIcon(QIcon("icons/clear.png"))
        
        self.batch_convert_btn = QPushButton("Start Batch Conversion")
        self.batch_convert_btn.setMinimumHeight(35)
        self.batch_convert_btn.clicked.connect(self.start_batch_conversion)
        batch_convert_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        self.batch_convert_btn.setFont(batch_convert_font)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.batch_convert_btn.setIcon(QIcon(start_icon_path))
        else:
            self.batch_convert_btn.setIcon(QIcon("icons/start.png"))
        
        batch_action_layout.addWidget(self.remove_selected_btn)
        batch_action_layout.addStretch()
        batch_action_layout.addWidget(self.batch_convert_btn)
        batch_layout.addLayout(batch_action_layout)
        
        right_layout.addWidget(batch_group)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 550])
        
        main_layout.addWidget(splitter)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setVisible(False)
        status_layout.addWidget(self.batch_progress_bar)
        
        self.current_file_label = QLabel("")
        self.current_file_label.setVisible(False)
        self.current_file_label.setStyleSheet("color: #FFA500; font-style: italic;")
        status_layout.addWidget(self.current_file_label)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #4CAF50;")
        status_layout.addWidget(self.status_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setPlaceholderText("Conversion log will appear here...")
        status_layout.addWidget(QLabel("Log:"))
        status_layout.addWidget(self.log_text)
        
        main_layout.addWidget(status_group)

        self.single_progress_bar = QProgressBar()
        self.single_progress_bar.setVisible(False)
        main_layout.insertWidget(3, self.single_progress_bar)
        
        self.stop_batch_btn = QPushButton("Stop Batch")
        self.stop_batch_btn.setVisible(False)
        self.stop_batch_btn.clicked.connect(self.stop_batch_conversion)
        self.stop_batch_btn.setStyleSheet("background-color: #f44336;")

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.stop_batch_btn.setIcon(QIcon(stop_icon_path))
        else:
            self.stop_batch_btn.setIcon(QIcon("icons/stop.png"))
        batch_action_layout.addWidget(self.stop_batch_btn)

    def create_toolbar(self):
        web_icon_path = resource_path("icons/web.png")
        bug_report_icon_path = resource_path("icons/bug_report.png")

        toolbar = self.addToolBar("Navigation")
        toolbar.setMovable(False)

        web_action = QAction("Try on Web version", self)
        
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            web_action.setIcon(QIcon(web_icon_path))
        else:
            web_action.setIcon(QIcon("icons/web.png"))

        web_action.triggered.connect(self.open_website)
        toolbar.addAction(web_action)

        bug_report = QAction("Report the bug on GitHub", self)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            bug_report.setIcon(QIcon(bug_report_icon_path))
        else:
            bug_report.setIcon(QIcon("icons/bug_report.png"))

        bug_report.triggered.connect(self.report_bug)
        toolbar.addAction(bug_report)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

    def open_website(self):
        webbrowser.open("https://sirthegamercoder.github.io/Psych-to-Codename-Character-Converter/")

    def report_bug(self):
        webbrowser.open("https://github.com/sirthegamercoder/Psych-to-Codename-Character-Converter/issues")

    def center(self):
        frame_geo = self.frameGeometry()
        screen = QApplication.primaryScreen()
        available_geo = screen.availableGeometry()
        center_point = available_geo.center()
        frame_geo.moveCenter(center_point)
        self.move(frame_geo.topLeft())

    def apply_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")

        dark_palette = QPalette()

        dark_bg = QColor(30, 30, 35)
        darker_bg = QColor(20, 20, 25)
        widget_bg = QColor(40, 40, 45)
        highlight = QColor(76, 175, 80)
        highlight_hover = QColor(56, 155, 60)
        text_color = QColor(220, 220, 220)
        text_disabled = QColor(100, 100, 100)
        border_color = QColor(50, 50, 55)

        dark_palette.setColor(QPalette.ColorRole.Window, dark_bg)
        dark_palette.setColor(QPalette.ColorRole.WindowText, text_color)
        dark_palette.setColor(QPalette.ColorRole.Base, darker_bg)
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, widget_bg)
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 40, 45))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
        dark_palette.setColor(QPalette.ColorRole.Text, text_color)
        dark_palette.setColor(QPalette.ColorRole.Button, widget_bg)
        dark_palette.setColor(QPalette.ColorRole.ButtonText, text_color)
        dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 100, 100))
        dark_palette.setColor(QPalette.ColorRole.Link, highlight)
        dark_palette.setColor(QPalette.ColorRole.Highlight, highlight)
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.PlaceholderText, text_disabled)

        app.setPalette(dark_palette)

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {dark_bg.name()};
            }}
            
            QGroupBox {{
                border: 1px solid {border_color.name()};
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                background-color: {widget_bg.name()};
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: {highlight.name()};
            }}
            
            QPushButton {{
                background-color: {highlight.name()};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                color: white;
                min-width: 100px;
            }}
            
            QPushButton:hover {{
                background-color: {highlight_hover.name()};
            }}
            
            QPushButton:pressed {{
                background-color: {darker_bg.name()};
            }}
            
            QPushButton:disabled {{
                background-color: {text_disabled.name()};
                color: {darker_bg.name()};
            }}
            
            QLabel {{
                color: {text_color.name()};
            }}
            
            QProgressBar {{
                border: 1px solid {border_color.name()};
                border-radius: 4px;
                text-align: center;
                background-color: {darker_bg.name()};
                color: {text_color.name()};
            }}
            
            QProgressBar::chunk {{
                background-color: {highlight.name()};
                border-radius: 3px;
            }}
            
            QListWidget {{
                background-color: {darker_bg.name()};
                border: 1px solid {border_color.name()};
                border-radius: 4px;
                padding: 4px;
                color: {text_color.name()};
                outline: none;
            }}
            
            QListWidget::item {{
                padding: 4px;
                border-bottom: 1px solid {border_color.name()};
            }}
            
            QListWidget::item:selected {{
                background-color: {highlight.name()};
                color: white;
            }}
            
            QListWidget::item:hover {{
                background-color: {widget_bg.name()};
            }}
            
            QTextEdit {{
                background-color: {darker_bg.name()};
                border: 1px solid {border_color.name()};
                border-radius: 4px;
                padding: 4px;
                color: {text_color.name()};
            }}
            
            QTextEdit:focus {{
                border: 1px solid {highlight.name()};
            }}
            
            QFrame[frameShape="4"] {{
                color: {border_color.name()};
                background-color: {border_color.name()};
            }}
            
            QSplitter::handle {{
                background-color: {border_color.name()};
            }}
        """)

    def add_log_message(self, message: str, msg_type: str = "info"):
        colors = {
            "info": "#FFFFFF",
            "success": "#4CAF50",
            "error": "#f44336",
            "warning": "#FFA500"
        }
        color = colors.get(msg_type, "#FFFFFF")
        self.log_text.append(f'<span style="color:{color};">{message}</span>')
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def select_xml_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select XML Character File", "", "XML Files (*.xml);;All Files (*.*)"
        )

        if file_path:
            self.current_xml_path = file_path
            self.input_path_label.setText(file_path)
            self.input_path_label.setStyleSheet("color: #4CAF50;")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    xml_content = f.read()
                    self.current_xml_content = xml_content
                    self.status_label.setText(f"Loaded XML file: {os.path.basename(file_path)}")
                    self.status_label.setStyleSheet("color: #4CAF50;")
                    self.add_log_message(f"Loaded file: {file_path}", "success")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load XML file: {str(e)}")
                self.add_log_message(f"Failed to load file: {str(e)}", "error")

    def select_output_path(self):
        start_dir = ""
        output_name = "character.json"
        if self.current_xml_path:
            start_dir = os.path.dirname(self.current_xml_path)
            base_name = os.path.basename(self.current_xml_path)
            file_name = os.path.splitext(base_name)[0]
            output_name = f"{file_name}.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save JSON Character File",
            os.path.join(start_dir, output_name),
            "JSON Files (*.json);;All Files (*.*)",
        )

        if file_path:
            self.current_json_path = file_path
            self.output_path_label.setText(file_path)
            self.output_path_label.setStyleSheet("color: #4CAF50;")

    def start_conversion(self):
        if not self.current_xml_content or not self.current_xml_content.strip():
            QMessageBox.warning(self, "Warning", "Please load an XML file first.")
            return

        if not self.current_json_path:
            self.select_output_path()
            if not self.current_json_path:
                return

        self.convert_btn.setEnabled(False)
        self.select_file_btn.setEnabled(False)
        self.select_output_btn.setEnabled(False)
        self.single_progress_bar.setVisible(True)
        self.single_progress_bar.setRange(0, 0)

        xml_content = self.current_xml_content
        output_path = self.current_json_path

        self.worker = ConversionWorker(xml_content, self.current_xml_path, output_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_conversion_finished)
        self.worker.error.connect(self.on_conversion_error)
        self.worker.start()

    def update_progress(self, message: str, input_path: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #FFA500;")

    def on_conversion_finished(self, result: Dict, output_path: str):
        self.convert_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        self.select_output_btn.setEnabled(True)
        self.single_progress_bar.setVisible(False)

        if output_path:
            QMessageBox.information(
                self,
                "Success",
                f"Character converted and saved to:\n{output_path}",
            )
            self.add_log_message(f"Successfully converted to: {output_path}", "success")

        self.status_label.setText("Conversion completed successfully!")
        self.status_label.setStyleSheet("color: #4CAF50;")

    def on_conversion_error(self, error_msg: str, input_path: str):
        self.convert_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        self.select_output_btn.setEnabled(True)
        self.single_progress_bar.setVisible(False)

        QMessageBox.critical(self, "Conversion Error", error_msg)
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setStyleSheet("color: #f44336;")
        self.add_log_message(f"Conversion error: {error_msg}", "error")

    def add_batch_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select XML Character Files", "", "XML Files (*.xml);;All Files (*.*)"
        )
        
        for file_path in file_paths:
            if file_path not in [f[0] for f in self.batch_files]:
                self.batch_files.append((file_path, ""))
                self.add_file_to_list(file_path, "")
        
        self.update_batch_ui_state()

    def add_batch_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Folder containing XML files"
        )
        
        if folder_path:
            xml_files = []
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.xml'):
                        full_path = os.path.join(root, file)
                        xml_files.append(full_path)
            
            for file_path in xml_files:
                if file_path not in [f[0] for f in self.batch_files]:
                    self.batch_files.append((file_path, ""))
                    self.add_file_to_list(file_path, "")
            
            self.add_log_message(f"Added {len(xml_files)} XML files from folder: {folder_path}", "info")
            self.update_batch_ui_state()

    def add_file_to_list(self, file_path: str, output_path: str):
        item = QListWidgetItem(os.path.basename(file_path))
        item.setToolTip(f"Input: {file_path}\nOutput: {output_path if output_path else 'Not set'}")
        item.setData(Qt.ItemDataRole.UserRole, (file_path, output_path))
        self.file_list_widget.addItem(item)

    def clear_batch_files(self):
        self.batch_files.clear()
        self.file_list_widget.clear()
        self.update_batch_ui_state()
        self.add_log_message("Cleared all files from batch list", "info")

    def remove_selected_files(self):
        selected_items = self.file_list_widget.selectedItems()
        for item in selected_items:
            file_path, _ = item.data(Qt.ItemDataRole.UserRole)
            self.batch_files = [f for f in self.batch_files if f[0] != file_path]
            self.file_list_widget.takeItem(self.file_list_widget.row(item))
        self.update_batch_ui_state()
        self.add_log_message(f"Removed {len(selected_items)} file(s) from batch list", "info")

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory for Batch Conversion"
        )
        
        if directory:
            self.output_dir = directory
            self.output_dir_label.setText(directory)
            self.output_dir_label.setStyleSheet("color: #4CAF50;")

            updated_files = []
            for input_path, _ in self.batch_files:
                base_name = os.path.splitext(os.path.basename(input_path))[0]
                output_path = os.path.join(directory, f"{base_name}.json")
                updated_files.append((input_path, output_path))
            
            self.batch_files = updated_files

            self.file_list_widget.clear()
            for input_path, output_path in self.batch_files:
                self.add_file_to_list(input_path, output_path)
            
            self.add_log_message(f"Output directory set to: {directory}", "success")
            self.update_batch_ui_state()

    def update_batch_ui_state(self):
        has_files = len(self.batch_files) > 0
        has_output_dir = hasattr(self, 'output_dir') and self.output_dir
        
        self.batch_convert_btn.setEnabled(has_files and has_output_dir)
        self.clear_files_btn.setEnabled(has_files)
        self.remove_selected_btn.setEnabled(len(self.file_list_widget.selectedItems()) > 0)

    def start_batch_conversion(self):
        if not self.batch_files:
            QMessageBox.warning(self, "Warning", "Please add XML files to convert.")
            return
        
        if not hasattr(self, 'output_dir') or not self.output_dir:
            QMessageBox.warning(self, "Warning", "Please select an output directory.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Batch Conversion",
            f"Are you sure you want to convert {len(self.batch_files)} file(s)?\n\n"
            f"Output directory: {self.output_dir}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
 
        self.set_batch_ui_enabled(False)

        self.log_text.clear()
        self.add_log_message(f"Starting batch conversion of {len(self.batch_files)} file(s)...", "info")
        
        self.batch_manager = BatchConversionManager()
        self.batch_manager.setup_batch(self.batch_files, self.output_dir)

        self.batch_manager.progress_updated.connect(self.on_batch_progress)
        self.batch_manager.file_completed.connect(self.on_batch_file_completed)
        self.batch_manager.batch_finished.connect(self.on_batch_finished)
        self.batch_manager.log_message.connect(self.add_log_message)
        
        self.batch_manager.start()

    def stop_batch_conversion(self):
        if self.batch_manager and self.batch_manager.is_running:
            reply = QMessageBox.question(
                self,
                "Stop Batch Conversion",
                "Are you sure you want to stop the batch conversion?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.batch_manager.stop()
                self.add_log_message("Stopping batch conversion...", "warning")

    def on_batch_progress(self, current: int, total: int, current_file: str):
        self.batch_progress_bar.setVisible(True)
        self.batch_progress_bar.setRange(0, total)
        self.batch_progress_bar.setValue(current)
        self.current_file_label.setVisible(True)
        self.current_file_label.setText(f"Processing: {current_file} ({current}/{total})")
        self.status_label.setText(f"Batch progress: {current}/{total}")

    def on_batch_file_completed(self, file_path: str, success: bool, message: str):
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            item_file_path, _ = item.data(Qt.ItemDataRole.UserRole)
            if item_file_path == file_path:
                if success:
                    item.setText(f"{item.text()}")
                    item.setForeground(QColor(76, 175, 80))
                else:
                    item.setText(f"{item.text()}")
                    item.setForeground(QColor(244, 67, 54))
                item.setToolTip(f"{item.toolTip()}\nStatus: {message}")
                break

    def on_batch_finished(self, success_count: int, fail_count: int):
        self.set_batch_ui_enabled(True)
        self.batch_progress_bar.setVisible(False)
        self.current_file_label.setVisible(False)
        
        if fail_count == 0:
            self.status_label.setText(f"Batch completed! {success_count} files converted successfully.")
            self.status_label.setStyleSheet("color: #4CAF50;")
            QMessageBox.information(
                self,
                "Batch Conversion Complete",
                f"Successfully converted: {success_count} file(s)\nFailed: {fail_count} file(s)\n\n"
                f"Check the log for details."
            )
        else:
            self.status_label.setText(f"Batch completed with {fail_count} error(s).")
            self.status_label.setStyleSheet("color: #FFA500;")
            QMessageBox.warning(
                self,
                "Batch Conversion Completed with Errors",
                f"Successfully converted: {success_count} file(s)\nFailed: {fail_count} file(s)\n\n"
                f"Check the log for details."
            )
        
        self.add_log_message(f"Batch conversion finished. Success: {success_count}, Failed: {fail_count}", 
                            "success" if fail_count == 0 else "warning")

    def set_batch_ui_enabled(self, enabled: bool):
        self.add_files_btn.setEnabled(enabled)
        self.add_folder_btn.setEnabled(enabled)
        self.clear_files_btn.setEnabled(enabled)
        self.remove_selected_btn.setEnabled(enabled)
        self.select_output_dir_btn.setEnabled(enabled)
        self.batch_convert_btn.setEnabled(enabled)
        self.stop_batch_btn.setVisible(not enabled)

        self.select_file_btn.setEnabled(enabled)
        self.select_output_btn.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)


def main():
    app_icon_path = resource_path("icons/app.ico")

    app = QApplication(sys.argv)
    app.setApplicationName("Psych to Codename Character Converter")

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        app.setWindowIcon(QIcon(app_icon_path))
    else:
        app.setWindowIcon(QIcon("icons/app.ico"))

    window = PsychToCodenameConverter()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()