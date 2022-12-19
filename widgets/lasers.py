from widgets.widget_base import WidgetBase
from PyQt5.QtCore import Qt, QSize
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider, QLineEdit, \
    QTabWidget, QVBoxLayout
from oxxius_laser import Cmd, Query



class Lasers(WidgetBase):

    def __init__(self, viewer, cfg, instrument, simulated):

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

        self.wavelength_selection = {}
        self.selected = {}
        self.laser_power = {}
        self.tab_map = {}
        self.rl_tab_widgets = {}
        self.selected_wl_layout = None
        self.tab_widget = None


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

    def change_tab(self, wl_tab_index):

        index = self.tab_widget.currentIndex() if type(wl_tab_index) != int else wl_tab_index
        title = self.tab_widget.tabText(index)
        wl = title[-3:]

        try:
            if self.viewer.layers.selection.active == self.viewer.layers['Video Right']:
                self.rl_tab_widgets[wl].setCurrentIndex(0)

            if self.viewer.layers.selection.active == self.viewer.layers['Video Left']:
                self.rl_tab_widgets[wl].setCurrentIndex(1)

        except:
            pass

    def format_wavelength_tabs(self, wl:str):

        """Create tabs within wavelength tabs to separate right and left parameters"""

        self.viewer.layers.selection.events.changed.connect(self.change_tab)
        self.rl_tab_widgets[wl] = QTabWidget()  # Creating tab object
        self.rl_tab_widgets[wl].setTabPosition(QTabWidget.West)
        params_widget = self.scan_wavelength_params(wl)
        right_camera_layout = {}
        left_camera_layout = {}
        general_layout = {}

        for keys in params_widget:
            if 'right' in keys:
                left_camera_layout[keys] = params_widget[keys]
                params_widget[keys].children()[1].setText(params_widget[keys].children()[1].text().replace('Right', ''))

            elif 'left' in keys:
                right_camera_layout[keys] = params_widget[keys]
                params_widget[keys].children()[1].setText(params_widget[keys].children()[1].text().replace('Left', ''))

            else:
                general_layout[keys] = params_widget[keys]

        left_camera_widget = self.create_layout('V', **left_camera_layout)
        right_camera_widget = self.create_layout('V', **right_camera_layout)
        self.rl_tab_widgets[wl].addTab(right_camera_widget, 'Right Camera')
        self.rl_tab_widgets[wl].addTab(left_camera_widget, 'Left Camera')

        general_widget = self.create_layout('V', **general_layout)

        return self.create_layout('V', general = general_widget, tabs= self.rl_tab_widgets[wl])

    def add_wavelength_tabs(self, tab_widget: QTabWidget):

        """Adds laser parameters tabs onto main window for all possible wavelengths
        :param imaging_dock: main window to tabify laser parameter """

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.change_tab)
        for wl in self.possible_wavelengths:
            wl = str(wl)
            wl_dock = self.format_wavelength_tabs(wl)
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
        return self.scan(laser_specs_wavelength, 'laser_specs', wl=wavelength, subdict=True)


    def laser_power_slider(self, lasers: dict):

        """Create slider for every possible laser and hides ones not in use
        :param lasers: dictionary of lasers created """

        self.lasers = lasers
        laser_power_layout = {}
        for wl in lasers:  # Convert into strings for convenience. Laser device dict uses int , widget dict uses str
            wls = str(wl)

            # Setting commands and initial values for slider widgets. 561 is power based and others current
            if wl == 561:
                command = Cmd.LaserPower
                set_value = float(lasers[wl].get(Query.LaserPowerSetting)) if not self.simulated else 15
                slider_label = f'{wl}: {set_value}mW'
            else:
                command = Cmd.LaserCurrent
                set_value = float(lasers[wl].get(Query.LaserCurrentSetting)) if not self.simulated else 15

            # Creating label and line edit widget
            self.laser_power[f'{wls} label'], self.laser_power[wls] = self.create_widget(
                value=None,
                Qtype=QSlider,
                label=f'{wl}: {set_value}mW' if wl == 561 else f'{wl}: {set_value}%')

            # Setting coloring and bounds for sliders
            self.laser_power[wls].setTickPosition(QSlider.TickPosition.TicksBothSides)
            self.laser_power[wls].setStyleSheet(
                f"QSlider::sub-page:horizontal{{ background-color:{self.cfg.laser_specs[wls]['color']}; }}")
            self.laser_power[wls].setMinimum(0)
            self.laser_power[wls].setMaximum(float(lasers[wl].get(Query.MaximumLaserPower))) \
                if wl == 561 and not self.simulated else self.laser_power[wls].setMaximum(100)
            self.laser_power[wls].setValue(set_value)

            # Setting activity when slider is moved (update lable value)
            # or released (update laser current or power to slider setpoint)
            self.laser_power[wls].sliderReleased.connect(
                lambda value=self.laser_power[wls].value(), wl=wls, released=True, command=command:
                self.laser_power_label(command, wl, released, command))
            self.laser_power[wls].sliderMoved.connect(
                lambda value=self.laser_power[wls].value(), wl=wls: self.laser_power_label(value, wl))

            # Hides sliders that are not being used in imaging
            if wl not in self.imaging_wavelengths:
                self.laser_power[wls].setHidden(True)
                self.laser_power[f'{wls} label'].setHidden(True)
            laser_power_layout[wls] = self.create_layout(struct='H', label=self.laser_power[f'{wls} label'],
                                                         text=self.laser_power[wls])

        return self.create_layout(struct='V', **laser_power_layout)


    def laser_power_label(self, value, wl: int, released=False, command=None):

        """Set laser current or power to slider set point if released and update label if slider moved
        :param value: value of slider
        :param wl: wavelength of laser
        :param released: if slider was released
        :param command: command to send to laser. Set current or power
        """

        value = self.laser_power[wl].value()
        text = f'{wl}: {value}mW' if wl == str(561) else f'{wl}: {value}%'
        self.laser_power[f'{wl} label'].setText(text)

        if released:
            self.lasers[int(wl)].set(command, float(self.laser_power[wl].value()))
            # TODO: When gui talks to hardware, log statement clarifying this
            #   Anytime gui changes state of not the gui
            # self.lasers[561].get(Query.LaserPowerSetting)
