import napari
from qtpy.QtWidgets import QDockWidget
from qtpy.QtCore import QTimer
import dispim.dispim as dispim
from acquisition_params_tab import AcquisitionParamsTab
from initialize_acquisition_tab import InitializeAcquisitionTab
import logging

class UserInterface:

    def __init__(self, config_filepath: str,
                 log_filename: str = 'debug.log',
                 console_output: bool = True,
                 console_output_level: str = 'info',
                 simulated: bool = False):
        # TODO: Create logger tab at bottom of napari viewer
        try:
            self.log = logging.getLogger("dispim")

            self.viewer = napari.Viewer(title='diSPIM control', ndisplay=2, axis_labels=('x', 'y'))

            self.instrument = dispim.Dispim(config_filepath=config_filepath,
                                            simulated=simulated)

            self.cfg = self.instrument.cfg
            self.wavelengths = self.cfg.imaging_specs['laser_wavelengths']
            self.possible_wavelengths = self.cfg.cfg['imaging_specs']['possible_wavelengths']

            dock = {'Imaging': self.imaging_tab(),
                    'Imaging Specs': self.imaging_specs_tab()}
            self.imaging_dock = self.viewer.window.add_dock_widget(dock['Imaging'], name='Imaging')
            self.imaging_dock_params = self.viewer.window.add_dock_widget(dock['Imaging Specs'],
                                                                          name='Acquisition Parameters', area='left')

            self.general_imaging.adding_wavelength_tabs(self.imaging_dock)
            self.viewer.window.add_dock_widget(self.general_imaging.laser_power_slider(self.instrument.lasers),
                                               name ="Laser Current", area ='bottom')


            self.viewer.scale_bar.visible = True
            self.viewer.scale_bar.unit = "um"
            napari.run()

        finally:
            self.instrument.close()
            with napari.gui_qt() as app:
                time_in_msec = 1000
                QTimer().singleShot(time_in_msec, app.quit)
            self.viewer.close()
            print("end")

    def imaging_specs_tab(self):
        imaging_tab = AcquisitionParamsTab()
        imaging_specs = imaging_tab.scan_config(self.cfg)
        acquisition_widget = imaging_tab.imaging_specs_container(imaging_specs)
        scroll_box = imaging_tab.scroll_box(acquisition_widget)
        imaging_specs_dock = QDockWidget()
        imaging_specs_dock.setWidget(scroll_box)
        return imaging_specs_dock

    def imaging_tab(self):
        imaging = QDockWidget()
        imaging.setWindowTitle('Imaging')

        self.general_imaging = InitializeAcquisitionTab(self.wavelengths, self.possible_wavelengths, self.viewer, self.cfg,
                                                   self.instrument)
        qframes = {'live_view': self.general_imaging.live_view_widget(),
                               'screenshot': self.general_imaging.screenshot_button(),
                               #'position': self.general_imaging.sample_stage_position(),
                               #'volumetric_image': self.general_imaging.volumeteric_imaging_button(),
                               'waveform': self.general_imaging.waveform_graph(),
                               'wavelength_select': self.general_imaging.laser_wl_select(),}

        general_imaging_tab_widget = self.general_imaging.create_layout(struct='V', **qframes)
        imaging.setWidget(general_imaging_tab_widget)
        return imaging

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
