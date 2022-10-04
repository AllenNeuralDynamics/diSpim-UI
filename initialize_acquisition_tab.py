from tab import Tab
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget
import qtpy.QtGui as QtGui
import qtpy.QtCore as QtCore
from napari.qt.threading import thread_worker
from time import sleep
import numpy as np
from skimage.io import imsave
from pyqtgraph import PlotWidget, mkPen
from dispim.compute_waveforms import generate_waveforms
from clickable_spin_box import ClickableSpinBox

class InitializeAcquisitionTab(Tab):

    def __init__(self, wavelengths: list, possible_wavelengths: list, viewer, cfg, instrument):

        """ :param wavelengths: current list of wavelengths used in acqusistion
            :param possible_wavelengths: all possible laser wavelengths in instrument
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used"""

        self.imaging_wavelengths = wavelengths
        self.possible_wavelengths = possible_wavelengths
        self.viewer = viewer
        self.cfg = cfg
        self.instrument = instrument

        self.pos_widget = {}
        self.wavelength_selection = {}
        self.live_view = {}
        self.waveform = {}
        self.selected = {}
        self.laser_dock = {}
        self.wavelength_select_widget = None
        self.colors = None
        self.livestream_worker = None
        self.stage_position = None
        self.data_line = None
        self.selected_wl_layout = None

    def live_view_widget(self):

        """Contains button to activate livestream as well as selection of laser, autocontrast and rotation of
        liveview """

        self.live_view['start'] = QPushButton('Start Live View')
        self.live_view['start'].clicked.connect(self.start_live_view)

        wv_strs = [str(x) for x in self.possible_wavelengths]
        self.live_view['wavelength'] = QComboBox()
        self.live_view['wavelength'].addItems(wv_strs)
        self.live_view['wavelength'].currentIndexChanged.connect(self.color_change)

        i = 0
        for wavelength in wv_strs:
            self.live_view['wavelength'].setItemData(i, QtGui.QColor(self.cfg.laser_specs[wavelength]['color']),
                                                     QtCore.Qt.BackgroundRole)
            i += 1
        self.live_view['wavelength'].setStyleSheet(
            'QComboBox { background-color:' + self.cfg.laser_specs[wv_strs[0]]['color'] + '; color : black; }')
        self.live_view['autocontrast'] = QCheckBox('Autocontrast')
        self.live_view['autocontrast'].setChecked(True)
        self.live_view['rotate'] = QCheckBox('Rotate')
        self.live_view['rotate'].setChecked(True)

        return self.create_layout(struct='H', **self.live_view)

    def start_live_view(self):

        if self.live_view['start'].text() == 'Start Live View':
            self.live_view['start'].setText('Stop Live View')
            self.live_view['start'].clicked.disconnect(self.start_live_view)
            self.live_view['start'].clicked.connect(self.stop_live_view)

        self.instrument.start_livestream(int(self.live_view['wavelength'].currentText()))
        self.livestream_worker = self._livestream_worker()
        self.livestream_worker.yielded.connect(self.update_layer)
        self.livestream_worker.start()

    def stop_live_view(self):
        self.instrument.stop_livestream()
        self.livestream_worker.quit()
        self.live_view['start'].setText('Start Live View')
        self.live_view['start'].clicked.disconnect(self.stop_live_view)
        self.live_view['start'].clicked.connect(self.start_live_view)

    @thread_worker
    def _livestream_worker(self):
        while True:
            try:
                sleep(1 / 16)
                yield self.instrument.get_latest_img()

            except IndexError:
                pass

    def update_layer(self, image):

        # if self.live_view['autocontrast'].isChecked():
        #     image = self.instrument.apply_contrast(image)
        if self.live_view['rotate'].isChecked():
            image = np.rot90(image, -1)

        try:
            self.viewer.layers['Live View'].data = image
        except KeyError:
            self.viewer.add_image(image, name='Live View', scale=(1, 1))
            vert_line = np.array([[0, 0], [self.cfg.column_count_px, 0]])
            horz_line = np.array([[0, 0], [0, self.cfg.row_count_px]])
            lines = [vert_line, horz_line]
            color = ['blue', 'green']
            shapes_layer = self.viewer.add_shapes(
                lines, shape_type='line', edge_width=20, edge_color=color)
            shapes_layer.mode = 'select'

            @shapes_layer.mouse_drag_callbacks.append
            def click_drag(layer, event):
                data_coordinates = layer.world_to_data(event.position)
                val = layer.get_value(data_coordinates)
                yield
                # on move
                while event.type == 'mouse_move':
                    if val == (0, None) and self.cfg.column_count_px >= event.position[1] >= 0:  #vert_line
                        layer.data = [[[0, event.position[1]], [self.cfg.column_count_px, event.position[1]]],
                                      layer.data[1]]
                        layer.data = [layer.data[0],
                                      [[event.position[0], 0], [event.position[0], self.cfg.row_count_px]]]
                        yield
                    elif val == (1, None) and self.cfg.row_count_px >= event.position[0] >= 0:  #horz_line
                        layer.data = [[[0, event.position[1]], [self.cfg.column_count_px, event.position[1]]],
                                      layer.data[1]]
                        layer.data = [layer.data[0],
                                      [[event.position[0], 0], [event.position[0], self.cfg.row_count_px]]]
                        yield
                    else:
                        yield

    def color_change(self):
        wavelength = int(self.live_view['wavelength'].currentText())
        self.live_view['wavelength'].setStyleSheet(
            'QComboBox { background-color:' + self.cfg.laser_specs[str(wavelength)]['color'] + '; color : black; }')

    def screenshot_button(self):

        """Button that will take a screenshot of liveviewer"""
        # TODO: Add a way to specify where you want png to be saved

        screenshot_b = QPushButton()
        screenshot_b.setText('Screenshot')
        screenshot_b.clicked.connect(self.take_screenshot)
        return screenshot_b

    def take_screenshot(self):

        if self.viewer.layers != []:
            screenshot = self.viewer.screenshot()
            self.viewer.add_image(screenshot)
            imsave('screenshot.png', screenshot)
        else:
            self.error_msg('Screenshot', 'No image to screenshot')

    def sample_stage_position(self):

        """Creates labels and boxs to indicate sample position"""
        # TODO: Get this working at all and also figure out which coordinates field it represents

        directions = ['X', 'Y', 'Z']
        self.pos_widget = {}
        self.stage_position = self.instrument.get_sample_position()
        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction], ClickableSpinBox, f'{direction}:')
            self.pos_widget[direction].valueChanged.connect(self.stage_position_changed)
            self.pos_widget[direction].clicked.connect(self.update_sample_pos)


        return self.create_layout(struct='H', **self.pos_widget)

    def update_sample_pos(self):
        """Update position widgets for volumetric imaging or manually moving"""
        print('clicked')
        sample_pos = self.instrument.get_sample_position()
        for direction, value in sample_pos.items():
            if direction in self.pos_widget:
                self.pos_widget[direction].setValue(value)

    def stage_position_changed(self):
        self.instrument.move_sample_relative(self.pos_widget['X'].value(), self.pos_widget['Y'].value(),
                                             self.pos_widget['Z'].value())

    def volumeteric_imaging_button(self):

        volumetric_image = {'start': QPushButton('Start Volumetric Imaging')}
        volumetric_image['start'].clicked.connect(self.start_volumetric_imaging)
        # volumetric_image['overwrite'] = QCheckBox('Overwrite Data')
        # volumetric_image['overwrite'].setChecked(True)

        return self.create_layout(struct='H', **volumetric_image)

    def start_volumetric_imaging(self):

        self.sample_pos_worker = self._sample_pos_worker()
        self.sample_pos_worker.yielded.connect(self.update_sample_pos)
        self.sample_pos_worker.start()

        self.volumetric_worker = self._volumetric_worker()
        self.volumetric_worker.start()
        # overwrite=self.volumetric_image['overwrite'].isChecked()

    @thread_worker
    def _volumetric_worker(self):

        self.instrument.run_from_config()

    @thread_worker
    def _sample_pos_worker(self):
        while self.instrument.volumetric_imaging.is_set():
            yield self.instrument.get_sample_position()

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
        t, voltages_t = generate_waveforms(self.cfg, int(self.live_view['wavelength'].currentText()))
        try:
            for index, ao_name in enumerate(self.cfg.daq_ao_names_to_channels.keys()):
                self.data_line.setData(t, voltages_t[index], name=ao_name, pen=mkPen(color=self.colors[index]))
            self.viewer.window.remove_dock_widget(self.waveform['graph'])
            self.viewer.window.add_dock_widget(self.waveform['graph'])
        except:
            for index, ao_name in enumerate(self.cfg.daq_ao_names_to_channels.keys()):
                # self.waveform['graph'].setFixedWidth(500)
                # self.waveform['graph'].setFixedHeight(250)
                self.waveform['graph'].setTitle("Waveforms One Image Capture Sequence", color="w", size="10pt")
                self.waveform['graph'].setLabel('bottom', 'Time (s)')
                self.waveform['graph'].setLabel('left', 'Amplitude (V)')
                self.waveform['graph'].setXRange(0, .03)
                self.data_line = self.waveform['graph'].plot(t, voltages_t[index], name=ao_name,
                                                             pen=mkPen(color=self.colors[index], width=3))
                self.waveform['graph'].addLegend(offset=(365, .5), horSpacing=20, verSpacing=0, labelTextSize='8pt')
            self.viewer.window.add_dock_widget(self.waveform['graph'])

    def laser_wl_select(self):

        """Adds a dropdown box with the laser wavelengths that are not selected for the current acquisition based on
        config. Selecting a wavelength adds the wavelength to the lasers to be used during acquisition. To remove a
        wavelength, click on the resultant label"""

        self.wavelength_selection['unselected'] = QComboBox()
        remaining_wavelengths = [str(wavelength) for wavelength in self.possible_wavelengths if
                                 not wavelength in self.imaging_wavelengths]

        remaining_wavelengths.insert(0, '')
        self.wavelength_selection['unselected'].addItems(remaining_wavelengths)
        self.wavelength_selection['unselected'].activated.connect(self.unhide_labels)
        # Adds a 'label' (QPushButton) for every possible wavelength then hides the unselected ones.
        # Pushing labels should hide them and selecting QComboBox should unhide them
        self.wavelength_selection['selected'] = self.selected_wv_label()
        return self.create_layout('H', **self.wavelength_selection)

    def selected_wv_label(self):

        """Adds labels for all possible wavelengths"""

        for wavelengths in self.possible_wavelengths:
            wavelengths = str(wavelengths)
            self.selected[wavelengths] = QPushButton(wavelengths)
            color = self.cfg.laser_specs[wavelengths]
            self.selected[wavelengths].setStyleSheet('QPushButton { background-color:' + color['color'] + '; color : '
                                                                                                          'black; }')
            self.selected[wavelengths].clicked.connect(lambda clicked=None, widget=self.selected[wavelengths]:
                                                       self.hide_labels(clicked, widget))
            if int(wavelengths) not in self.imaging_wavelengths:
                self.selected[wavelengths].setHidden(True)
        self.selected_wl_layout = self.create_layout(struct='H', **self.selected)
        return self.selected_wl_layout

    def hide_labels(self, clicked, widget):
        widget_wavelength = widget.text()
        widget.setHidden(True)
        self.laser_dock[widget_wavelength].setHidden(True)
        self.imaging_wavelengths.remove(int(widget_wavelength))
        self.wavelength_selection['unselected'].addItem(widget.text())

    def unhide_labels(self):
        index = self.wavelength_selection['unselected'].currentIndex()
        if index != 0:
            widget_wavelength = self.wavelength_selection['unselected'].currentText()
            self.imaging_wavelengths.append(int(widget_wavelength))
            self.wavelength_selection['unselected'].removeItem(index)
            self.selected[widget_wavelength].setHidden(False)
            self.laser_dock[widget_wavelength].setHidden(False)

    def adding_wavelength_tabs(self, imaging_dock):
        for wavelength in self.possible_wavelengths:
            wavelength = str(wavelength)
            main_dock = QDockWidget()
            main_dock.setWindowTitle('Laser ' + wavelength)
            main_dock = self.scan_wavelength_params(wavelength)
            self.laser_dock[wavelength] = self.viewer.window.add_dock_widget(main_dock, name='Wavelength ' + wavelength)
            self.viewer.window._qt_window.tabifyDockWidget(imaging_dock, self.laser_dock[wavelength])
            if int(wavelength) not in self.imaging_wavelengths:
                self.laser_dock[wavelength].setHidden(True)

    def scan_wavelength_params(self, wavelength: str):
        """Scans config for relevant laser wavelength parameters
        :param wavelength: the wavelength of the laser"""

        laser_specs_wavelength = self.cfg.laser_specs[wavelength]
        tab_widget_wl = self.scan(laser_specs_wavelength, 'laser_specs', wl=wavelength, subdict=True)
        return self.create_layout(struct='V', **tab_widget_wl)
