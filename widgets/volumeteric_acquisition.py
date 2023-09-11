from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, \
    QSlider, QLineEdit,QMessageBox, QTabWidget, QProgressBar, QToolButton, QMenu, QAction, QDialog, QWidget, QTextEdit, \
    QVBoxLayout,QDialogButtonBox, QTableWidget, QTableWidgetItem, QWidgetAction, QToolBar
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
        self.delete_scan_bt = {}
        self.cells_changed = []
        self.scans = []     # Scans performed in the UI instance

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget

    def volumeteric_imaging_button(self):

        self.volumetric_image = {'start': QToolButton(),
                                 'overwrite': QCheckBox('Overwrite'),
                                 'save_config': QPushButton('Save Configuration')}
        self.volumetric_image['start'].pressed.connect(self.run_volumeteric_imaging)
        self.volumetric_image['save_config'].clicked.connect(self.instrument.cfg.save)
        # # Put in seperate function so upon initiation of gui, run() funtion does not start

        self.start_image_qwidget = self.create_layout('H', **self.volumetric_image)
        self.volumetric_image['start'].setText('Start Volumeteric Image')
        self.volumetric_image['start'].setStyleSheet(
            "QToolButton{"
            "background-color: rgb(65, 72, 81);"    # Napari dark theme foreground
            "}"
            "QToolButton:pressed{"
            "background-color: rgb(38, 41, 48);"    # Napari dark theme background
            "}"
        )

        # Create dropdown menu for qtoolbutton
        menu = QMenu(self.volumetric_image['start'])
        add_scan = QAction("Add Scan", self.start_image_qwidget)
        add_scan.triggered.connect(self.setup_additional_scan)
        menu.addAction(add_scan)
        # Create table widget
        col_headers = ['start_pos_um' ,'ext_storage_dir','local_storage_dir','subject_id','tile_prefix','volume_x_um',
                      'volume_y_um','volume_z_um','channels', '']
        self.scan_table_widget = QTableWidget()
        self.scan_table_widget.setColumnCount(10)
        self.scan_table_widget.setHorizontalHeaderLabels(col_headers)
        self.scan_table_widget.setRowCount(0)
        # Create a QAction to put scan table in menu
        table = QWidgetAction(self.start_image_qwidget)
        table.setDefaultWidget(self.scan_table_widget)
        menu.addAction(table)
        # Set menu
        menu.setMinimumWidth(920)
        self.volumetric_image['start'].setMenu(menu)
        self.volumetric_image['start'].setPopupMode(QToolButton.MenuButtonPopup)

        menu.aboutToHide.connect(self.configure_scans)
        self.scan_table_widget.itemChanged.connect(self.table_items_changed)

        return self.start_image_qwidget

    def setup_additional_scan(self):
        """Add scan to imaging run"""

        with self.instrument.stage_query_lock:
            position = self.instrument.sample_pose.get_position()

        scan_info = { 'start_pos_um' : {k:round(1/10*v,1) for k,v in position.items()},
                      'ext_storage_dir': self.cfg.ext_storage_dir,
                      'local_storage_dir': self.cfg.local_storage_dir,
                      'subject_id': self.cfg.subject_id,
                      'tile_prefix': self.cfg.tile_prefix,
                      'volume_x_um': self.cfg.volume_x_um,
                      'volume_y_um': self.cfg.volume_y_um,
                      'volume_z_um': self.cfg.volume_z_um,
                      'channels': self.cfg.imaging_wavelengths
        }
        # Check if scan is will exceed stage limits. Will use config values and current pos
        if self.exceed_stage_limit_check():
            return
        # Add scan to acquisition dictionary
        self.acquisition_order[len(self.acquisition_order)] = scan_info
        self.scan_table_widget.insertRow(self.scan_table_widget.rowCount())
        row = self.scan_table_widget.rowCount()-1
        i = 0
        for v in scan_info.values():
            self.scan_table_widget.setItem(row, i, QTableWidgetItem(str(v)))
            i += 1

        # create a delete button
        self.table_delete_button(row)

        self.cells_changed = [] # Reset cells changed to ignore items added

    def remove_scan(self, pushed, row):
        """Remove scan of row where button was pushed and reconfigures acquisition order"""
        for i in self.cells_changed:
            if i[0] == row:self.cells_changed.remove(i)
        self.configure_scans()  # Check cells before rows change but ignore ones being deleted
        self.scan_table_widget.removeRow(row)
        del self.acquisition_order[row]  # delete scan
        keys = list(self.acquisition_order.keys())
        for i in keys: # Shift dictionary and cells to match rows
            if i < row: continue
            self.acquisition_order[i-1] = self.acquisition_order[i]
            self.scan_table_widget.removeCellWidget(i-1, len(self.acquisition_order[i]))  # Remove delete button
            self.table_delete_button(i-1) # create a delete button

    def table_delete_button(self, row):
        """Convenient function for creating delete button at certain row in scan_table_widget"""

        delete = QPushButton(self.scan_table_widget)
        delete.setText('Delete')
        self.scan_table_widget.setCellWidget(row, self.scan_table_widget.columnCount()-1, delete)
        delete.clicked.connect(lambda pushed=True, row=row: self.remove_scan(pushed, row))

    def table_items_changed(self, cell):
        """Function to keep track of changes made in scan_table widget"""

        self.cells_changed.append((cell.row(), cell.column()))

    def configure_scans(self):
        """View and edit previously setup scans"""

        for cell in self.cells_changed:
            key = self.scan_table_widget.horizontalHeaderItem(cell[1]).text()
            scan_num = cell[0]
            # Check to see if inputs make sense
            try:
                cell_value = self.scan_table_widget.item(cell[0], cell[1]).text()
                if key == 'start_pos_um':
                    new_value = json.loads(cell_value.replace("'", '"'))  # save as dict
                    if self.exceed_stage_limit_check(new_value, {'x': self.acquisition_order[scan_num]['volume_x_um'],
                                                                 'y': self.acquisition_order[scan_num]['volume_y_um'],
                                                                 'z': self.acquisition_order[scan_num]['volume_z_um']}):
                        raise ValueError

                elif key == 'channels':
                    new_value = list(json.loads(cell_value.replace("'", '"')))  # save as or list
                    for wl in new_value:
                        if wl not in self.cfg.laser_wavelengths:    # check that wavelengths are valid
                            raise ValueError
                else:
                    value_type = type(getattr(self.cfg, key))
                    new_value = value_type(cell_value)

                self.acquisition_order[scan_num][key] = new_value

            except(ValueError, TypeError):
                self.error_msg('Error', f'Scan {scan_num} value {key} was invalid. Changes to were NOT saved.')
                self.scan_table_widget.item(cell[0], cell[1]).setText(str(self.acquisition_order[scan_num][key]))
                continue

        self.cells_changed = []     # reset changed cells to none

    def exceed_stage_limit_check(self, start_pos_um:dict = None, volume:dict = None):

        """Check if scan with parameters in the cfg will exceed stage limits
        :param start_pos_um: start position of scan in um"""

        with self.instrument.stage_query_lock:
            limits_mm = self.instrument.sample_pose.get_travel_limits(*['x', 'y', 'z'])
        limits_um = {k:[v[0]*1000,v[1]*1000] for k, v in limits_mm.items()}
        if start_pos_um == None:
            with self.instrument.stage_query_lock:
                start_pos = self.instrument.sample_pose.get_position()
            start_pos_um = {k:v/10 for k,v in start_pos.items()}
        limit_exceeded = []
        for k in limits_um.keys():
            end_pos = start_pos_um[k]+getattr(self.cfg, f'volume_{k}_um') \
                if volume ==None else start_pos_um[k] + volume[k]
            if not limits_um[k][0] < end_pos < limits_um[k][1] or not limits_um[k][0] < start_pos_um[k] < limits_um[k][1]:
                limit_exceeded.append(k)
        if limit_exceeded != []:
            self.error_msg('CAUTION', 'Starting stage at this position with '
                                      'these scan parameters will exceed stage '
                                      f'limits in these directions: {limit_exceeded}')
            return True
        return False

    def run_volumeteric_imaging(self):

        self.volumetric_image['start'].blockSignals(True)  # Block release signal so transferring json doesn't start

        if self.instrument.livestream_enabled.is_set():
            self.error_msg('Livestream', 'Livestream is still set. Please stop livestream')
            self.volumetric_image['start'].blockSignals(False)

        if [int(x) for x in self.cfg.imaging_wavelengths].sort() != [int(x) for x in self.instrument.channel_gene.keys()].sort() or \
                None in self.instrument.channel_gene.values() or '' in self.instrument.channel_gene.values():
            self.error_msg('Genes', 'Genes for channels are unspecified. '
                                    'Enter genes in the text box next to power '
                                    'slider to continue to scan.')
            self.volumetric_image['start'].blockSignals(False)
            return

        if self.volumetric_image['overwrite'].isChecked():
            return_value = self.overwrite_warning()
            if return_value == QMessageBox.Cancel:
                self.volumetric_image['start'].blockSignals(False)
                return

        if self.acquisition_order == {}:       # Add scan of current configuration if none are configured
            self.setup_additional_scan()
            return_value = self.scan_summary()
            if return_value == QMessageBox.Cancel:
                self.volumetric_image['start'].blockSignals(False)
                self.scan_table_widget.removeRow(0)
                self.acquisition_order = {}
                return

        else:
            for scan in self.acquisition_order.values():
                #Set up config for each scan
                for k, v in scan.items():
                    if k == 'start_pos_um':
                        self.instrument.set_scan_start({k1: 10 * v1 for k1, v1 in scan[k].items()})
                        print(self.instrument.start_pos)
                    else:
                        setattr(self.cfg, k, v)
                return_value = self.scan_summary()
                if return_value == QMessageBox.Cancel:

                    self.volumetric_image['start'].blockSignals(False)
                    return
        self.viewer.layers.clear()  # Clear existing layers
        self.volumetric_image_worker = create_worker(self.instrument._acquisition_livestream_worker)
        self.volumetric_image_worker.yielded.connect(self.update_layer)
        self.volumetric_image_worker.start()

        self.run_worker = self._run()
        self.run_worker.finished.connect(lambda: self.end_scan())  # Napari threads have finished signals
        self.run_worker.start()

    @thread_worker
    def _run(self):

        sleep(5)
        for scan in self.acquisition_order.values():
            #Set up config for each scan
            for k, v in scan.items():
                if k == 'start_pos_um':
                    self.instrument.set_scan_start({k1: 10 * v1 for k1, v1 in scan[k].items()})
                else:
                    setattr(self.cfg, k, v)

            for i in range(1,len(self.tab_widget)):
                self.tab_widget.setTabEnabled(i,False)
            self.instrument.cfg.save()

            self.progress_worker = self._progress_bar_worker()
            self.progress_worker.start()
            self.instrument.run(overwrite=self.volumetric_image['overwrite'].isChecked())
            dest = str(self.instrument.img_storage_dir) if self.instrument.img_storage_dir != None else str(self.instrument.local_storage_dir)
            self.scans.append(dest)
            self.volumetric_image['start'].blockSignals(False)
            self.volumetric_image['start'].released.emit()  # Signal that scans are done
            self.volumetric_image['start'].blockSignals(True)

    def end_scan(self):

        self.run_worker.quit()
        self.volumetric_image_worker.quit()
        self.progress_worker.quit()
        QtCore.QMetaObject.invokeMethod(self.progress['bar'], f'setValue', QtCore.Q_ARG(int, round(100)))
        for i in range(1,len(self.tab_widget)):
            self.tab_widget.setTabEnabled(i,True)
        self.volumetric_image['start'].blockSignals(False)

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
        if self.cfg.acquisition_style == 'interleaved' and not self.instrument.overview_set.is_set:
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

            if completion_date >= datetime.now():
                date_str = completion_date.strftime("%d %b, %Y at %H:%M %p")
                weekday = calendar.day_name[completion_date.weekday()]
                end_time = f'{weekday}, {date_str}'
            else:
                end_time = '¯\_(ツ)_/¯'
            self.progress['end_time'].setText(f"End Time: {end_time}")
            yield
            yield  # So thread can stop
        end_time = datetime.now().strftime("%d %b, %Y at %H:%M %p")
        self.progress['end_time'].setText(f"End Time: {end_time}")

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
                       f"Start (um): {self.instrument.start_pos if self.instrument.start_pos != None else self.instrument.sample_pose.get_position()}\n"
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






