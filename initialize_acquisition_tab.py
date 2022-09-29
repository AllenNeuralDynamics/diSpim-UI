from tab import Tab
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox
import qtpy.QtGui as QtGui
import qtpy.QtCore as QtCore
from napari.qt.threading import thread_worker
from time import sleep
import numpy as np
from skimage.io import imsave
from pyqtgraph import PlotWidget, mkPen
from dispim.compute_waveforms import generate_waveforms


class InitializeAcquisitionTab(Tab):

    def __init__(self, wavelengths: list, possible_wavelengths: list, viewer, cfg, instrument):

        """ :param wavelengths: current list of wavelengths used in acqusistion
            :param possible_wavelengths: all possible laser wavelengths in instrument
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used"""

        self.wavelengths = wavelengths
        self.possible_wavelengths = possible_wavelengths
        self.viewer = viewer
        self.cfg = cfg
        self.instrument = instrument

        self.pos_widget = {}
        self.wavelength_selection = {}
        self.live_view = {}
        self.waveform = {}
        self.wavelength_select_widget = None
        self.colors = None
        self.livestream_worker = None
        self.stage_position = None
        self.data_line = None

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

        if self.live_view['autocontrast'].isChecked():
            image = self.instrument.apply_contrast(image)
        if self.live_view['rotate'].isChecked():
            image = np.rot90(image, -1)

        try:
            self.viewer.layers['Live View'].data = image
        except KeyError:
            self.viewer.add_image(image, name='Live View', scale=(1, 1))
            vert_line = np.array([[0, 0], [2048, 0]])
            horz_line = np.array([[0, 0], [0, 2048]])
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
                    layer.data = [[[0, event.position[1]], [2048, event.position[1]]], layer.data[1]]
                    if val == (0, None) and 2048 >= event.position[1] >= 0:  # Conditions for vert_line
                        layer.data = [[[0, event.position[1]], [2048, event.position[1]]], layer.data[1]]
                        yield
                    elif val == (1, None) and 2048 >= event.position[0] >= 0:  # Conditions for horz_line
                        layer.data = [layer.data[0], [[event.position[0], 0], [event.position[0], 2048]]]
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
        self.stage_position = self.instrument.sample_pose.get_position()
        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = self.stage_indicator(direction)
            # self.pos_widget[direction].valueChanged.connect(self.stage_position_changed)

        return self.create_layout(struct='H', **self.pos_widget)

    def stage_indicator(self, direction):

        """Creates label and indicators for sample stage position"""

        pos_label = QLabel()
        pos_label.setText(direction + ' position: ')
        f = pos_label.font()
        f.setPointSize(7)
        pos_label.setFont(f)
        pos_value = QSpinBox()
        pos_value.setValue(self.stage_position[direction])
        #pos_value.setFixedWidth(20)
        return pos_label, pos_value

    def volumeteric_imaging_button(self):

        volumetric_image = {'start': QPushButton('Start Volumetric Imaging')}
        volumetric_image['start'].clicked.connect(self.start_volumetric_imaging)
        #volumetric_image['overwrite'] = QCheckBox('Overwrite Data')
        #volumetric_image['overwrite'].setChecked(True)

        return self.create_layout(struct='H', **volumetric_image)

    def start_volumetric_imaging(self):

        self.instrument.run_from_config()
        # overwrite=self.volumetric_image['overwrite'].isChecked()

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
                #self.waveform['graph'].setFixedWidth(500)
                #self.waveform['graph'].setFixedHeight(250)
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
        remaining_wavelengths = [wavelength for wavelength in self.possible_wavelengths if
                                 not wavelength in self.wavelengths]
        rem_wl_str = [str(x) for x in remaining_wavelengths]
        rem_wl_str.insert(0, '')
        self.wavelength_selection['unselected'].addItems(rem_wl_str)
        self.wavelength_selection['unselected'].activated.connect(self.add_selected_wl)
        self.wavelength_selection['selected'] = self.selected_wv_label(self.wavelengths)
        self.wavelength_select_widget = self.create_layout('H', **self.wavelength_selection)
        self.viewer.window.add_dock_widget(self.wavelength_select_widget, name='Selected Laser Wavelengths')

    def selected_wv_label(self, selected_wl):
        selected_wl_labels = [QPushButton(str(wavelength)) for wavelength in selected_wl]
        selected_labels_dict = {}
        i = 0
        for labels, wavelengths in zip(selected_wl_labels, selected_wl):
            labels.setStyleSheet('QPushButton { background-color:' +
                                 self.cfg.laser_specs[str(wavelengths)]['color'] +
                                 '; color : black; }')

            labels.clicked.connect(lambda clicked=None, widget=labels: self.remove_selected_wl(clicked, widget))
            selected_labels_dict[str(wavelengths)] = labels
            i += 1

        return self.create_layout(struct='H', **selected_labels_dict)

    def add_selected_wl(self):

        """If unselected wavelengths are pressed, the selected wavelength labels are updated"""

        index = self.wavelength_selection['unselected'].currentIndex()
        if index != 0:
            self.viewer.window.remove_dock_widget(self.wavelength_select_widget)
            self.wavelengths.append(int(self.wavelength_selection['unselected'].currentText()))
            self.wavelength_selection['selected'] = self.selected_wv_label(self.wavelengths)
            self.wavelength_selection['unselected'].removeItem(index)

            self.wavelength_select_widget = self.create_layout('H', **self.wavelength_selection)
            self.viewer.window.add_dock_widget(self.wavelength_select_widget, name='Selected Laser Wavelengths')

    def remove_selected_wl(self, clicked, widget):

        """If laser wavelength labels are clicked they are removed from config and gui"""

        self.viewer.window.remove_dock_widget(self.wavelength_select_widget)
        self.wavelength_selection['unselected'].addItem(widget.text())
        self.wavelengths.remove(int(widget.text()))
        self.wavelength_selection['selected'] = self.selected_wv_label(self.wavelengths)
        self.wavelength_select_widget = self.create_layout('H', **self.wavelength_selection)
        self.viewer.window.add_dock_widget(self.wavelength_select_widget, name='Selected Laser Wavelengths')
