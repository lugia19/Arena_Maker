import os
import re
import subprocess
import sys
import json
import shutil
import zipfile
import webbrowser
import core
import requests
from PyQt6.QtWidgets import QApplication, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QListWidget, QPushButton, QLineEdit, QFileDialog, QMessageBox, QLabel, QWidget, QProgressBar
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread

from customWidgets import DownloadDialog

CONFIG_FILE = "config.json"

FIGHTS_FOLDER = core.FIGHTS_FOLDER
class PathWidget(QWidget):
    def __init__(self, label_text, browse_text, link_url=None, is_file=True):
        super().__init__()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.is_file = is_file

        self.label = QLabel(label_text)
        self.line_edit = QLineEdit()
        self.browse_button = QPushButton(browse_text)
        self.browse_button.clicked.connect(self.browse_path)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.line_edit)
        button_layout.addWidget(self.browse_button)

        if link_url:
            self.link_button = QPushButton("Open Link")
            self.link_url = link_url
            self.link_button.clicked.connect(self.open_link)
            button_layout.addWidget(self.link_button)

        self.layout.addWidget(self.label)
        self.layout.addLayout(button_layout)

    def browse_path(self):
        if self.is_file:
            path = QFileDialog.getOpenFileName(self, "Select File")[0]
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if path:
            self.line_edit.setText(path)

    def open_link(self):
        webbrowser.open(self.link_url)

class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int, str)
    error = pyqtSignal(object)
    def run(self):
        #try:
        core.compile_folder(self.progress)
        #except Exception as e:
            #self.error.emit(e)

        self.finished.emit()

