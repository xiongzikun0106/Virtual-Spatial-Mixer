from PyQt6.QtWidgets import QToolBar, QToolButton, QLabel, QWidget, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt


class Toolbar(QToolBar):
    import_clicked = pyqtSignal()
    play_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    record_toggled = pyqtSignal(bool)
    export_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setFixedHeight(40)

        self.btn_import = QToolButton()
        self.btn_import.setText("Import WAV")
        self.btn_import.clicked.connect(self.import_clicked.emit)
        self.addWidget(self.btn_import)

        self.addSeparator()

        self.btn_play = QToolButton()
        self.btn_play.setText("Play")
        self.btn_play.clicked.connect(self.play_clicked.emit)
        self.addWidget(self.btn_play)

        self.btn_stop = QToolButton()
        self.btn_stop.setText("Stop")
        self.btn_stop.clicked.connect(self.stop_clicked.emit)
        self.addWidget(self.btn_stop)

        self.btn_record = QToolButton()
        self.btn_record.setText("Record")
        self.btn_record.setCheckable(True)
        self.btn_record.toggled.connect(self.record_toggled.emit)
        self.addWidget(self.btn_record)

        self.addSeparator()

        self.btn_export = QToolButton()
        self.btn_export.setText("Export Mix")
        self.btn_export.clicked.connect(self.export_clicked.emit)
        self.addWidget(self.btn_export)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        self.time_label = QLabel("00:00.000")
        self.time_label.setStyleSheet("color: #00E5FF; font-size: 14px; padding-right: 12px;")
        self.addWidget(self.time_label)

    def set_playing(self, playing: bool):
        self.btn_play.setText("Pause" if playing else "Play")

    def set_time(self, seconds: float):
        mins = int(seconds) // 60
        secs = seconds - mins * 60
        self.time_label.setText(f"{mins:02d}:{secs:06.3f}")
