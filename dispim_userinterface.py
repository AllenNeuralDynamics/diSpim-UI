import napari
from qtpy.QtWidgets import QDockWidget
from qtpy.QtCore import QTimer
import dispim.dispim as dispim
from acquisition_params_tab import AcquisitionParamsTab
from initialize_acquisition_tab import InitializeAcquisitionTab
import logging
import traceback

class UserInterface:

    def __init__(self, config_filepath: str,
                 log_filename: str = 'debug.log',
                 console_output: bool = True,
                 console_output_level: str = 'info',
                 simulated: bool = False):
        # TODO: Create logger tab at bottom of napari viewer
        try:

           #self.log = logging.getLogger("dispim")

            self.viewer = napari.Viewer(title='diSPIM control', ndisplay=2, axis_labels=('x', 'y'))

            self.instrument = dispim.Dispim(config_filepath=config_filepath,
                                            simulated=simulated)

            self.cfg = self.instrument.cfg
            self.possible_wavelengths = self.cfg.cfg['imaging_specs']['possible_wavelengths']

            self.imaging, self.laser_slider = self.imaging_tab(simulated)
            self.imaging_specs = self.imaging_specs_tab(simulated)

            dock = {'Imaging': self.imaging,
                    'Laser Slider': self.laser_slider,
                    'Imaging Specs': self.imaging_specs,
                    }




            self.imaging_dock = self.viewer.window.add_dock_widget(dock['Imaging'], name='Imaging')
            self.imaging_dock_params = self.viewer.window.add_dock_widget(dock['Imaging Specs'],
                                                                          name='Config Inputs', area='left')
            self.viewer.window.add_dock_widget(dock['Laser Slider'], name="Laser Current", area='bottom')

            self.general_imaging.adding_wavelength_tabs(self.imaging_dock)

            self.viewer.scale_bar.visible = True
            self.viewer.scale_bar.unit = "um"
            self.viewer.window.qt_viewer.dockLayerControls.setVisible(False)
            # logging.basicConfig(level=5)
            # logging.getLogger().setLevel(5)
            napari.run()

        finally:
            traceback.print_exc()
            self.close_instrument()
            self.viewer.close()


    def imaging_specs_tab(self, simulated):
        imaging_tab = AcquisitionParamsTab(self.instrument.frame_grabber, self.cfg.sensor_column_count, simulated,
                                           self.instrument, self.cfg)
        instument_params = imaging_tab.scan_config(self.cfg)
        cpx_exposure_widget = imaging_tab.slit_width_widget()
        cpx_line_interval_widget = imaging_tab.exposure_time_widget()
        acquisition_widget = imaging_tab.create_layout('V', exp = cpx_exposure_widget,
                                                       line = cpx_line_interval_widget,
                                                       params = instument_params)
        #acquisition_widget = imaging_tab.create_layout('V', params = instument_params)
        scroll_box = imaging_tab.scroll_box(acquisition_widget)
        imaging_specs_dock = QDockWidget()
        imaging_specs_dock.setWidget(scroll_box)

        return imaging_specs_dock

    def imaging_tab(self, simulated):
        imaging = QDockWidget()
        imaging.setWindowTitle('Imaging')

        self.general_imaging = InitializeAcquisitionTab(self.viewer, self.cfg,
                                                   self.instrument, simulated)
        qframes = {
                        'live_view': self.general_imaging.live_view_widget(),
                        'grid' : self.general_imaging.grid_widget(),
                        'screenshot': self.general_imaging.screenshot_button(),
                        'position': self.general_imaging.sample_stage_position(),
                        'volumetric_image': self.general_imaging.volumeteric_imaging_button(),
                        'waveform': self.general_imaging.waveform_graph(),
                        'wavelength_select': self.general_imaging.laser_wl_select(),}

        general_imaging_tab_widget = self.general_imaging.create_layout(struct='V', **qframes)
        imaging.setWidget(general_imaging_tab_widget)

        laser_slider = self.general_imaging.laser_power_slider(self.instrument.lasers)

        return imaging, laser_slider

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
