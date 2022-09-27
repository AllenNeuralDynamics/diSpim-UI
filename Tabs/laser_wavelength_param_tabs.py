from tab import Tab
from qtpy.QtWidgets import QPushButton, QMessageBox, QLineEdit, QCheckBox, QVBoxLayout, QDockWidget, QWidget, \
    QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QScrollArea


class LaserWavelengthParamTabs(Tab):

    def __init__(self, cfg, instrument, viewer):
        """:param cfg: config of the current instrument
        :param instrument: instrument"""

        self.cfg = cfg
        self.instrument = instrument
        self.viewer = viewer

        pass

    def scan_wavelength_params(self, wavelength: str):
        """Scans config for relevant laser wavelength parameters
        :param wavelength: the wavelength of the laser"""

        # tab_widget_wl = {}
        laser_specs_wavelength = self.cfg.laser_specs[wavelength]
        # laser_specs = {}
        tab_widget_wl = self.scan(laser_specs_wavelength, 'laser_specs', wl=wavelength, subdict=True)

        # for keys in laser_specs_wavelength.keys():
        #     if type(laser_specs_wavelength[keys]) != dict:
        #         laser_specs[keys, '_label'], laser_specs[keys] = self.create_widget(laser_specs_wavelength[keys], keys,
        #                                                                             QLineEdit)
        #         laser_specs[keys].editingFinished.connect((lambda widget=laser_specs[keys], kw=keys:
        #                                                    self.config_change(widget, 'laser_specs', kw, wavelength)))
        #         tab_widget_wl[keys] = self.create_layout(type='H', label=laser_specs[keys, '_label'],
        #                                                  text=laser_specs[keys])
        #     else:
        #         dictionary = laser_specs_wavelength[keys]
        #         for items in dictionary.keys():
        #             laser_specs[items, '_label'], laser_specs[items] = self.create_widget(dictionary[items], items,
        #                                                                                   QLineEdit)
        #             laser_specs[items].editingFinished.connect(
        #                 (lambda widget=laser_specs[items], kw=items:
        #                  self.config_change(widget, 'laser_specs', kw, wavelength)))
        #             tab_widget_wl[items] = self.create_layout(type='H', label=laser_specs[items, '_label'],
        #                                                       text=laser_specs[items])
        return self.create_layout(struct='V', **tab_widget_wl)

    def adding_wavelength_tabs(self, wavelengths, main_dock: dict, imaging_dock):
        for wavelength in wavelengths:
            key = 'Laser_' + str(wavelength) + '_parameters'
            main_dock[key] = QDockWidget()
            main_dock[key].setWindowTitle('Laser ' + str(wavelength))
            main_dock[key] = self.scan_wavelength_params(str(wavelength))
            laser_dock = self.viewer.window.add_dock_widget(main_dock[key],
                                                            name='Wavelength ' + str(wavelength))
            self.viewer.window._qt_window.tabifyDockWidget(imaging_dock, laser_dock)
