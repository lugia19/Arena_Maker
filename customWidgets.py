import os
import sys
import time

import requests as requests
from PyQt6 import QtWidgets, QtCore, QtGui

class DownloadThread(QtCore.QThread):
    setProgressBarTotalSignal = QtCore.pyqtSignal(int)
    updateProgressSignal = QtCore.pyqtSignal(int)
    etaSignal = QtCore.pyqtSignal(int)
    doneSignal = QtCore.pyqtSignal()

class FileDownloadThread(DownloadThread):
    def __init__(self, url, location):
        super().__init__()
        self.url = url
        self.location = location

    def run(self):
        response = requests.get(self.url, stream=True)
        total_size_in_bytes = response.headers.get('content-length')

        if total_size_in_bytes is None:  # If 'content-length' is not found in headers
            self.setProgressBarTotalSignal.emit(-1)  # Set progress bar to indeterminate state
        else:
            total_size_in_bytes = int(total_size_in_bytes)
            self.setProgressBarTotalSignal.emit(total_size_in_bytes)

        block_size = 1024 * 16
        try:
            response.raise_for_status()
            file = open(self.location, 'wb')

            start_time = time.time()
            total_data_received = 0
            last_emit_time = start_time  # Initialize last_emit_time to start_time
            data_received_since_last_emit = 0

            for data in response.iter_content(block_size):
                total_data_received += len(data)
                data_received_since_last_emit += len(data)

                file.write(data)
                if total_size_in_bytes is not None:  # Only update if 'content-length' was found
                    current_time = time.time()
                    if current_time - last_emit_time >= 1:
                        elapsed_time_since_last_emit = current_time - last_emit_time
                        download_speed = data_received_since_last_emit / elapsed_time_since_last_emit

                        # Calculate ETA
                        remaining_data = total_size_in_bytes - total_data_received
                        if download_speed != 0:  # Avoid division by zero
                            eta = int(remaining_data / download_speed)
                            self.etaSignal.emit(eta)
                        self.updateProgressSignal.emit(int((total_data_received / total_size_in_bytes) * 100))
                        # Reset tracking variables for the next X seconds
                        last_emit_time = current_time  # Update last_emit_time
                        data_received_since_last_emit = 0  # Reset data_received_since_last_emit

            file.flush()
            file.close()

        except requests.exceptions.RequestException as e:
            if os.path.exists(self.location):
                os.remove(self.location)
            raise

        self.doneSignal.emit()


class ProgressDialog(QtWidgets.QDialog):
    def __init__(self, baseLabelText, downloadThread:DownloadThread):
        super().__init__()

        self.setWindowTitle('Download')
        self.previous_percent_completed = -1

        self.layout = QtWidgets.QVBoxLayout()
        self.baseLabelText = baseLabelText
        self.label = QtWidgets.QLabel(self.baseLabelText)

        self.layout.addWidget(self.label)
        self.progress = QtWidgets.QProgressBar(self)
        self.layout.addWidget(self.progress)
        self.setLayout(self.layout)

        self.download_thread = downloadThread

        self.download_thread.setProgressBarTotalSignal.connect(self.set_progress_bar_total)
        self.download_thread.doneSignal.connect(lambda: self.done(0))
        self.download_thread.etaSignal.connect(self.set_eta)
        self.download_thread.updateProgressSignal.connect(self.update_progress_bar)

    def set_eta(self, ETASeconds):
        self.label.setText(f"{self.baseLabelText} ({format_eta(ETASeconds)})")

    def set_progress_bar_total(self, amount):
        if amount == -1:
            self.progress.setRange(0, 0)
        else:
            self.progress.setMaximum(100)

    def update_progress_bar(self, percent_completed):
        if percent_completed != self.previous_percent_completed:
            self.progress.setValue(percent_completed)
            self.previous_percent_completed = percent_completed

    def showEvent(self, event):
        super().showEvent(event)
        self.download_thread.start()

    def closeEvent(self, event):
        reply = QtWidgets.QMessageBox.question(
            self,
            'Confirmation',
            'Are you sure you want to quit?',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.download_thread.terminate()
            event.accept()
            sys.exit(0)
        else:
            event.ignore()

class DownloadDialog(ProgressDialog):
    def __init__(self, baseLabelText, url, location):
        super().__init__(baseLabelText, FileDownloadThread(url, location))


def format_eta(seconds) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{int(hours)}h {int(minutes)}m"
    elif minutes:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"