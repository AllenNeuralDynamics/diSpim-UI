from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QComboBox, QSpinBox, QLineEdit, QTabWidget
import qtpy.QtGui as QtGui
import qtpy.QtCore as QtCore
import numpy as np
from math import ceil
from skimage.io import imsave
from napari.qt.threading import thread_worker, create_worker
from time import sleep
import logging


class Livestream(WidgetBase):

    def __init__(self, viewer, cfg, instrument, simulated: bool):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.cfg = cfg
        self.possible_wavelengths = self.cfg.laser_wavelengths
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.live_view = {}
        self.waveform = {}
        self.selected = {}
        self.grid = {}
        self.pos_widget = {}
        self.pos_widget = {}  # Holds widgets related to sample position
        self.set_volume = {}  # Holds widgets related to setting volume limits during scan
        self.stage_position = None
        self.tab_widget = None
        self.sample_pos_worker = None
        self.end_scan = None

        self.livestream_worker = None
        self.scale = [self.cfg.cfg['tile_specs']['x_field_of_view_um'] / self.cfg.sensor_row_count,
                      self.cfg.cfg['tile_specs']['y_field_of_view_um'] / self.cfg.sensor_column_count]
        # TODO:change to config params
        self.layer_index = 0
        self.stream_id = 1

        # Start and end points for lines
        self.vert_start = -self.cfg.sensor_column_count * self.scale[0]  # I can just change this to um in field of view
        self.vert_end = 0
        self.horz_start = -self.cfg.sensor_row_count * self.scale[1]
        self.horz_end = self.cfg.sensor_row_count * self.scale[1]

        self.camera_id = ['Right', 'Left']

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.update_positon)

    def update_positon(self, index):

        directions = ['X', 'Y', 'Z']
        if index == 0:
            self.stage_position = self.instrument.tigerbox.get_position()
            # Update stage labels if stage has moved
            for direction in directions:
                self.pos_widget[direction].setValue(int(self.stage_position[direction] * 1 / 10))


    def liveview_widget(self):

        """Contains button to activate livestream as well as selection of laser, autocontrast and rotation of
        liveview """

        self.live_view['start'] = QPushButton('Start Live View')
        self.live_view['start'].clicked.connect(self.start_live_view)

        self.live_view['0'] = QPushButton('Right')
        self.live_view['0'].setHidden(True)
        self.live_view['0'].pressed.connect(lambda stream_id=0: self.toggle_camera_view(stream_id))

        self.live_view['1'] = QPushButton('Left')
        self.live_view['1'].setHidden(True)
        self.live_view['1'].pressed.connect(lambda stream_id=1: self.toggle_camera_view(stream_id))

        self.live_view['overlay'] = QPushButton('Blend')
        self.live_view['overlay'].setHidden(True)
        self.live_view['overlay'].clicked.connect(self.blending_views)

        self.live_view['grid'] = QPushButton('Both')
        self.live_view['grid'].setHidden(True)
        self.live_view['grid'].clicked.connect(self.dual_stream)

        self.camera_button_change('1')

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

    def camera_button_change(self, pressed: str):

        """Changes selected button color to green and unselected to grey"""

        for kw in self.live_view:
            if kw == 'wavelength':
                continue
            else:
                color = 'green' if kw == pressed else 'gray'
                self.live_view[kw].setStyleSheet(f"background-color : {color}")

    def toggle_camera_view(self, stream_id):

        """Toggles opacity of left and right camera layer depending on button press """

        self.stream_id = stream_id
        not_id = (stream_id + 1) % 2
        key = f"Video {self.camera_id[stream_id]}"
        not_key = f"Video {self.camera_id[not_id]}"

        self.viewer.layers['line'].visible = True
        self.viewer.layers['line'].mode = 'select'
        self.viewer.grid.enabled = False
        self.viewer.layers[key].opacity = 1
        self.viewer.layers[not_key].opacity = 0
        self.viewer.layers.selection.active = self.viewer.layers[key]
        self.camera_button_change(str(self.stream_id))

    def blending_views(self):

        """Blends right and left camera views"""

        self.viewer.grid.enabled = False
        self.viewer.layers['line'].visible = True
        self.viewer.layers['line'].mode = 'select'
        self.viewer.layers[f"Video Left"].blending = self.viewer.layers[f"Video Right"].blending = 'additive'
        self.viewer.layers[f"Video Left"].opacity = self.viewer.layers[f"Video Right"].opacity = 1.0
        self.camera_button_change('overlay')

    def dual_stream(self):

        """Displays right and left camera layers side by side and hides line and grid layer"""

        try:
            self.viewer.layers.remove(self.viewer.layers['grid'])
        except:
            pass
        self.viewer.layers[f"Video Left"].opacity = self.viewer.layers[f"Video Right"].opacity = 1.0
        self.camera_button_change('grid')
        self.viewer.grid.enabled = True
        self.viewer.layers[-1].visible = False
        self.viewer.grid.shape = (1, 4)
        self.viewer.camera.zoom = .35

    def start_live_view(self):

        """Start livestreaming"""

        self.disable_button(self.live_view['start'])
        self.live_view['start'].clicked.disconnect(self.start_live_view)

        if self.live_view['start'].text() == 'Start Live View':
            self.live_view['start'].setText('Stop Live View')
            self.live_view['overlay'].setHidden(False)
            self.live_view['1'].setHidden(False)
            self.live_view['0'].setHidden(False)
            self.live_view['grid'].setHidden(False)

        self.instrument.start_livestream(int(self.live_view['wavelength'].currentText()))
        self.livestream_worker = create_worker(self.instrument._livestream_worker)
        self.livestream_worker.yielded.connect(self.update_layer)
        self.livestream_worker.start()

        pause = sleep(5) if self.simulated else sleep(1)    # Allow livestream to start

        self.sample_pos_worker = self._sample_pos_worker()
        self.sample_pos_worker.start()


        self.live_view['start'].clicked.connect(self.stop_live_view)
        # Only allow stopping once everything is initialized
        # to avoid crashing gui

    def stop_live_view(self):

        """Stop livestreaming"""

        self.disable_button(self.live_view['start'])
        self.live_view['start'].clicked.disconnect(self.stop_live_view)
        self.instrument.stop_livestream()
        self.livestream_worker.quit()
        self.sample_pos_worker.quit()
        self.live_view['start'].setText('Start Live View')
        self.live_view['overlay'].setHidden(True)
        self.live_view['1'].setHidden(True)
        self.live_view['0'].setHidden(True)
        self.live_view['grid'].setHidden(True)

        self.live_view['start'].clicked.connect(self.start_live_view)

    def disable_button(self, button, pause=5000):

        """Function to disable button clicks for a period of time to avoid crashing gui"""

        button.setEnabled(False)
        QtCore.QTimer.singleShot(pause, lambda: button.setDisabled(False))

    def update_layer(self, args):

        """Update right and left layers switching each iteration"""

        (image, stream_id) = args
        key = f"Video {self.camera_id[stream_id]}"
        try:

            layer = self.viewer.layers[key]
            layer._slice.image._view = image
            layer.events.set_data()

        except KeyError:

            self.viewer.add_image(image, name=f"Video {self.camera_id[stream_id]}", scale=self.scale)
            self.layer_index += 1

            if self.layer_index == 2:
                center = self.viewer.camera.center
                self.viewer.camera.center = (0, center[1] + self.horz_start, center[2])
                self.viewer.layers['Video Right'].rotate = self.viewer.layers['Video Left'].rotate = 90

                vert_line = np.array([[self.vert_start, 0], [self.vert_end, 0]])
                horz_line = np.array([[0, 0], [0, self.horz_end]])
                l = [vert_line, horz_line]
                color = ['blue', 'green']

                shapes_layer = self.viewer.add_shapes(l, shape_type='line', edge_width=3, edge_color=color, name='line')
                shapes_layer.mode = 'select'

                self.viewer.layers.selection.active = self.viewer.layers["Video Left"]


                @shapes_layer.mouse_drag_callbacks.append
                def click_drag(layer, event):
                    """Create draggable lines"""
                    data_coordinates = layer.world_to_data(event.position)
                    val = layer.get_value(data_coordinates)
                    yield
                    # on move
                    while event.type == 'mouse_move':
                        if val == (0, None) and self.cfg.sensor_column_count >= event.position[1] >= 0 or \
                                val == (1, None) and self.horz_end >= event.position[0] >= self.horz_start:
                            layer.data = [
                                [[self.vert_start, event.position[1]], [self.vert_end, event.position[1]]],
                                [[event.position[0], 0], [event.position[0], self.horz_end]]]
                            yield
                        else:
                            yield

    def color_change(self):

        """Changes color of drop down menu based on selected lasers """

        wavelength = int(self.live_view['wavelength'].currentText())
        self.live_view['wavelength'].setStyleSheet(
            f'QComboBox {{ background-color:{self.cfg.laser_specs[str(wavelength)]["color"]}; color : black; }}')

        if self.instrument.livestream_enabled.is_set():
            self.instrument.setup_imaging_for_laser(wavelength, True)

    def grid_widget(self):

        """Creates input widget for how many horz/vert lines in created grid.
            Create widget displaying area contained in grid box"""

        self.grid['label'], self.grid['widget'] = self.create_widget(2, QSpinBox, 'Grid Lines: ')
        self.grid['widget'].setValue(2)
        self.grid['widget'].setMinimum(2)
        self.grid['widget'].valueChanged.connect(self.create_grid)

        self.grid['pixel label'], self.grid['pixel widget'] = self.create_widget(
            f'{ceil(self.cfg.sensor_row_count * self.scale[0])}x'
            f'{ceil(self.cfg.sensor_column_count * self.scale[1])}', QLineEdit, 'um per Area:')
        self.grid['pixel widget'].setReadOnly(True)

        return self.create_layout(struct='H', **self.grid)

    def create_grid(self, n):

        """Creates grid layers"""

        try:
            self.viewer.layers.remove(self.viewer.layers['grid'])
        except:
            pass

        dim = [self.cfg.sensor_row_count, self.cfg.sensor_column_count]  # rows
        vert = [None] * n
        horz = [None] * n
        vert[0] = np.array([[0, 0], [dim[0], 0]])
        horz[0] = np.array([[0, 0], [0, dim[1]]])
        v_coord = ceil((dim[1] / (n - 1)))
        h_coord = ceil((dim[0] / (n - 1)))
        for i in range(0, n - 1):
            vert[i] = np.array([[0, v_coord * i], [dim[0], v_coord * i]])
            horz[i] = np.array([[h_coord * i, 0], [h_coord * i, dim[1]]])

        vert[n - 1] = np.array([[0, dim[1]], [dim[0], dim[1]]])
        horz[n - 1] = np.array([[dim[0], 0], [dim[0], dim[1]]])
        lines = vert + horz
        self.viewer.add_shapes(
            lines,
            shape_type='line',
            name='grid',
            edge_width=10,
            edge_color='white',
            scale=self.scale)

        self.grid['pixel widget'].setText(f'{ceil(v_coord * self.scale[0])}x'
                                          f'{ceil(h_coord * self.scale[1])}')
        self.viewer.layers['grid'].rotate = 90

    def sample_stage_position(self):

        """Creates labels and boxs to indicate sample position"""

        directions = ['X', 'Y', 'Z']
        self.stage_position = self.instrument.tigerbox.get_position()

        # Create X, Y, Z labels and displays for where stage is
        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction]*1/10, QSpinBox, f'{direction} [um]:')
            self.pos_widget[direction].setReadOnly(True)

        # Sets start position of scan to current position of sample
        self.set_volume['set_start'] = QPushButton()
        self.set_volume['set_start'].setText('Set Scan Start')

        # Sets start position of scan to current position of sample
        self.set_volume['set_end'] = QPushButton()
        self.set_volume['set_end'].setText('Set Scan End')
        self.set_volume['set_end'].setHidden(True)

        self.set_volume['clear'] = QPushButton()
        self.set_volume['clear'].setText('Clear')
        self.set_volume['clear'].clicked.connect(self.clear_start_position)
        self.set_volume['clear'].setHidden(True)

        self.pos_widget['volume_widgets'] = self.create_layout(struct='V', **self.set_volume)

        return self.create_layout(struct='H', **self.pos_widget)

    def clear_start_position(self):

        """Reset start position of scan to None which means the scan will start at current positon"""

        self.instrument.set_scan_start(None)

    @thread_worker
    def _sample_pos_worker(self):
        """Update position widgets for volumetric imaging or manually moving"""

        self.log.info('Starting stage update')
        # While livestreaming and looking at the first tab the stage position updates
        while True:
            while self.instrument.livestream_enabled.is_set() and \
                    self.tab_widget.currentIndex() == 0:
                self.sample_pos = self.instrument.tigerbox.get_position()
                for direction, value in self.sample_pos.items():
                    if direction in self.pos_widget:
                        self.pos_widget[direction].setValue(int(value*1/10))  #Units in microns
            yield       # yield so thread can quit
            sleep(.5)

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