class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Progress")
        self.setMinimumWidth(300)

        self.progress_bar = QProgressBar(self)
        self.status_label = QLabel("Initializing...", self)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

        self.thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.accept)
        self.worker.error.connect(self.error_display)

    def start_task(self):
        self.thread.start()
    def error_display(self, exception):
        QMessageBox.critical(None, "Error", f"Compilation failed: {exception}")
    def closeEvent(self, event) -> None:
        event.ignore()

    def update_progress(self, value, status):
        self.progress_bar.setValue(value)
        self.status_label.setText(status)
        if value == 100:
            QMessageBox.information(self, "Success", "Mod has been compiled. Ensure it's enabled.")

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.wwise_studio_widget = PathWidget("WwiseConsole.exe Path:", "Browse", "https://www.audiokinetic.com/en/download/")
        self.wwise_studio_widget.line_edit.setToolTip("The location of WwiseConsole.exe")
        self.mod_folder_widget = PathWidget("Destination Mod Folder:", "Browse", is_file=False)
        self.mod_folder_widget.line_edit.setToolTip("The folder where you want your finalized mod to go.")
        self.game_folder_widget = PathWidget("AC6 Game Folder:", "Browse", is_file=False)
        self.game_folder_widget.line_edit.setToolTip("Needs to have been unpacked using UXM.")
        self.layout.addWidget(self.wwise_studio_widget)
        self.layout.addWidget(self.mod_folder_widget)
        self.layout.addWidget(self.game_folder_widget)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_config)
        button_layout.addWidget(self.save_button)

        self.layout.addLayout(button_layout)

    def save_config(self):
        if not self.wwise_studio_widget.line_edit.text() or not self.mod_folder_widget.line_edit.text() or not self.game_folder_widget.line_edit.text():
            QMessageBox.warning(self, "Warning", "Please fill in all the required paths.")
        else:
            with open(CONFIG_FILE, "r") as fp: config = json.load(fp)
            config["wwise_studio_path"] = self.wwise_studio_widget.line_edit.text().replace("/","\\")
            config["mod_folder"] = self.mod_folder_widget.line_edit.text().replace("/","\\")
            game_folder = self.game_folder_widget.line_edit.text()
            if not game_folder.endswith("Game"):
                game_folder = os.path.join(game_folder, "Game")
                self.game_folder_widget.line_edit.setText(game_folder)
            config["game_folder"] = game_folder.replace("/","\\")
            with open(CONFIG_FILE, 'w') as file:
                json.dump(config, file, indent=4)
            self.accept()

    def closeEvent(self, event):
        if not self.wwise_studio_widget.line_edit.text() or not self.mod_folder_widget.line_edit.text() or not self.game_folder_widget.line_edit.text():
            QMessageBox.warning(self, "Warning", "Please fill in all the required paths.")
            event.ignore()
        else:
            event.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arena Maker")
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.folder_list = QListWidget()

        self.up_button = QPushButton("↑")
        self.up_button.clicked.connect(self.move_up)
        self.down_button = QPushButton("↓")
        self.down_button.clicked.connect(self.move_down)

        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self.import_folder)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_folder)

        self.config_button = QPushButton("Config")
        self.config_button.clicked.connect(self.open_config)
        self.compile_button = QPushButton("Compile")
        self.compile_button.clicked.connect(self.compile)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(self.open_fights_folder)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)

        bottom_layout_1 = QHBoxLayout()
        bottom_layout_1.addWidget(self.import_button)
        bottom_layout_1.addWidget(self.remove_button)
        bottom_layout_1.addWidget(self.open_folder_button)
        bottom_layout_2 = QHBoxLayout()
        bottom_layout_2.addWidget(self.config_button)
        bottom_layout_2.addWidget(self.compile_button)

        list_layout = QHBoxLayout()
        list_layout.addWidget(self.folder_list)
        list_layout.addLayout(button_layout)

        self.layout.addLayout(list_layout)
        self.layout.addLayout(bottom_layout_1)
        self.layout.addLayout(bottom_layout_2)

        self.config_dialog = ConfigDialog(self)
        self.load_config()
        self.load_folders()

    def open_fights_folder(self):
        if os.path.exists(FIGHTS_FOLDER):
            os.startfile(FIGHTS_FOLDER)
        else:
            QMessageBox.warning(self, "Error", "Fights folder not found.")

    def load_folders(self):
        folder_order = self.load_folder_order()
        self.folder_list.clear()
        updated_folder_order = []
        for folder in folder_order:
            if os.path.exists(os.path.join(FIGHTS_FOLDER, folder)):
                self.folder_list.addItem(folder)
                updated_folder_order.append(folder)
            else:
                print(f"Folder not found: {folder}")
        if updated_folder_order != folder_order:
            self.save_folder_order(updated_folder_order)

    def move_up(self):
        current_row = self.folder_list.currentRow()
        if current_row > 0:
            current_item = self.folder_list.takeItem(current_row)
            self.folder_list.insertItem(current_row - 1, current_item)
            self.folder_list.setCurrentRow(current_row - 1)
            self.save_folder_order()

    def move_down(self):
        current_row = self.folder_list.currentRow()
        if current_row < self.folder_list.count() - 1:
            current_item = self.folder_list.takeItem(current_row)
            self.folder_list.insertItem(current_row + 1, current_item)
            self.folder_list.setCurrentRow(current_row + 1)
            self.save_folder_order()

    def import_folder(self):
        zip_files, _ = QFileDialog.getOpenFileNames(self, "Select ZIP Files", "", "ZIP Files (*.zip)")
        for zip_file in zip_files:
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    root_path = zipfile.Path(zip_ref, "")
                    namelist = zip_ref.namelist()
                    folder_names = set(os.path.dirname(name) for name in namelist)
                    if "data.json" in namelist and any(name.endswith(".design") for name in namelist):
                        # Handle the case where data.json is in the root of the ZIP
                        zip_name = os.path.splitext(os.path.basename(zip_file))[0]
                        dest_folder = os.path.join(FIGHTS_FOLDER, zip_name)
                        os.makedirs(dest_folder, exist_ok=True)
                        zip_ref.extractall(dest_folder)
                        if len(self.folder_list.findItems(zip_name, Qt.MatchFlag.MatchExactly)) == 0:
                            self.folder_list.addItem(zip_name)
                        self.save_folder_order()
                    else:
                        # Handle the case where data.json is in subfolders
                        for folder_name in folder_names:
                            if not folder_name.count("/") == 0:
                                continue
                            path_obj = root_path.joinpath(folder_name)

                            if path_obj.is_dir():
                                datajson_obj = root_path.joinpath(folder_name, "data.json")
                                design_exists = any(name.endswith(".design") for name in zip_ref.namelist() if name.startswith(folder_name))
                                if not (datajson_obj.is_file() and design_exists):
                                    raise ValueError(f"Invalid folder structure in {zip_file}")
                            dest_folder = os.path.join(FIGHTS_FOLDER, folder_name)
                            os.makedirs(dest_folder, exist_ok=True)
                            for name in zip_ref.namelist():
                                if name.startswith(folder_name):
                                    if name.endswith('/'):
                                        # This is a directory, create it
                                        os.makedirs(os.path.join(FIGHTS_FOLDER, name), exist_ok=True)
                                    else:
                                        # This is a file, extract it
                                        try:
                                            zip_ref.extract(name, FIGHTS_FOLDER)
                                        except zipfile.BadZipFile:
                                            print(f"Skipping bad zip file: {name}")
                                        except Exception as e:
                                            print(f"Error extracting {name}: {str(e)}")
                            if len(self.folder_list.findItems(folder_name, Qt.MatchFlag.MatchExactly)) == 0:
                                self.folder_list.addItem(folder_name)
                            self.save_folder_order()

            except (zipfile.BadZipFile, ValueError) as e:
                QMessageBox.warning(self, "Error", str(e))

    def remove_folder(self):
        current_item = self.folder_list.currentItem()
        if current_item:
            folder_name = current_item.text()
            folder_path = os.path.join(FIGHTS_FOLDER, folder_name)
            reply = QMessageBox.question(self, "Confirmation", f"Are you sure you want to remove the folder '{folder_name}'?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                shutil.rmtree(folder_path)
                self.folder_list.takeItem(self.folder_list.row(current_item))
                self.save_folder_order()

    def open_config(self):
        self.config_dialog.exec()

    def compile(self):
        config = json.load(open(CONFIG_FILE, "r"))
        if not os.path.exists(os.path.join(config["game_folder"], "param")):
            QMessageBox.critical(self, "ERROR", "The game has not been unpacked using UXM. Please do so.")
            return

        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.show()
        self.progress_dialog.start_task()

    def load_folder_order(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as file:
                config = json.load(file)
                folder_order = config.get("folder_order", None)

        for folder_name in os.listdir(FIGHTS_FOLDER):
            folder_path = os.path.join(FIGHTS_FOLDER, folder_name)
            if os.path.isdir(folder_path):
                data_json_path = os.path.join(folder_path, "data.json")
                design_file_found = False
                for file_name in os.listdir(folder_path):
                    if file_name.endswith(".design"):
                        design_file_found = True
                        break
                if os.path.isfile(data_json_path) and design_file_found and folder_name not in folder_order:
                    folder_order.append(folder_name)

        self.save_folder_order(folder_order)
        return folder_order
    def save_folder_order(self, folder_order=None):
        if folder_order is None:
            folder_order = [self.folder_list.item(i).text() for i in range(self.folder_list.count())]
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as file:
                config = json.load(file)
        config["folder_order"] = folder_order
        with open(CONFIG_FILE, 'w') as file:
            json.dump(config, file, indent=4)

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w") as fp: fp.write("{}")

            #Copy over sample fight
            os.makedirs(FIGHTS_FOLDER, exist_ok=True)
            zip_path = os.path.join("resources", "example_fights.zip")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(FIGHTS_FOLDER)

            msg_box = QMessageBox()
            msg_box.setWindowTitle("Attention!")
            msg_box.setText("This appears to be your first time running this tool.\n"
                            "If you want to be able to hear custom audio files and music, please make sure you are on the correct build of ModEngine2.\n"
                            "If you simply downloaded it off of github, then you are not, so click Download to get and install the correct version.")
            msg_box.addButton("Okay", QMessageBox.ButtonRole.AcceptRole)
            open_link_button = msg_box.addButton("Download", QMessageBox.ButtonRole.ActionRole)
            msg_box.exec()

            # Check which button was clicked
            if msg_box.clickedButton() == open_link_button:
                webbrowser.open("https://drive.proton.me/urls/DVXY4PQQX0#BuUpaVfPP3IU")

        with open(CONFIG_FILE, 'r') as file:
            config = json.load(file)
            if not config.get("wwise_studio_path"):
                audiokinetic_path = r"C:\Program Files (x86)\Audiokinetic"
                if os.path.exists(audiokinetic_path):
                    wwise_folders = [folder for folder in os.listdir(audiokinetic_path) if "Wwise" in folder]
                    wwise_folder = None
                    for folder in wwise_folders:
                        if "Wwise2023" in folder:
                            wwise_folder = folder
                            config["wwise_studio_path"] = folder
                            break

                    if not wwise_folder:
                        for folder in wwise_folders:
                            wwise_console_path = os.path.join(audiokinetic_path, folder, "Authoring", "x64", "Release", "bin", "WwiseConsole.exe")
                            if os.path.exists(wwise_console_path):
                                config["wwise_studio_path"] = wwise_console_path
                                break
                    else:
                        wwise_console_path = os.path.join(audiokinetic_path, wwise_folder, "Authoring", "x64", "Release", "bin", "WwiseConsole.exe")
                        config["wwise_studio_path"] = wwise_console_path

            self.config_dialog.wwise_studio_widget.line_edit.setText(config.get("wwise_studio_path", ""))
            self.config_dialog.mod_folder_widget.line_edit.setText(config.get("mod_folder", ""))
            self.config_dialog.game_folder_widget.line_edit.setText(config.get("game_folder", ""))

    def save_config(self):
        with open(CONFIG_FILE, "r") as file: config = json.load(file)
        config["wwise_studio_path"] = self.config_dialog.wwise_studio_widget.line_edit.text()
        config["mod_folder"] = self.config_dialog.mod_folder_widget.line_edit.text()
        config["game_folder"] = self.config_dialog.game_folder_widget.line_edit.text()

        with open(CONFIG_FILE, 'w') as file:
            json.dump(config, file, indent=4)

def get_github_release(repo_owner, repo_name, tag=None) -> (str, list):
    if tag:
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{tag}"
    else:
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    response = requests.get(api_url)
    if response.status_code == 200:
        release_data = response.json()
        latest_tag = release_data["tag_name"]
        return latest_tag, release_data["assets"]
    else:
        return None

def check_tools():
    root_dir = os.path.dirname(__file__)
    resources_dir = os.path.join(root_dir, "resources")

    rewwise_dir = os.path.join(resources_dir, "rewwise")
    os.makedirs(rewwise_dir, exist_ok=True)

    with open(CONFIG_FILE, 'r') as file:
        config = json.load(file)
    latest_rewwise_release = get_github_release("vswarte", "rewwise")
    if latest_rewwise_release and config.get("rewwise_release", "0.0") != latest_rewwise_release[0]:
        zip_path = os.path.join(rewwise_dir, "rewwise.zip")
        DownloadDialog(f"Downloading rewwise", "https://github.com/vswarte/rewwise/releases/latest/download/binaries.zip", zip_path).exec()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(rewwise_dir)
        config["rewwise_release"] = latest_rewwise_release[0]

    texconv_path = os.path.join(resources_dir, "texconv.exe")
    latest_texconv_release = get_github_release("microsoft", "DirectXTex")
    if latest_texconv_release and config.get("texconv_release", "0.0") != latest_texconv_release[0]:
        DownloadDialog(f"Downloading texconv", "https://github.com/microsoft/DirectXTex/releases/latest/download/texconv.exe", texconv_path).exec()
        config["texconv_release"] = latest_texconv_release[0]

    witchy_dir = os.path.join(resources_dir, "witchybnd")
    os.makedirs(witchy_dir, exist_ok=True)
    latest_witchy_release = get_github_release("ividyon", "WitchyBND")
    if latest_witchy_release and config.get("witchy_release", "0.0") != latest_witchy_release[0]:
        zip_path = os.path.join(witchy_dir, "witchy.zip")
        DownloadDialog(f"Downloading WitchyBND", latest_witchy_release[1][0]["browser_download_url"], zip_path).exec()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(witchy_dir)

        config["witchy_release"] = latest_witchy_release[0]


    ffdec_dir = os.path.join(resources_dir, "ffdec")
    os.makedirs(ffdec_dir, exist_ok=True)
    ffdec_release = get_github_release("jindrapetrik", "jpexs-decompiler", tag="version20.1.0")
    if ffdec_release and config.get("ffdec_release", "0.0") != ffdec_release[0]:
        zip_path = os.path.join(ffdec_dir, "ffdec.zip")
        download_url = None
        for asset in ffdec_release[1]:
            if re.match("ffdec_(\d+\.)+zip", asset["name"]):
                download_url = asset["browser_download_url"]
                break
        if download_url:
            DownloadDialog(f"Downloading ffdec", download_url, zip_path).exec()
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(ffdec_dir)

        config["ffdec_release"] = ffdec_release[0]
    with open(CONFIG_FILE, "w") as fp: json.dump(config, fp, indent=4)


if __name__ == "__main__":
    stylesheet = open(os.path.join(os.path.dirname(__file__),"resources", "stylesheet.qss")).read()
    colors_dict = {
        "primary_color": "#1A1D22",
        "secondary_color": "#282C34",
        "hover_color": "#596273",
        "text_color": "#FFFFFF",
        "toggle_color": "#4a708b",
        "green": "#3a7a3a",
        "yellow": "#faf20c",
        "red": "#7a3a3a"
    }

    for colorKey, colorValue in colors_dict.items():
        stylesheet = stylesheet.replace("{" + colorKey + "}", colorValue)
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet)

    main_window = MainWindow()
    main_window.show()

    check_tools()
    # Check if the required paths are specified
    if not main_window.config_dialog.wwise_studio_widget.line_edit.text() or not main_window.config_dialog.mod_folder_widget.line_edit.text() or not main_window.config_dialog.game_folder_widget.line_edit.text():
        main_window.open_config()



    sys.exit(app.exec())