from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QComboBox, QSpinBox, QLineEdit, QTabWidget,QListWidget,QListWidgetItem, \
    QAbstractItemView, QScrollArea, QSlider, QLabel, QCheckBox
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
        self.pos_widget = {}  # Holds widgets related to sample position
        self.move_stage = {}
        self.set_scan_start = {}  # Holds widgets related to setting volume limits during scan
        self.stage_position = None
        self.tab_widget = None
        self.sample_pos_worker = None
        self.end_scan = None

        self.livestream_worker = None
        self.scale = [self.cfg.tile_specs['x_field_of_view_um'] / self.cfg.sensor_row_count,
                      self.cfg.tile_specs['y_field_of_view_um'] / self.cfg.sensor_column_count]

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

        wv_strs = [str(x) for x in self.possible_wavelengths]
        wv_strs.sort()

        # Determine if we can do multichannel liveview and set up corresponding drop box or multiselect

        if self.cfg.acquisition_style == 'interleaved':
            self.live_view['wavelength'] = QListWidget()
            self.live_view['wavelength'].setSelectionMode(QAbstractItemView.MultiSelection)
            wv_item = {}
            for wavelength in wv_strs:
                wv_item[wavelength] = QListWidgetItem(wavelength)

                wv_item[wavelength].setBackground(QtGui.QColor(65, 72, 81,255))
                self.live_view['wavelength'].addItem(wv_item[wavelength])
            self.live_view['wavelength'].itemPressed.connect(self.color_change_list)
            self.live_view['wavelength'].setMaximumHeight(70)
            self.live_view['wavelength'].setSortingEnabled(True)

        elif self.cfg.acquisition_style == 'sequential':

            self.live_view['wavelength'] = QComboBox()
            self.live_view['wavelength'].addItems(wv_strs)
            self.live_view['wavelength'].currentIndexChanged.connect(self.color_change_combbox)
            i = 0
            for wavelength in wv_strs:
                self.live_view['wavelength'].setItemData(i, QtGui.QColor(self.cfg.laser_specs[wavelength]['color']),
                                                         QtCore.Qt.BackgroundRole)
                i += 1
            self.live_view['wavelength'].setStyleSheet(
                f'QComboBox {{ background-color:{self.cfg.laser_specs[wv_strs[0]]["color"]}; color : black; }}')

        # Sets start position of scan to current position of sample
        self.set_scan_start['set_start'] = QPushButton()
        self.set_scan_start['set_start'].setText('Set Scan Start')
        self.set_scan_start['set_start'].clicked.connect(self.set_start_position)

        self.set_scan_start['clear'] = QPushButton()
        self.set_scan_start['clear'].setText('Clear')
        self.set_scan_start['clear'].clicked.connect(self.clear_start_position)
        self.set_scan_start['clear'].setHidden(True)

        self.set_scan_start['scouting'] = QCheckBox('Scout Mode')

        self.live_view['scan_start'] = self.create_layout(struct='V', **self.set_scan_start)

        return self.create_layout(struct='H', **self.live_view)

    def start_live_view(self):

        """Start livestreaming"""
        wavelengths = [int(item.text()) for item in self.live_view['wavelength'].selectedItems()] if \
            self.cfg.acquisition_style == 'interleaved' else [int(self.live_view['wavelength'].currentText())]
        if len(wavelengths) == 0:
            self.error_msg('No channel selected',
                           'Please select at least one channel to image in.')
            return

        self.disable_button(button=self.live_view['start'])
        self.live_view['start'].clicked.disconnect(self.start_live_view)

        if self.live_view['start'].text() == 'Start Live View':
            self.live_view['start'].setText('Stop Live View')
            for buttons in self.live_view:
                self.live_view[buttons].setHidden(False)

        self.instrument.start_livestream(wavelengths, self.set_scan_start['scouting'].isChecked()) # Needs to be list
        self.livestream_worker = create_worker(self.instrument._livestream_worker)
        self.livestream_worker.yielded.connect(self.update_layer)
        self.livestream_worker.start()

        sleep(2)    # Allow livestream to start

        self.sample_pos_worker = self._sample_pos_worker()
        self.sample_pos_worker.start()

        self.live_view['start'].clicked.connect(self.stop_live_view)
        # Only allow stopping once everything is initialized
        # to avoid crashing gui

        self.move_stage['slider'].setEnabled(False)
        self.move_stage['position'].setEnabled(False)
        # Disable moving stage while in liveview

    def stop_live_view(self):

        """Stop livestreaming"""

        self.disable_button(button=self.live_view['start'])
        self.live_view['start'].clicked.disconnect(self.stop_live_view)
        self.instrument.stop_livestream()
        self.livestream_worker.quit()
        self.sample_pos_worker.quit()
        self.live_view['start'].setText('Start Live View')

        self.live_view['start'].clicked.connect(self.start_live_view)

        self.move_stage['slider'].setEnabled(True)
        self.move_stage['position'].setEnabled(True)

    def disable_button(self, pressed=None, button = None, pause=3000):

        """Function to disable button clicks for a period of time to avoid crashing gui"""

        button.setEnabled(False)
        QtCore.QTimer.singleShot(pause, lambda: button.setDisabled(False))

    def color_change_list(self, item):

        """Changes selected iteams color in Qlistwidget"""

        wl = item.text()
        if item.isSelected():
            item.setBackground(QtGui.QColor(self.cfg.laser_specs[wl]['color']))
        else:
            item.setBackground(QtGui.QColor(65, 72, 81,255))

    def color_change_combbox(self):

        """Changes color of drop down menu based on selected lasers """

        wavelength = int(self.live_view['wavelength'].currentText())
        self.live_view['wavelength'].setStyleSheet(
            f'QComboBox {{ background-color:{self.cfg.laser_specs[str(wavelength)]["color"]}; color : black; }}')

        if self.instrument.livestream_enabled.is_set():
            self.instrument.setup_imaging_for_laser(wavelength, True)

    def sample_stage_position(self):

        """Creates labels and boxs to indicate sample position"""

        directions = ['X', 'Y', 'Z']
        self.stage_position = self.instrument.tigerbox.get_position()

        # Create X, Y, Z labels and displays for where stage is
        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction]*1/10, QSpinBox, f'{direction} [um]:')
            self.pos_widget[direction].setReadOnly(True)

        return self.create_layout(struct='H', **self.pos_widget)
    def set_start_position(self):

        """Set the starting position of the scan"""

        current = self.sample_pos if self.instrument.livestream_enabled.is_set() \
            else self.instrument.sample_pose.get_position()

        if self.instrument.start_pos is None:
            self.set_scan_start['clear'].setHidden(False)
        self.instrument.set_scan_start(current)

    def clear_start_position(self):

        """Reset start position of scan to None which means the scan will start at current positon"""

        self.instrument.set_scan_start(None)

    @thread_worker
    def _sample_pos_worker(self):
        """Update position widgets for volumetric imaging or manually moving"""

        self.log.info('Starting stage update')
        # While livestreaming and looking at the first tab the stage position updates
        while True:

            while self.instrument.livestream_enabled.is_set() and self.tab_widget.currentIndex() == 0:

                try:
                    self.sample_pos = self.instrument.tigerbox.get_position()
                    for direction, value in self.sample_pos.items():
                        if direction in self.pos_widget:
                            self.pos_widget[direction].setValue(int(value * 1 / 10))  # Units in microns
                    self.update_slider(self.sample_pos)     # Update slide with newest z depth
                except:
                    pass
                sleep(1)

            yield  # yield so thread can quit
            sleep(.1)

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

    def move_stage_widget(self):

        """Widget to move stage up and down w/o joystick control"""

        z_position = self.instrument.tigerbox.get_position('z')
        self.z_limit = self.instrument.sample_pose.get_travel_limits('y')
        self.z_limit['y'] = [round(x*10000) for x in self.z_limit['y']]
        self.z_range = self.z_limit["y"][1] + abs(self.z_limit["y"][0]) # Shift range up by lower limit so no negative numbers
        self.move_stage['up'] = QLabel(
            f'Upper Limit: {round(self.z_limit["y"][0])}')  # Upper limit will be the more negative limit
        self.move_stage['slider'] = QSlider()
        self.move_stage['slider'].setOrientation(QtCore.Qt.Vertical)
        self.move_stage['slider'].setInvertedAppearance(True)
        self.move_stage['slider'].setMinimum(self.z_limit["y"][0])
        self.move_stage['slider'].setMaximum(self.z_limit["y"][1])
        self.move_stage['slider'].setValue(int(z_position['Z']))
        self.move_stage['slider'].setTracking(False)
        self.move_stage['slider'].sliderReleased.connect(self.move_stage_vertical_released)
        self.move_stage['low'] = QLabel(
            f'Lower Limit: {round(self.z_limit["y"][1])}')  # Lower limit will be the more positive limit

        self.move_stage['halt'] = QPushButton('HALT')
        self.move_stage['halt'].clicked.connect(self.update_slider)
        self.move_stage['halt'].clicked.connect(lambda pressed=True, button=self.move_stage['halt']:
                                                self.disable_button(pressed,button))
        self.move_stage['halt'].clicked.connect(self.instrument.tigerbox.halt)

        self.move_stage['position'] = QLineEdit(str(z_position['Z']))
        self.move_stage['position'].setValidator(QtGui.QIntValidator(self.z_limit["y"][0],self.z_limit["y"][1]))
        self.move_stage['slider'].sliderMoved.connect(self.move_stage_textbox)
        self.move_stage_textbox(int(z_position['Z']))
        self.move_stage['position'].returnPressed.connect(self.move_stage_vertical_released)



        return self.create_layout(struct='V', **self.move_stage)

    def move_stage_vertical_released(self, location=None):

        """Move stage to location and stall until stopped"""

        if location==None:
            location = int(self.move_stage['position'].text())
            self.move_stage['slider'].setValue(location)
            self.move_stage_textbox(location)
        self.tab_widget.setTabEnabled(len(self.tab_widget)-1, False)
        self.instrument.tigerbox.move_absolute(z=location)
        self.move_stage_worker = create_worker(lambda axis='y', pos=float(location): self.instrument.wait_to_stop(axis, pos))
        self.move_stage_worker.start()
        self.move_stage_worker.finished.connect(lambda:self.enable_stage_slider())

    def enable_stage_slider(self):

        """Enable stage slider after stage has finished moving"""
        self.move_stage['slider'].setEnabled(True)
        self.move_stage['position'].setEnabled(True)
        self.tab_widget.setTabEnabled(len(self.tab_widget) - 1, True)


    def move_stage_textbox(self, location):

        position = self.move_stage['slider'].pos()
        self.move_stage['position'].setText(str(location))
        self.move_stage['position'].move(QtCore.QPoint(position.x() + 30,
                                                      position.y() + (-5)+((location+ abs(self.z_limit["y"][0]))/self.z_range
                                                      *(self.move_stage['slider'].height()-10))))

    def update_slider(self, location:dict):

        """Update position of slider if stage halted"""

        if type(location) == bool:      # if location is bool, then halt button was pressed
            self.move_stage_worker.quit()
            location = self.instrument.tigerbox.get_position('z')
        self.move_stage_textbox(int(location['Z']))
        self.move_stage['slider'].setValue(int(location['Z']))
