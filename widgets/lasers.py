from widgets.widget_base import WidgetBase
from PyQt5.QtCore import Qt, QSize, QPoint
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider, QLineEdit, \
    QTabWidget, QVBoxLayout, QMessageBox, QDial, QFrame, QInputDialog, QWidget, QDialog, QDialogButtonBox
import qtpy.QtCore as QtCore
import logging
import numpy as np
from math import floor, ceil
from sympy import symbols, Eq, solve
from ispim.compute_waveforms import generate_waveforms, plot_waveforms_to_pdf, galvo_waveforms, etl_waveforms
from math import pi
from napari.qt.threading import thread_worker, create_worker
from time import time, sleep
import copy
from qtpy.QtGui import QPixmap, QImage, QPainter, QPen
import qtpy.QtGui as QtGui

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
        self.dial_widgets = {}
        self.dials = {}

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
            self.selected[wavelengths].setStyleSheet(f'QPushButton {{ background-color:{self.cfg.laser_specs[wavelengths]["color"]}; color '
                                                     f':black; }}')
            self.selected[wavelengths].clicked.connect(lambda clicked=None, widget=self.selected[wavelengths]:
                                                       self.hide_labels(clicked, widget))

            if int(wavelengths) not in self.imaging_wavelengths:
                self.selected[wavelengths].setHidden(True)
        self.selected_wl_layout = self.create_layout(struct='V', **self.selected)
        return self.selected_wl_layout

    def geneprompt(self, wl):
        text, okPressed = QInputDialog.getText(QWidget(), f"Enter gene for channel {wl}", "Gene:")
        self.laser_power[f'{wl} textbox'].setText(text)
        self.instrument.channel_gene[wl] = text

    def hide_labels(self, clicked, widget):

        """Hides laser labels and tabs that are not in use
        :param widget: widget that was clicked to remove from imaging wavelengths
        """

        widget_wavelength = widget.text()
        widget.setHidden(True)
        self.tab_widget.setTabVisible(self.tab_map[widget_wavelength], False)
        if widget_wavelength in self.laser_power:
            self.laser_power[widget_wavelength].setHidden(True)
            self.laser_power[f'{widget_wavelength} label'].setHidden(True)
            self.laser_power[f'{widget_wavelength} textbox'].setHidden(True)
        self.instrument.channel_gene.pop(widget_wavelength)
        self.imaging_wavelengths.remove(int(widget_wavelength))
        self.imaging_wavelengths.sort()
        self.wavelength_selection['unselected'].addItem(widget.text())

    def unhide_labels(self, index=None):

        """Reveals laser labels and tabs that are now in use"""

        if index != 0:
            widget_wavelength = self.wavelength_selection['unselected'].itemText(index)
            self.geneprompt(widget_wavelength)
            self.imaging_wavelengths.append(int(widget_wavelength))
            self.imaging_wavelengths.sort()
            self.wavelength_selection['unselected'].removeItem(index)
            self.selected[widget_wavelength].setHidden(False)
            self.tab_widget.setTabVisible(self.tab_map[widget_wavelength], True)
            if widget_wavelength in self.laser_power:
                self.laser_power[widget_wavelength].setHidden(False)
                self.laser_power[f'{widget_wavelength} label'].setHidden(False)
                self.laser_power[f'{widget_wavelength} textbox'].setHidden(False)

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
            self.tab_widget.tabBarClicked.connect(self.change_viewer_layer)
            self.tab_map[wl] = self.tab_widget.indexOf(scrollable_dock)
            if int(wl) not in self.cfg.imaging_wavelengths:
                tab_widget.setTabVisible(self.tab_map[wl], False)

            self.viewer.layers.selection.events.changed.connect(self.layer_change)

        return self.tab_widget

    def change_viewer_layer(self, index):

        """Change selected layer based on what laser tab your on"""

        tab_text = self.tab_widget.tabText(index)
        for layer in self.viewer.layers:
            if tab_text == layer.name:
                self.viewer.layers.selection.active = self.viewer.layers[tab_text]

    def layer_change(self):

        """Change wavelength tab based on what layer your on"""

        # Not on the main tab or the tissue map
        if self.tab_widget.currentIndex() != len(self.tab_widget) - 1 and self.tab_widget.currentIndex() != 0:
            for i in range(1, self.tab_widget.count() - 1):  # skipping over main and tissue map
                if str(self.viewer.layers.selection.active) == str(self.tab_widget.tabText(i)):
                    self.tab_widget.setCurrentIndex(i)
                    if not self.tab_widget.isTabVisible(i):
                        combo_index = self.wavelength_selection['unselected'].findText(
                            str(self.viewer.layers.selection.active)[-3:])
                        self.unhide_labels(combo_index)
                    return

    def scan_wavelength_params(self, wv: str):
        """Scans config for relevant laser wavelength parameters
        :param wavelength: the wavelength of the laser"""

        galvo = {f'laser_specs.{wv}.galvo.{k}': v for k, v in self.cfg.laser_specs[wv]['galvo'].items()}
        etl = {f'laser_specs.{wv}.etl.{k}': v for k, v in self.cfg.laser_specs[wv]['etl'].items()}
        dial_values = {**galvo, **etl}

        self.dials[wv] = {}
        self.dial_widgets[wv] = {}
        for k, v in dial_values.items():
            self.dials[wv][k] = QDial()
            self.dials[wv][k].setRange(0, 5000)  # QDials only do int values
            self.dials[wv][k].setNotchesVisible(True)
            self.dials[wv][k].setValue(round(v * 1000))
            self.dials[wv][k].setSingleStep(1)
            self.dials[wv][k].setStyleSheet(
                f"QDial{{ background-color:{self.cfg.laser_specs[wv]['color']}; }}")

            self.dials[wv][k + 'value'] = QLineEdit(str(v))
            self.dials[wv][k + 'value'].setAlignment(QtCore.Qt.AlignCenter)
            self.dials[wv][k + 'value'].setReadOnly(True)
            self.dials[wv][k + 'label'] = QLabel(" ".join(k.split('.')[1:]))
            self.dials[wv][k + 'label'].setAlignment(QtCore.Qt.AlignCenter)

            self.dials[wv][k].valueChanged.connect(
                lambda value=str(self.dials[wv][k].value() / 1000),  # Divide to get dec
                       widget=self.dials[wv][k + 'value']: self.update_dial_label(value, widget))
            self.dials[wv][k + 'value'].textChanged.connect(lambda value=self.dials[wv][k].value() / 1000,
                                                                   path=k.split('.')[1:],
                                                                   dict=getattr(self.cfg, k.split('.')[0]):
                                                            self.config_change(value, path, dict))

            roi_button = QPushButton('Draw Autofocus ROI')
            roi_button.clicked.connect(lambda click = False, wl=wv, attribute=k:
                                                            self.autofocus_roi(click, wl, attribute))
            autofocus_button = QPushButton('Autofocus')
            autofocus_button.clicked.connect(lambda click = False, value=self.dials[wv][k].value() / 1000,
                                                                   attribute=k,
                                                                   wl=wv:
                                                            self.autofocus_thread(click, value, attribute, wl))

            self.dials[wv][k + 'autofocus'] = self.create_layout(struct='H', roi=roi_button, autofocus=autofocus_button)
            self.dial_widgets[wv][k] = self.create_layout(struct='V', label=self.dials[wv][k + 'label'],
                                                          dial=self.dials[wv][k],
                                                          value=self.dials[wv][k + 'value'],
                                                          autofocus = self.dials[wv][k + 'autofocus'])

        return self.create_layout(struct='HV', **self.dial_widgets[wv])

    def update_dial_label(self, value, widget):

        widget.setText(str(value / 1000))

    def autofocus_thread(self, click, start_value, attribute, wl, step=.1, roi=[slice(None, None), slice(None, None)]):

          autofocus_worker = create_worker(lambda value=start_value,
                                                   attribute=attribute,
                                                   wl=wl:
                                            self.autofocus(value, attribute, wl))
          autofocus_worker.start()

          self.image_worker = create_worker(self.instrument._acquisition_livestream_worker)
          self.image_worker.yielded.connect(self.update_layer)
          self.image_worker.start()
    def autofocus(self, start_value, attribute, wl, step=.1, roi = [slice(None, None), slice(None, None)]):

        self.instrument.active_lasers = [wl]    # Set active lasers to wl so image_worker will work
        self.instrument.frame_grabber.setup_stack_capture([self.cfg.local_storage_dir], 1000000000, 'Trash')
        self.instrument.frame_grabber.start()
        self.instrument.lasers[wl].enable()
        
        shannon_entropy = {start_value: 0}
        step_start = start_value - (step * 10) if start_value - (step * 10) >= 0 else 0.0
        step_range = (step * 10) + start_value if (step * 10) + start_value < 5 else 5.0
        step_i = step_start
        while step_i <= step_range:
            self.config_change(step_i, attribute.split('.')[1:], self.cfg.laser_specs)    # Change config to new voltage
            self.instrument._setup_waveform_hardware([wl], True, True)
            self.start_stop_ni()
            self.instrument.framedata(0)
            im = self.instrument.latest_frame
            shannon_entropy_im = self.instrument.calculate_normalized_dct_shannon_entropy(im[roi[0], roi[1]])
            if list(shannon_entropy.values())[0] < shannon_entropy_im:
                shannon_entropy = {step_i: shannon_entropy_im}

            step_i += step
        self.instrument.frame_grabber.runtime.abort()
        if step > .001:
            self.autofocus(list(shannon_entropy.keys())[0], attribute, wl, step/10)
            self.instrument.active_lasers = None
            self.instrument.lasers[wl].disable()
            self.image_worker.quit()
        else:
            self.dials[wl][attribute + 'value'].setText(str(round(list(shannon_entropy.keys())[0], 3)))
            self.dials[wl][attribute].setValue(round(1000*list(shannon_entropy.keys())[0], 3))
            self.config_change(round(list(shannon_entropy.keys())[0], 3), attribute.split('.')[1:], self.cfg.laser_specs)

    def autofocus_roi(self, click, wl, attribute):

        def paintEvent(event):
            painter = QPainter(self.roi_selection)
            br = QtGui.QBrush(QtGui.QColor(0, 100, 0, 100))
            painter.drawPixmap(self.roi_selection.rect(), self.image)
            painter.setBrush(br)
            painter.drawRect(QtCore.QRect(self.begin, self.end))
        def mousePressEvent(event):
            self.begin = event.pos()
            self.end = event.pos()
            self.roi_selection.update()

        def mouseMoveEvent(event):
            painter = QPainter(self.image)
            self.end = event.pos()
            self.roi_selection.update()

        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()
        key = f'Wavelength {wl}'
        if key in self.viewer.layers:
            self.roi_selection = QDialog()
            self.roi_selection.setGeometry(100, 100, self.cfg.sensor_row_count/2, self.cfg.sensor_column_count/2)
            self.roi_selection.setFixedSize(self.cfg.sensor_row_count/2, self.cfg.sensor_column_count/2)
            layout = QVBoxLayout()
            img = self.viewer.layers[key].data
            max = np.percentile(img, 90)
            min = np.percentile(img, 5)
            img = img.clip(min, max)
            img -= min
            img = np.floor_divide(img, (max - min) / 256, out=img, casting='unsafe')

            pixmap = QImage(img, img.shape[1], img.shape[0], QImage.Format_Grayscale16)
            img_widget = QLabel()
            self.image = QPixmap(pixmap.scaled(self.cfg.sensor_row_count/2, self.cfg.sensor_column_count/2,
                                                       QtCore.Qt.KeepAspectRatio))
            cancel_ok = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(cancel_ok)
            cancel_ok.accepted.connect(self.roi_selection.accept)
            cancel_ok.rejected.connect(self.roi_selection.reject)
            self.roi_selection.setLayout(layout)
            self.roi_selection.paintEvent = paintEvent
            self.roi_selection.mousePressEvent = mousePressEvent
            self.roi_selection.mouseMoveEvent = mouseMoveEvent
            result = self.roi_selection.exec()
            if result == 1:     # 1 means okay button pressed
                x = slice(self.begin.x(), self.end.x()) if self.end.x() > 0 else slice(self.begin.x(), 0)
                y = slice(self.begin.y(), self.end.y()) if self.end.y() > 0 else slice(self.begin.y(), 0)
                path = attribute.split('.')
                self.autofocus_thread(False, self.cfg.laser_specs[wl][path[2]][path[3]],
                                      attribute, wl, .1, [y, x])


    def calculate_laser_current(self, func, num=0):

        """Will find the solution of a polynomial function between 0 and 100
        coresponding to curent % of laser

        :param func: polynomial function coresponding to laser power vs current """

        percent = None
        solutions = solve(func - num)  # solutions for laser value
        for sol in solutions:
            if round(sol) in range(0, 101):
                percent = sol
                return percent

        # If value between 0-100 doesn't exist return error message
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(f"No current percent correlates to {num} mW")
        msgBox.setWindowTitle("Error")
        msgBox.setStandardButtons(QMessageBox.Ok)
        return msgBox.exec()

    def laser_power_slider(self):

        """Create slider for every possible laser and hides ones not in use
        :param lasers: dictionary of lasers created """

        laser_power_layout = {}

        for wl in self.possible_wavelengths:
            wl = str(wl)
            if wl not in self.lasers:
                continue

            # Coeffiecients and order of coeffs describing power vs current curve
            if 'coeffecients' in self.cfg.laser_specs[wl]:
                coeffiecients = self.cfg.laser_specs[wl]['coeffecients']
            else:
                coeffiecients = {}

            # Populating function with coefficients and exponents
            x = symbols('x')
            func = 0
            for order, co in coeffiecients.items():
                func = func + float(co) * x ** int(order)

            intensity = getattr(self.lasers[wl], self.cfg.laser_specs[wl]['intensity_mode']+'_setpoint')#float(self.lasers[wl].get_setpoint()) if not self.simulated else 15
            value = intensity if coeffiecients == {} else round(func.subs(x, intensity))
            unit = '%' if coeffiecients == {} and self.cfg.laser_specs[wl]['intensity_mode'] == 'current' else 'mW'
            min = 0
            max = float(getattr(self.lasers[wl], 'max_'+self.cfg.laser_specs[wl]['intensity_mode'])) if (coeffiecients == {}
                                                                   and not self.simulated) else round(func.subs(x, 100))


            # Create slider and label
            self.laser_power[f'{wl} label'], self.laser_power[wl] = self.create_widget(
                value=None,
                Qtype=QSlider,
                label=f'{wl}: {value} {unit}')
            # Set background of slider to laser color, set min, max, and current value
            self.laser_power[wl].setStyleSheet(
                f"QSlider::sub-page:horizontal{{ background-color:{self.cfg.laser_specs[wl]['color']}; }}")
            self.laser_power[wl].setMinimum(min)
            self.laser_power[wl].setMaximum(int(float(max)))
            self.laser_power[wl].setValue(int(float(value)))

            # Creating textbox for gene
            self.laser_power[f'{wl} textbox'] = QLineEdit()
            self.laser_power[f'{wl} textbox'].editingFinished.connect(lambda wl=wl: self.add_gene(wl))
            self.laser_power[f'{wl} textbox'].setMaximumWidth(50)
            # Setting activity when slider is moved (update label value)
            # or released (update laser current or power to slider setpoint)
            self.laser_power[wl].sliderReleased.connect(
                lambda value=value, unit=unit, wl=wl, curve=func, released=True:
                self.laser_power_label(value, unit, wl, curve, released))
            self.laser_power[wl].sliderMoved.connect(
                lambda value=value, unit=unit, wl=wl: self.laser_power_label(value, unit, wl))

            # Hides sliders that are not being used in imaging
            if int(wl) not in self.imaging_wavelengths:
                self.laser_power[wl].setHidden(True)
                self.laser_power[f'{wl} label'].setHidden(True)
                self.laser_power[f'{wl} textbox'].setHidden(True)
            else:
                self.instrument.channel_gene[wl] = None
            laser_power_layout[str(wl)] = self.create_layout(struct='H',
                                                             gene=self.laser_power[f'{wl} textbox'],
                                                             label=self.laser_power[f'{wl} label'],
                                                             text=self.laser_power[wl])

        return self.create_layout(struct='V', **laser_power_layout)

    def add_gene(self, wl):
        self.instrument.channel_gene[wl] = self.laser_power[f'{wl} textbox'].text()

    def laser_power_label(self, value, unit, wl: int, curve=None, release=False):

        """Set laser current or power to slider set point if released and update label if slider moved
        :param value: value of slider
        :param wl: wavelength of laser
        :param released: if slider was released
        :param command: command to send to laser. Set current or power
        """

        value = self.laser_power[wl].value()
        text = f'{wl}: {value} {unit}'
        self.laser_power[f'{wl} label'].setText(text)

        if release:
            self.log.info(f'Setting laser {wl} to {value} {unit}')

            if self.cfg.laser_specs[wl]['intensity_mode'] == 'current' and unit == 'mW':
                power = self.calculate_laser_current(curve, value)
                if power == QMessageBox.Ok:
                    return
                setattr(self.lasers[wl], self.cfg.laser_specs[wl]['intensity_mode'] + '_setpoint', round(power))
            else:
                setattr(self.lasers[wl], self.cfg.laser_specs[wl]['intensity_mode'] + '_setpoint',value)

    def laser_power_splitter(self):

        """
        Create slider for laser combiner power split
                """

        split_percentage = self.lasers['main'].get_percentage_split() if not self.simulated else '15%'
        self.combiner_power_split['Left label'] = QLabel(
            f'Left: {100 - float(split_percentage[0:-1])}%')  # Left laser is set to 100 - percentage entered
        self.combiner_power_split['slider'] = QSlider()
        self.combiner_power_split['slider'].setOrientation(QtCore.Qt.Vertical)
        self.combiner_power_split['slider'].setMinimum(0)
        self.combiner_power_split['slider'].setMaximum(100)
        self.combiner_power_split['slider'].setValue(float(split_percentage[0:-1]))
        self.combiner_power_split['slider'].sliderReleased.connect(
            lambda value=None, released=True:
            self.set_power_split(value, released))
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
            self.lasers['main'].set_percentage_split(value)
            self.log.info(f'Laser power split set. Right: {value}%  Left: {100 - int(value)}%')
