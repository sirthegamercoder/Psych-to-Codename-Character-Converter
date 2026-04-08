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
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor, QIcon
from PySide6.QtCore import QSettings

from lxml import etree


class ConversionWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, xml_content: str, output_path: str = None):
        super().__init__()
        self.xml_content = xml_content
        self.output_path = output_path

    def run(self):
        try:
            self.progress.emit("Parsing XML file...")
            result = self.convert_to_psych(self.xml_content)

            if result:
                if self.output_path:
                    self.progress.emit(f"Saving to {self.output_path}...")
                    with open(self.output_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    self.progress.emit("Conversion completed successfully!")
                self.finished.emit(result)
            else:
                self.error.emit("Failed to convert XML to Psych format")
        except Exception as e:
            self.error.emit(f"Conversion error: {str(e)}")

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
                    "Invalid Codename Engine character XML: root element must be 'character'"
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
            self.progress.emit(f"Converting color from HEX {color_hex} to RGB...")
            rgb_color = self.hex_to_rgb(color_hex)
            self.progress.emit(f"RGB color: {rgb_color}")

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
            self.error.emit(f"XML parsing error: {str(e)}")
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


class PsychToCodenameConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_xml_path = None
        self.current_json_path = None
        self.current_xml_content = None
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        self.setFixedSize(750, 600)
        self.center()

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

        input_group = QGroupBox("Input")
        input_layout = QVBoxLayout(input_group)

        file_layout = QHBoxLayout()
        self.input_path_label = QLabel("No file selected")
        self.input_path_label.setWordWrap(True)
        self.input_path_label.setStyleSheet("color: #888888;")

        self.select_file_btn = QPushButton("Select XML File")
        self.select_file_btn.clicked.connect(self.select_xml_file)
        self.select_file_btn.setIcon(QIcon("icons/xml.png"))
        file_layout.addWidget(self.select_file_btn)
        file_layout.addWidget(self.input_path_label, 1)
        input_layout.addLayout(file_layout)

        main_layout.addWidget(input_group)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        output_file_layout = QHBoxLayout()
        self.output_path_label = QLabel("No output path selected")
        self.output_path_label.setWordWrap(True)
        self.output_path_label.setStyleSheet("color: #888888;")

        self.select_output_btn = QPushButton("Select Output Path")
        self.select_output_btn.clicked.connect(self.select_output_path)
        self.select_output_btn.setIcon(QIcon("icons/output.png"))
        output_file_layout.addWidget(self.select_output_btn)
        output_file_layout.addWidget(self.output_path_label, 1)
        output_layout.addLayout(output_file_layout)

        main_layout.addWidget(output_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #4CAF50; font-style: italic;")
        main_layout.addWidget(self.status_label)

        self.convert_btn = QPushButton("Convert to JSON")
        self.convert_btn.setMinimumHeight(40)
        self.convert_btn.clicked.connect(self.start_conversion)
        convert_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        self.convert_btn.setFont(convert_font)
        self.convert_btn.setIcon(QIcon("icons/convert.png"))
        main_layout.addWidget(self.convert_btn)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)

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
                padding: 8px 16px;
                font-weight: bold;
                color: white;
                min-width: 120px;
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
            
            QFrame[frameShape="4"] {{
                color: {border_color.name()};
                background-color: {border_color.name()};
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
        """)

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
                    self.status_label.setText(
                        f"Loaded XML file: {os.path.basename(file_path)}"
                    )
                    self.status_label.setStyleSheet("color: #4CAF50;")

            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to load XML file: {str(e)}"
                )

    def select_output_path(self):
        start_dir = ""
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
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        xml_content = self.current_xml_content
        output_path = self.current_json_path

        self.worker = ConversionWorker(xml_content, output_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_conversion_finished)
        self.worker.error.connect(self.on_conversion_error)
        self.worker.start()

    def update_progress(self, message: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #FFA500;")

    def on_conversion_finished(self, result: Dict):
        json_str = json.dumps(result, indent=2, ensure_ascii=False)

        self.convert_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        self.select_output_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if self.current_json_path:
            QMessageBox.information(
                self,
                "Success",
                f"✓ Character converted and saved to:\n{self.current_json_path}",
            )

        self.status_label.setText("Conversion completed successfully!")
        self.status_label.setStyleSheet("color: #4CAF50;")

    def on_conversion_error(self, error_msg: str):
        self.convert_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        self.select_output_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        QMessageBox.critical(self, "Conversion Error", error_msg)
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setStyleSheet("color: #f44336;")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Psych to Codename Character Converter")
    app.setWindowIcon(QIcon("app.ico"))

    window = PsychToCodenameConverter()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
