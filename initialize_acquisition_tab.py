from tab import Tab
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider
import qtpy.QtGui as QtGui
import qtpy.QtCore as QtCore
from napari.qt.threading import thread_worker
from time import sleep
import numpy as np
from skimage.io import imsave
from pyqtgraph import PlotWidget, mkPen
from dispim.compute_waveforms import generate_waveforms
from oxxius_laser import Cmd, Query
from skimage import data, measure

class InitializeAcquisitionTab(Tab):

    def __init__(self,viewer, cfg, instrument, simulated):

        """ :param wavelengths: current list of wavelengths used in acqusistion
            :param possible_wavelengths: all possible laser wavelengths in instrument
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used"""

        self.cfg = cfg
        self.possible_wavelengths = self.cfg.cfg['imaging_specs']['possible_wavelengths']
        self.imaging_wavelengths = self.cfg.imaging_specs['laser_wavelengths']
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.pos_widget = {}
        self.wavelength_selection = {}
        self.live_view = {}
        self.waveform = {}
        self.selected = {}
        self.laser_dock = {}
        self.laser_power = {}
        self.wavelength_select_widget = None
        self.colors = None
        self.livestream_worker = None
        self.stage_position = None
        self.data_line = None
        self.selected_wl_layout = None

        self.layer_index = 0
        self.stream_id = 1
        # Start and end points for lines
        self.vert_start = -self.cfg.sensor_column_count
        self.vert_end = 0
        self.horz_start = -self.cfg.sensor_row_count
        self.horz_end = 0

        self.camera_id = ['Right', 'Left']


    def live_view_widget(self):

        """Contains button to activate livestream as well as selection of laser, autocontrast and rotation of
        liveview """

        self.live_view['start'] = QPushButton('Start Live View')
        self.live_view['start'].clicked.connect(self.start_live_view)

        self.live_view['0'] = QPushButton('Right Camera')
        self.live_view['0'].setStyleSheet("background-color : gray")
        self.live_view['0'].setHidden(True)
        self.live_view['0'].pressed.connect(lambda stream_id=0: self.camera_view(stream_id))

        self.live_view['1'] = QPushButton('Left Camera')
        self.live_view['1'].setStyleSheet("background-color : green")
        self.live_view['1'].setHidden(True)
        self.live_view['1'].pressed.connect(lambda stream_id=1: self.camera_view(stream_id))

        self.live_view['overlay'] = QPushButton('Overlay Camera Views')
        self.live_view['overlay'].setStyleSheet("background-color : gray")
        self.live_view['overlay'].setHidden(True)
        self.live_view['overlay'].clicked.connect(self.blending_set)

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
            f'QComboBox {{ background-color:{self.cfg.laser_specs[wv_strs[0]]["color"]}; color : black; }}')

        return self.create_layout(struct='H', **self.live_view)

    def camera_view(self, stream_id):

        self.stream_id = stream_id
        not_id = (stream_id + 1) % 2

        key = f"Video {self.camera_id[stream_id]}"
        not_key = f"Video {self.camera_id[not_id]}"

        self.viewer.layers[key].opacity = 1
        self.viewer.layers[not_key].opacity = 0
        self.live_view[str(stream_id)].setStyleSheet("background-color : green")
        self.live_view[str(not_id)].setStyleSheet("background-color : gray")
        self.live_view['overlay'].setStyleSheet("background-color : gray")

    def blending_set(self):

        self.viewer.layers[f"Video Left"].blending = self.viewer.layers[f"Video Right"].blending = 'additive'
        self.viewer.layers[f"Video Left"].opacity = self.viewer.layers[f"Video Right"].opacity = 1.0

        self.live_view['0'].setStyleSheet("background-color : gray")
        self.live_view['1'].setStyleSheet("background-color : gray")
        self.live_view['overlay'].setStyleSheet("background-color : green")

    def profile_lines(self, image, shape_layer):
        profile_data = [
            measure.profile_line(image, line[0], line[1], mode='reflect').mean()
            for line in shape_layer.data
        ]

        return profile_data

    def start_live_view(self):

        if self.live_view['start'].text() == 'Start Live View':
            self.live_view['start'].setText('Stop Live View')
            self.live_view['start'].clicked.disconnect(self.start_live_view)
            self.live_view['start'].clicked.connect(self.stop_live_view)
            self.live_view['overlay'].setHidden(False)
            self.live_view['1'].setHidden(False)
            self.live_view['0'].setHidden(False)

        self.instrument.start_livestream(int(self.live_view['wavelength'].currentText()))
        self.livestream_worker = self.instrument._livestream_worker()
        self.livestream_worker.yielded.connect(self.update_layer)
        self.livestream_worker.start()

    def stop_live_view(self):
        self.instrument.stop_livestream()
        self.livestream_worker.quit()
        self.live_view['start'].setText('Start Live View')
        self.live_view['start'].clicked.disconnect(self.stop_live_view)
        self.live_view['start'].clicked.connect(self.start_live_view)
        self.live_view['overlay'].setHidden(True)
        self.live_view['1'].setHidden(True)
        self.live_view['0'].setHidden(True)

    def update_layer(self, args):
        (image, stream_id) = args
        key = f"Video {self.camera_id[stream_id]}"
        try:

            layer = self.viewer.layers[key]
            layer._slice.image._view = image
            layer.events.set_data()

            profile_data = self.profile_lines(
                 self.viewer.layers[f'Video {self.camera_id[self.stream_id]}'].data, self.viewer.layers['lines'])
            self.viewer.layers['lines'].features = {'line_profile': [profile_data[0], profile_data[1]], }

        except KeyError:
            self.viewer.add_image(image, name=f"Video {self.camera_id[stream_id]}")
            self.layer_index += 1

            if self.layer_index == 2:

                self.viewer.layers['Video Right'].rotate = 90
                self.viewer.layers['Video Left'].rotate = 90

                vert_line = np.array([[self.vert_start, 0], [self.vert_end, 0]])
                horz_line = np.array([[0, 0], [0, self.cfg.sensor_row_count]])
                lines = [vert_line, horz_line]

                features = {'line_profile': [0,0],}
                color = ['blue', 'green']
                text = {'string': '{line_profile:0.1f}%','anchor': 'upper_right', 'translation': [0, 300], 'size': 8,
                        'color': 'white'}

                shapes_layer = self.viewer.add_shapes(
                    lines, shape_type='line', edge_width=20, edge_color=color, features=features, text=text, name='lines')
                shapes_layer.mode = 'select'

                @shapes_layer.mouse_drag_callbacks.append
                def click_drag(layer, event):
                    data_coordinates = layer.world_to_data(event.position)
                    val = layer.get_value(data_coordinates)
                    yield
                    # on move
                    while event.type == 'mouse_move':
                        if val == (0, None) and self.cfg.sensor_column_count >= event.position[1] >= 0:  # vert_line
                            layer.data = [
                                [[self.vert_start, event.position[1]], [self.vert_end, event.position[1]]],
                                layer.data[1]]

                            layer.data = [layer.data[0],
                                          [[event.position[0], 0], [event.position[0], self.cfg.sensor_row_count]]]
                            yield
                        elif val == (1, None) and self.horz_end >= event.position[0] >= self.horz_start:  # horz_line
                            layer.data = [
                                [[self.vert_start, event.position[1]], [self.vert_end, event.position[1]]],
                                layer.data[1]]

                            layer.data = [layer.data[0],
                                          [[event.position[0], 0], [event.position[0], self.cfg.sensor_row_count]]]
                            yield
                        else:
                            yield

    def color_change(self):
        wavelength = int(self.live_view['wavelength'].currentText())
        self.live_view['wavelength'].setStyleSheet(
            f'QComboBox {{ background-color:{self.cfg.laser_specs[str(wavelength)]["color"]}; color : black; }}')

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

        directions = ['X', 'Y', 'Z']
        self.pos_widget = {}
        self.stage_position = self.instrument.get_sample_position()

        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction], QSpinBox, f'{direction}:')
            self.pos_widget[direction].valueChanged.connect(self.stage_position_changed)

        return self.create_layout(struct='H', **self.pos_widget)

    # def update_sample_pos(self):
    #     """Update position widgets for volumetric imaging or manually moving"""
    #
    #     sample_pos = self.instrument.get_sample_position()
    #     for direction, value in sample_pos.items():
    #         if direction in self.pos_widget:
    #             self.pos_widget[direction].setValue(value)
    #
    # def stage_position_changed(self):
    #     self.instrument.move_sample_absolute(self.pos_widget['X'].value(), self.pos_widget['Y'].value(),
    #                                          self.pos_widget['Z'].value())
    #     print(self.instrument.get_sample_position())
    #
    # def volumeteric_imaging_button(self):
    #
    #     volumetric_image = {'start': QPushButton('Start Volumetric Imaging')}
    #     volumetric_image['start'].clicked.connect(self.instrument.run_from_config())
    #
    #     return self.create_layout(struct='H', **volumetric_image)

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
                #self.waveform['graph'].setXRange(0, .03)
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
            self.selected[wavelengths].setStyleSheet(f'QPushButton {{ background-color:{color["color"]}; color '
                                                     f':black; }}')
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
        self.laser_power[widget_wavelength].setHidden(True)
        self.laser_power[f'{widget_wavelength} label'].setHidden(True)
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
            self.laser_power[widget_wavelength].setHidden(False)
            self.laser_power[f'{widget_wavelength} label'].setHidden(False)

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

    def laser_power_slider(self, lasers: dict):
        self.lasers = lasers
        laser_power_layout = {}
        for wl in lasers:
            wls = str(wl)

            if wl == 561:
                command = Cmd.LaserPower
                set_value = float(lasers[wl].get(Query.LaserPowerSetting)) if not self.simulated else 15
                slider_label = f'{wl}: {set_value}mW'
            else:
                command = Cmd.LaserCurrent
                set_value = float(lasers[wl].get(Query.LaserCurrentSetting)) if not self.simulated else 15

            self.laser_power[f'{wls} label'], self.laser_power[wls] = self.create_widget(
                value=int(set_value),
                Qtype=QSlider,
                label=f'{wl}: {set_value}mW' if wl == 561 else f'{wl}: {set_value}%' )

            self.laser_power[wls].setTickPosition(QSlider.TickPosition.TicksBothSides)
            self.laser_power[wls].setStyleSheet(
                f"QSlider::sub-page:horizontal{{ background-color:{self.cfg.laser_specs[wls]['color']}; }}")
            self.laser_power[wls].setMinimum(0)
            self.laser_power[wls].setMaximum(float(lasers[wl].get(Query.MaximumLaserPower))) \
                if wl == 561 and not self.simulated else self.laser_power[wls].setMaximum(100)
            self.laser_power[wls].sliderReleased.connect(
                lambda value=self.laser_power[wls].value(), wl=wls, released = True, command=command:
                self.laser_power_label(command, wl, released, command))
            self.laser_power[wls].sliderMoved.connect(
                lambda value=self.laser_power[wls].value(), wl=wls: self.laser_power_label(value, wl))

            if wl not in self.imaging_wavelengths:
                self.laser_power[wls].setHidden(True)
                self.laser_power[f'{wls} label'].setHidden(True)
            laser_power_layout[wls] = self.create_layout(struct='H', label=self.laser_power[f'{wls} label'],
                                                            text=self.laser_power[wls])

        return self.create_layout(struct='V', **laser_power_layout)

    def laser_power_label(self, value, wl, released = False, command = None):

        text = f'{wl}: {value}mW' if wl == str(561) else f'{wl}: {value}%'
        self.laser_power[f'{wl} label'].setText(text)

        if released:
            self.lasers[int(wl)].set(command, self.laser_power[wl].value())



