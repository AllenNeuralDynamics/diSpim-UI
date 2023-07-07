from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, \
    QSlider, QLineEdit,QMessageBox, QTabWidget, QProgressBar
import numpy as np
from pyqtgraph import PlotWidget, mkPen
from ispim.compute_waveforms import generate_waveforms
import logging
from napari.qt.threading import thread_worker, create_worker
from time import sleep, time
from datetime import timedelta, datetime
import calendar
from  qtpy.QtGui import QOffscreenSurface
import qtpy.QtCore as QtCore
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

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget

    def volumeteric_imaging_button(self):

        self.volumetric_image = {'start': QPushButton('Start Volumetric Imaging'),
                                 'overwrite': QCheckBox('Overwrite'),
                                 'save_config': QPushButton('Save Configuration')}
        self.volumetric_image['start'].clicked.connect(self.run_volumeteric_imaging)
        self.volumetric_image['save_config'].clicked.connect(self.instrument.cfg.save)
        # Put in seperate function so upon initiation of gui, run() funtion does not start

        return self.create_layout(struct='H', **self.volumetric_image)

    def run_volumeteric_imaging(self):

        if self.volumetric_image['overwrite'].isChecked():
            return_value = self.overwrite_warning()
            if return_value == QMessageBox.Cancel:
                return

        for i in range(1,len(self.tab_widget)):
            self.tab_widget.setTabEnabled(i,False)
        self.instrument.cfg.save()
        self.run_worker = self._run()
        self.run_worker.finished.connect(lambda: self.end_scan())  # Napari threads have finished signals
        self.run_worker.start()

        sleep(5)
        self.viewer.layers.clear()     # Clear existing layers
        self.volumetric_image_worker = create_worker(self.instrument._acquisition_livestream_worker)
        self.volumetric_image_worker.yielded.connect(self.update_layer)
        self.volumetric_image_worker.start()

        sleep(5)
        self.progress_worker = self._progress_bar_worker()
        self.progress_worker.start()

    @thread_worker
    def _run(self):
        self.instrument.run(overwrite=self.volumetric_image['overwrite'].isChecked())
        yield
    def end_scan(self):

        self.run_worker.quit()
        self.volumetric_image_worker.quit()
        self.progress_worker.quit()
        QtCore.QMetaObject.invokeMethod(self.progress['bar'], f'setValue', QtCore.Q_ARG(int, round(100)))

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
            # Qt threads are so weird. Can't invoke repaint method outside of main thread and Qthreads don't play nice
            # with napari threads so QMetaObject is static read-only instances

            if self.instrument.tiles_acquired == 0:
                completion_date = self.instrument.start_time + timedelta(days=self.instrument.est_run_time)

            else:
                total_time_days = self.instrument.tile_time_s*time_scale
                completion_date = self.instrument.start_time + timedelta(days=total_time_days)

            date_str = completion_date.strftime("%d %b, %Y at %H:%M %p")
            weekday = calendar.day_name[completion_date.weekday()]
            self.progress['end_time'].setText(f"End Time: {weekday}, {date_str}")
            sleep(.5)
            yield  # So thread can stop

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






