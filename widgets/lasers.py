from widgets.widget_base import WidgetBase
from PyQt5.QtCore import Qt, QSize
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider, QLineEdit, \
    QTabWidget, QVBoxLayout
from oxxius_laser import Cmd, Query
import qtpy.QtCore as QtCore
import logging
import numpy as np
from math import floor, ceil

class Lasers(WidgetBase):

    def __init__(self, viewer, cfg, instrument, simulated, laser_conversion_filename = None):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.viewer = viewer
        self.cfg = cfg
        self.instrument = instrument
        self.simulated = simulated
        self.possible_wavelengths = self.cfg.laser_wavelengths
        self.imaging_wavelengths = self.cfg.imaging_wavelengths
        self.lasers = self.instrument.lasers
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.wavelength_selection = {}
        self.selected = {}
        self.laser_power = {}
        self.tab_map = {}
        self.rl_tab_widgets = {}
        self.combiner_power_split = {}
        self.selected_wl_layout = None
        self.tab_widget = None
        self.laser_power_conversion = {}
        self.current_mode = True
        if laser_conversion_filename is not None:
            self.laser_power_conversion = {}
            self.current_mode = False
            laser_txt = np.loadtxt(fr'{laser_conversion_filename}')

            for row in laser_txt:
                self.laser_power_conversion[row[0]] = {'m': row[1], 'b': row[2]}


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
        return self.create_layout('V', **self.wavelength_selection)

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
        self.selected_wl_layout = self.create_layout(struct='V', **self.selected)
        return self.selected_wl_layout

    def hide_labels(self, clicked, widget):

        """Hides laser labels and tabs that are not in use
        :param widget: widget that was clicked to remove from imaging wavelengths
        """

        widget_wavelength = widget.text()
        widget.setHidden(True)
        self.tab_widget.setTabVisible(self.tab_map[widget_wavelength], False)
        self.laser_power[widget_wavelength].setHidden(True)
        self.laser_power[f'{widget_wavelength} label'].setHidden(True)
        self.imaging_wavelengths.remove(int(widget_wavelength))
        self.imaging_wavelengths.sort()
        self.wavelength_selection['unselected'].addItem(widget.text())

    def unhide_labels(self):

        """Reveals laser labels and tabs that are now in use"""

        index = self.wavelength_selection['unselected'].currentIndex()
        if index != 0:
            widget_wavelength = self.wavelength_selection['unselected'].currentText()
            self.imaging_wavelengths.append(int(widget_wavelength))
            self.imaging_wavelengths.sort()
            self.wavelength_selection['unselected'].removeItem(index)
            self.selected[widget_wavelength].setHidden(False)
            self.tab_widget.setTabVisible(self.tab_map[widget_wavelength], True)
            self.laser_power[widget_wavelength].setHidden(False)
            self.laser_power[f'{widget_wavelength} label'].setHidden(False)


    def add_wavelength_tabs(self, tab_widget: QTabWidget):

        """Adds laser parameters tabs onto main window for all possible wavelengths
        :param imaging_dock: main window to tabify laser parameter """

        self.tab_widget = tab_widget
        for wl in self.possible_wavelengths:
            wl = str(wl)
            wl_dock = self.scan_wavelength_params(wl)
            scroll_box = self.scroll_box(wl_dock)
            scrollable_dock = QDockWidget()
            scrollable_dock.setWidget(scroll_box)
            self.tab_widget.addTab(scrollable_dock, f'Wavelength {wl}')
            self.tab_map[wl] = self.tab_widget.indexOf(scrollable_dock)
            if int(wl) not in self.cfg.imaging_wavelengths:
                tab_widget.setTabVisible(self.tab_map[wl], False)
        return self.tab_widget

    def scan_wavelength_params(self, wavelength: str):
        """Scans config for relevant laser wavelength parameters
        :param wavelength: the wavelength of the laser"""

        laser_specs_wavelength = self.cfg.laser_specs[wavelength]
        tab_widget_wl = self.scan(laser_specs_wavelength, 'laser_specs', wl=wavelength, subdict=True)
        return self.create_layout(struct='V', **tab_widget_wl)


    def laser_power_slider(self):

        """Create slider for every possible laser and hides ones not in use
        :param lasers: dictionary of lasers created """

        laser_power_layout = {}
        for wl in self.possible_wavelengths:

            if wl == 561:   # skip 561 because it's different
                value = float(self.lasers[wl].get(Query.LaserPowerSetting)) if not self.simulated else 15
                min = 0
                max = float(self.lasers[wl].get(Query.MaximumLaserPower))
                command = Cmd.LaserPower

            elif wl != 561:
                current_pct = 15 if self.simulated else float(self.lasers[wl].get(Query.LaserCurrentSetting))
                value = current_pct if self.current_mode else \
                    round(self.laser_power_conversion[wl]['m'] * current_pct + self.laser_power_conversion[wl]['b'])
                min = 0 if self.current_mode else -self.laser_power_conversion[wl]['b']/self.laser_power_conversion[wl]['m']
                max = 100 if self.current_mode else self.laser_power_conversion[wl]['m'] * 100 + self.laser_power_conversion[wl]['b']
                command = Cmd.LaserCurrent

            self.laser_power[f'{wl} label'], self.laser_power[f'{wl}'] = self.create_widget(   # Create slider and label
                value=None,
                Qtype=QSlider,
                label=f'{wl}: {value}mW' if not self.current_mode else f'{wl}: {value}%')

            self.laser_power[f'{wl}'].setStyleSheet(
                f"QSlider::sub-page:horizontal{{ background-color:{self.cfg.laser_specs[f'{wl}']['color']}; }}")

            command = Cmd.LaserCurrent
            self.laser_power[f'{wl}'].setTickPosition(QSlider.TickPosition.TicksBothSides)
            self.laser_power[f'{wl}'].setMinimum(min)
            self.laser_power[f'{wl}'].setMaximum(max)
            self.laser_power[f'{wl}'].setValue(value)

            # Setting activity when slider is moved (update label value)
            # or released (update laser current or power to slider setpoint)
            wls = str(wl)
            self.laser_power[wls].sliderReleased.connect(
                lambda value=self.laser_power[wls].value(), wl=wls, released=True, command=command:
                self.laser_power_label(command, wl, released, command))
            self.laser_power[wls].sliderMoved.connect(
                lambda value=self.laser_power[wls].value(), wl=wls: self.laser_power_label(value, wl))
            # Hides sliders that are not being used in imaging
            if int(wl) not in self.imaging_wavelengths:
                self.laser_power[f'{wl}'].setHidden(True)
                self.laser_power[f'{wl} label'].setHidden(True)
            laser_power_layout[f'{wl}'] = self.create_layout(struct='H', label=self.laser_power[f'{wl} label'],
                                                         text=self.laser_power[f'{wl}'])

        return self.create_layout(struct='V', **laser_power_layout)

    def laser_power_label(self, value, wl: int, release=False, command=None):

        """Set laser current or power to slider set point if released and update label if slider moved
        :param value: value of slider
        :param wl: wavelength of laser
        :param released: if slider was released
        :param command: command to send to laser. Set current or power
        """

        value = self.laser_power[wl].value()
        text = f'{wl}: {value}mW' if not self.current_mode else f'{wl}: {value}%'
        self.laser_power[f'{wl} label'].setText(text)

        if release:
            self.log.info(f'Setting laser {wl} to {value}mW')
            laser_value = value if int(wl) == 561 or self.current_mode else \
                round((value - self.laser_power_conversion[int(wl)]['b']) / self.laser_power_conversion[int(wl)]['m'])
            self.lasers[int(wl)].set(command, float(laser_value))
            # TODO: When gui talks to hardware, log statement clarifying this
            #   Anytime gui changes state of not the gui

    def laser_power_splitter(self):

        """
        Create slider for laser combiner power split
                """

        split_percentage = self.lasers['main'].get(Query.PercentageSplitStatus) if not self.simulated else 15
        self.combiner_power_split['Left label'] = QLabel(f'Left: {100-float(split_percentage[0:-1])}%')  # Left laser is set to 100 - percentage entered
        self.combiner_power_split['slider'] = QSlider()
        self.combiner_power_split['slider'].setOrientation(QtCore.Qt.Vertical)
        self.combiner_power_split['slider'].setMinimum(0)
        self.combiner_power_split['slider'].setMaximum(100)
        self.combiner_power_split['slider'].setValue(float(split_percentage[0:-1]))
        self.combiner_power_split['slider'].sliderReleased.connect(
            lambda value=None, released=True, command=Cmd.PercentageSplit:
            self.set_power_split(value, released, command))
        self.combiner_power_split['slider'].sliderMoved.connect(
            lambda value=None: self.set_power_split(value))

        self.combiner_power_split['Right label'] = QLabel(
            f'Right: {split_percentage[0:-1]}%')  # Right laser is set to percentage entered

        return self.create_layout(struct='V', **self.combiner_power_split)
    def set_power_split(self, value, released=False, command=None):

        value = int(self.combiner_power_split['slider'].value())
        self.combiner_power_split['Right label'].setText(f'Right: {value}%')
        self.combiner_power_split['Left label'].setText(f'Left: {100 - int(value)}%')

        if released:
            self.lasers['main'].set(command, value)
            self.log.info(f'Laser power split set. Right: {value}%  Left: {100 - int(value)}%')