from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, \
    QSlider, QLineEdit,QMessageBox, QTabWidget, QProgressBar, QToolButton, QMenu, QAction, QDialog, QWidget, QTextEdit, QVBoxLayout,QDialogButtonBox
import numpy as np
from pyqtgraph import PlotWidget, mkPen
from ispim.compute_waveforms import generate_waveforms
import logging
from napari.qt.threading import thread_worker, create_worker
from time import sleep, time
from datetime import timedelta, datetime
import calendar
import qtpy.QtCore as QtCore
import json

class VolumetericAcquisition(WidgetBase):

    def __init__(self,viewer, cfg, instrument, simulated):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.cfg = cfg
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.waveform = {}
        self.selected = {}
        self.progress = {}
        self.acquisition_order = {}
    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget

    def volumeteric_imaging_button(self):

        self.volumetric_image = {'start': QPushButton('Start Volumeteric Image'),
                                 'overwrite': QCheckBox('Overwrite'),
                                 'save_config': QPushButton('Save Configuration')}
        self.volumetric_image['start'].clicked.connect(self.run_volumeteric_imaging)
        self.volumetric_image['save_config'].clicked.connect(self.instrument.cfg.save)
        # # Put in seperate function so upon initiation of gui, run() funtion does not start
        
        self.start_image_qwidget = self.create_layout(struct='H', **self.volumetric_image)  # Need qwidget to see actions
        # self.volumetric_image['start'].setText('Start Volumetric Imaging')
        #
        # add_scan = QAction("Add Scan", self.start_image_qwidget)
        # add_scan.triggered.connect(self.setup_additional_scan)
        # self.volumetric_image['start'].addAction(add_scan)
        # self.volumetric_image['start'].setPopupMode(QToolButton.MenuButtonPopup)

        return self.start_image_qwidget

    def setup_additional_scan(self):
        """Add scan to imaging run"""

        with self.instrument.stage_query_lock:
            position = self.instrument.sample_pose.get_position()

        scan_info = { 'start_pos' : position,
                      'ext_storage_dir': self.cfg.ext_storage_dir,
                      'local_storage_dir': self.cfg.local_storage_dir,
                      'subject_id': self.cfg.subject_id,
                      'tile_prefix': self.cfg.tile_prefix,
                      'volume_x_um': self.cfg.volume_x_um,
                      'volume_y_um': self.cfg.volume_y_um,
                      'volume_z_um': self.cfg.volume_z_um
        }

        self.acquisition_order[scan_info['subject_id']] = scan_info
        new_scan = QAction(f'Scan {len(self.acquisition_order)}: {scan_info["subject_id"]}', self.start_image_qwidget)
        new_scan.triggered.connect(lambda pressed = True, info = self.acquisition_order[scan_info['subject_id']]: self.configure_scan(pressed, info))
        self.volumetric_image['start'].addAction(new_scan)

    def configure_scan(self, pressed, info:dict):
        """View and edit previously setup scans"""

        inputs = {}
        for k, v in info.items():
            label = QLabel(str(k))
            text = QTextEdit(str(v))
            inputs[k] = self.create_layout('H', label=label, text=text)
        cancel_ok = QDialogButtonBox(QDialogButtonBox.Ok| QDialogButtonBox.Cancel| QDialogButtonBox.Discard)
        dialog = QDialog()
        layout = QVBoxLayout()
        for arg in inputs.values():
            layout.addWidget(arg)
        layout.addWidget(cancel_ok)
        dialog.setLayout(layout)
        cancel_ok.accepted.connect(dialog.accept)
        cancel_ok.rejected.connect(dialog.reject)

        result = dialog.exec()
        if result == 0: # Cancel button pressed
            return
        new_info = {}
        for k, v in inputs.items():
            if k == 'start_pos':
                new_info[k] = json.loads(v.children()[2].toPlainText().replace("'", '"')) # save as dict
            else:
                value_type = type(getattr(self.cfg, k))
                new_info[k] = value_type(v.children()[2].toPlainText())
        if new_info != info:
            #Find the old key where old info is saved
            old_key = list(self.acquisition_order.keys())[list(self.acquisition_order.values()).index(info)]
            del self.acquisition_order[old_key]

            # Update with new info
            self.acquisition_order[new_info['subject_id']] = new_info

    def scan_popup(self, widgets):
        """Create QDialog box for checking configured scans"""



    def run_volumeteric_imaging(self):

        if self.instrument.livestream_enabled.is_set():
            self.error_msg('Livestream', 'Livestream is still set. Please stop livestream')

        if [int(x) for x in self.cfg.imaging_wavelengths].sort() != [int(x) for x in self.instrument.channel_gene.keys()].sort() or \
                None in self.instrument.channel_gene.values() or '' in self.instrument.channel_gene.values():
            self.error_msg('Genes', 'Genes for cheannels are unspecified. '
                                    'Enter genes in the text box next to power '
                                    'slider to continue to scan.')
            return

        if self.volumetric_image['overwrite'].isChecked():
            return_value = self.overwrite_warning()
            if return_value == QMessageBox.Cancel:
                return

        return_value = self.scan_summary()
        if return_value == QMessageBox.Cancel:
            return

        for i in range(1,len(self.tab_widget)):
            self.tab_widget.setTabEnabled(i,False)
        self.instrument.cfg.save()

        #sleep(5)        # Allow threads to fully stop before starting scan
        self.run_worker = self._run()
        self.run_worker.finished.connect(lambda: self.end_scan())  # Napari threads have finished signals
        self.run_worker.start()

        #sleep(5)
        self.viewer.layers.clear()     # Clear existing layers
        self.volumetric_image_worker = create_worker(self.instrument._acquisition_livestream_worker)
        self.volumetric_image_worker.yielded.connect(self.update_layer)
        self.volumetric_image_worker.start()

        #sleep(5)
        self.progress_worker = self._progress_bar_worker()
        self.progress_worker.start()

    @thread_worker
    def _run(self):

        sleep(5)
        self.instrument.run(overwrite=self.volumetric_image['overwrite'].isChecked())


    def end_scan(self):

        self.run_worker.quit()
        self.volumetric_image_worker.quit()
        self.progress_worker.quit()
        QtCore.QMetaObject.invokeMethod(self.progress['bar'], f'setValue', QtCore.Q_ARG(int, round(100)))
        for i in range(1,len(self.tab_widget)):
            self.tab_widget.setTabEnabled(i,True)

    def progress_bar_widget(self):

        self.progress['bar'] = QProgressBar()
        self.progress['bar'].setStyleSheet('QProgressBar::chunk {background-color: green;}')
        self.progress['bar'].setHidden(True)

        self.progress['end_time'] = QLabel()
        self.progress['end_time'].setHidden(True)

        return self.create_layout(struct='H', **self.progress)

    @thread_worker
    def _progress_bar_worker(self):
        """Displays progress bar of the current scan"""

        QtCore.QMetaObject.invokeMethod(self.progress['bar'], 'setHidden', QtCore.Q_ARG(bool, False))
        QtCore.QMetaObject.invokeMethod(self.progress['end_time'], 'setHidden', QtCore.Q_ARG(bool, False))
        QtCore.QMetaObject.invokeMethod(self.progress['bar'], 'setValue', QtCore.Q_ARG(int, 0))
        while self.instrument.total_tiles == None or self.instrument.est_run_time == None:
            yield
            sleep(.5)
        # Calculate total tiles within all stacks
        if self.cfg.acquisition_style == 'interleaved' and not self.instrument.overview_set.is_set():
            total_tiles = self.instrument.total_tiles*len(self.cfg.imaging_wavelengths)
            z_tiles = total_tiles / self.instrument.x_y_tiles
            time_scale = self.instrument.x_y_tiles/86400
        else:
            total_tiles = self.instrument.total_tiles * (len(self.cfg.imaging_wavelengths))^2
            z_tiles = self.instrument.total_tiles/self.instrument.x_y_tiles
            time_scale = (self.instrument.x_y_tiles * len(self.cfg.imaging_wavelengths))/86400

        pct = 0
        while self.instrument.total_tiles != None:
            pct = (self.instrument.latest_frame_layer+(self.instrument.tiles_acquired*z_tiles))/total_tiles \
                if self.instrument.latest_frame_layer != 0 else pct
            QtCore.QMetaObject.invokeMethod(self.progress['bar'], f'setValue', QtCore.Q_ARG(int, round(pct*100)))
            yield
            # Qt threads are so weird. Can't invoke repaint method outside of main thread and Qthreads don't play nice
            # with napari threads so QMetaObject is static read-only instances

            if self.instrument.tiles_acquired == 0:
                yield
                completion_date = self.instrument.start_time + timedelta(days=self.instrument.est_run_time)

            else:
                yield
                total_time_days = self.instrument.tile_time_s*time_scale
                completion_date = self.instrument.start_time + timedelta(days=total_time_days)

            date_str = completion_date.strftime("%d %b, %Y at %H:%M %p")
            weekday = calendar.day_name[completion_date.weekday()]
            self.progress['end_time'].setText(f"End Time: {weekday}, {date_str}")
            yield
            yield  # So thread can stop

    def scan_summary(self):

        x, y, z = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                           self.cfg.tile_overlap_y_percent,
                                                           self.cfg.z_step_size_um,
                                                           self.cfg.volume_x_um,
                                                           self.cfg.volume_y_um,
                                                           self.cfg.volume_z_um)
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(f"Scan Summary\n"
                       f"Lasers: {self.cfg.imaging_wavelengths}\n"
                       f"Time: {round(self.instrument.acquisition_time(x, y, z), 3)} days\n"
                       f"X Tiles: {x}\n"
                       f"Y Tiles: {y}\n"
                       f"Z Tiles: {z}\n"
                       f"Local Dir: {self.cfg.local_storage_dir}\n"
                       f"External Dir: {self.cfg.ext_storage_dir}\n"
                       f"Press cancel to abort run")
        msgBox.setWindowTitle("Scan Summary")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def overwrite_warning(self):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText("Running Acquisition will overwrite files. Are you sure you want to do this?")
        msgBox.setWindowTitle("Overwrite Files")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def waveform_graph(self):

        """Generate a graph of waveform for sanity check"""
        # TODO: change colors and make it a different pop up window. As of now it will interfere with widget placement
        self.waveform['generate'] = QPushButton('Generate Waveforms')
        self.colors = np.random.randint(0, 255,
                                        [12, 3])  # rework this so the colors are set and laser colors are consistent
        self.waveform['graph'] = PlotWidget()
        self.waveform['generate'].clicked.connect(self.waveform_update)

        return self.waveform['generate']

    def waveform_update(self):
        t, voltages_t = generate_waveforms(self.cfg, self.cfg.imaging_wavelengths)

        self.waveform['graph'].clear()
        for index, ao_name in enumerate(self.cfg.daq_ao_names_to_channels.keys()):
            self.waveform['graph'].addLegend(offset=(365, .5), horSpacing=20, verSpacing=0, labelTextSize='8pt')
            self.waveform['graph'].plot(t, voltages_t[index], name=ao_name,
                                        pen=mkPen(color=self.colors[index], width=3))
        try:
            self.viewer.window.remove_dock_widget(self.waveform['graph'])
        except LookupError:
            pass
        finally:
            self.viewer.window.add_dock_widget(self.waveform['graph'])






