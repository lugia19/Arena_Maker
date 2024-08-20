import hashlib
import os
import re
import subprocess
import sys
import json
import shutil
import zipfile
import webbrowser

import toml
from core import *
import requests
from PyQt6.QtWidgets import QApplication, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QListWidget, QPushButton, QLineEdit, QFileDialog, QMessageBox, QLabel, QWidget, QProgressBar
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread

from customWidgets import DownloadDialog

CONFIG_FILE = "config.json"

def launch_modengine2():
    resources_dir = os.path.join(os.path.dirname(__file__), "resources")
    me2_config_path = os.path.join(ARENA_MAKER_DATA_FOLDER, "custom_arena_config.toml")
    mod_folder = os.path.join(ARENA_MAKER_DATA_FOLDER, "mod")

    # Create custom_arena_config.toml if it doesn't exist
    if not os.path.exists(me2_config_path):
        me2_config_data = {
            "modengine": {
                "debug": False,
                "external_dlls": []
            },
            "extension": {
                "mod_loader": {
                    "enabled": True,
                    "loose_params": False,
                    "mods": [
                        {
                            "enabled": True,
                            "name": "CustomArena",
                            "path": mod_folder
                        }
                    ]
                },
                "scylla_hide": {
                    "enabled": False
                }
            }
        }

        with open(me2_config_path, "w") as file:
            toml_string = toml.dumps(me2_config_data)
            toml_string = toml_string.replace('"[[extension.mod_loader.mods]]"', '[[extension.mod_loader.mods]]')
            file.write(toml_string)

    # Launch modengine2 with the specified arguments
    me2_dir = os.path.join(TOOLS_FOLDER, "me2")
    os.makedirs(me2_dir, exist_ok=True)
    me2_exe = os.path.join(me2_dir, "modengine2_launcher.exe")
    if not os.path.exists(me2_exe):
        me2_zip = os.path.join(resources_dir, "modengine-sound-build.zip")
        with zipfile.ZipFile(me2_zip, 'r') as zip_ref:
            zip_ref.extractall(me2_dir)

    subprocess.Popen([me2_exe, "-t", "ac6", "-c", me2_config_path])

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
        compile_folder(self.progress)
        try:
            pass
        except Exception as e:
            self.error.emit(e)

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
        #if value == 100:
        #    QMessageBox.information(self, "Success", "Mod has been compiled. Ensure it's enabled.")

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

        self.compile_button = QPushButton("Launch")
        self.compile_button.clicked.connect(self.compile)
        self.open_folder_button = QPushButton("Open Fights")
        self.open_folder_button.clicked.connect(self.open_fights_folder)

        self.open_mod_button = QPushButton("Open Mod")
        self.open_mod_button.clicked.connect(self.open_mods_folder)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)

        bottom_layout_1 = QHBoxLayout()
        bottom_layout_1.addWidget(self.import_button)
        bottom_layout_1.addWidget(self.remove_button)
        bottom_layout_1.addWidget(self.open_folder_button)
        bottom_layout_2 = QHBoxLayout()
        bottom_layout_2.addWidget(self.open_mod_button)
        bottom_layout_2.addWidget(self.compile_button)

        list_layout = QHBoxLayout()
        list_layout.addWidget(self.folder_list)
        list_layout.addLayout(button_layout)

        self.layout.addLayout(list_layout)
        self.layout.addLayout(bottom_layout_1)
        self.layout.addLayout(bottom_layout_2)

        self.load_folders()

    def open_fights_folder(self):
        if os.path.exists(FIGHTS_FOLDER):
            os.startfile(FIGHTS_FOLDER)
        else:
            QMessageBox.warning(self, "Error", "Fights folder not found.")

    def open_mods_folder(self):
        mod_folder = os.path.join(ARENA_MAKER_DATA_FOLDER, "mod")
        os.makedirs(mod_folder, exist_ok=True)
        os.startfile(mod_folder)

    def load_folders(self):
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w") as fp: fp.write("{}")

            #Copy over sample fight
            os.makedirs(FIGHTS_FOLDER, exist_ok=True)
            zip_path = os.path.join("resources", "example_fights.zip")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(FIGHTS_FOLDER)

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

    def compile(self):
        # Check if the mod folder exists and last_run.txt matches the current folder order
        last_run_path = os.path.join(ARENA_MAKER_DATA_FOLDER, "last_run.txt")
        mod_folder = os.path.join(ARENA_MAKER_DATA_FOLDER, "mod")
        if os.path.exists(mod_folder) and os.path.exists(last_run_path):
            with open(last_run_path, "r") as file:
                last_run_order = file.read().strip()
            current_order = ",".join([self.folder_list.item(i).text() for i in range(self.folder_list.count())])
            if last_run_order == current_order:
                reply = QMessageBox.question(self, "Skip Compilation", "The mod folder already exists and the folder order hasn't changed. Do you want to skip the compilation?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    launch_modengine2()
                    return

        progress_dialog = ProgressDialog(self)
        progress_dialog.start_task()
        progress_dialog.exec()

        # Save the current folder order to last_run.txt
        current_order = ",".join([self.folder_list.item(i).text() for i in range(self.folder_list.count())])
        with open(last_run_path, "w") as file:
            file.write(current_order)

        launch_modengine2()


    def load_folder_order(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as file:
                config = json.load(file)
                folder_order = config.get("folder_order", [])

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
    os.makedirs(TOOLS_FOLDER, exist_ok=True)

    if not os.path.exists(VERSIONS_FILE):
        with open(VERSIONS_FILE, "w") as fp:
            json.dump({}, fp)

    with open(VERSIONS_FILE, 'r') as file:
        versions = json.load(file)

    rewwise_dir = os.path.join(TOOLS_FOLDER, "rewwise")

    latest_rewwise_release = get_github_release("vswarte", "rewwise")
    if latest_rewwise_release and versions.get("rewwise_release", "0.0") != latest_rewwise_release[0]:
        zip_path = os.path.join(rewwise_dir, "rewwise.zip")
        DownloadDialog(f"Downloading rewwise", "https://github.com/vswarte/rewwise/releases/latest/download/binaries.zip", zip_path).exec()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(rewwise_dir)
        versions["rewwise_release"] = latest_rewwise_release[0]

    texconv_path = os.path.join(TOOLS_FOLDER, "DirectXTex", "texconv.exe")
    os.makedirs(os.path.join(TOOLS_FOLDER, "DirectXTex"))
    latest_texconv_release = get_github_release("microsoft", "DirectXTex")
    if latest_texconv_release and versions.get("texconv_release", "0.0") != latest_texconv_release[0]:
        DownloadDialog(f"Downloading texconv", "https://github.com/microsoft/DirectXTex/releases/latest/download/texconv.exe", texconv_path).exec()
        versions["texconv_release"] = latest_texconv_release[0]

    witchy_dir = os.path.join(TOOLS_FOLDER, "witchybnd")
    os.makedirs(witchy_dir, exist_ok=True)
    latest_witchy_release = get_github_release("ividyon", "WitchyBND")
    if latest_witchy_release and versions.get("witchy_release", "0.0") != latest_witchy_release[0]:
        zip_path = os.path.join(witchy_dir, "witchy.zip")
        DownloadDialog(f"Downloading WitchyBND", latest_witchy_release[1][0]["browser_download_url"], zip_path).exec()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(witchy_dir)

        versions["witchy_release"] = latest_witchy_release[0]

    ffdec_dir = os.path.join(TOOLS_FOLDER, "ffdec")
    os.makedirs(ffdec_dir, exist_ok=True)
    ffdec_release = get_github_release("jindrapetrik", "jpexs-decompiler", tag="version20.1.0")
    if ffdec_release and versions.get("ffdec_release", "0.0") != ffdec_release[0]:
        zip_path = os.path.join(ffdec_dir, "ffdec.zip")
        download_url = None
        for asset in ffdec_release[1]:
            if re.match("ffdec(\d+\.)+zip", asset["name"]):
                download_url = asset["browser_download_url"]
                break
        if download_url:
            DownloadDialog(f"Downloading ffdec", download_url, zip_path).exec()
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(ffdec_dir)

        versions["ffdec_release"] = ffdec_release[0]

    game_data_zip = os.path.join(ARENA_MAKER_DATA_FOLDER, "game_data.zip")
    if os.path.exists(game_data_zip):
        with open(game_data_zip, 'rb') as file:
            game_data_hash = hashlib.sha1(file.read()).hexdigest()
    else:
        game_data_hash = None

    expected_hash = "d31015d76a13165c66ea58276cfe04449de3f577"
    download_url = "https://f004.backblazeb2.com/file/lugia19/game_data.zip"
    if not game_data_hash or game_data_hash != expected_hash:
        DownloadDialog(f"Downloading base game files...", download_url, game_data_zip).exec()


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

    sys.exit(app.exec())