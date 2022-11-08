import napari
from qtpy.QtWidgets import QDockWidget
from qtpy.QtCore import QTimer
import dispim.dispim as dispim
from widgets.instrument_parameters import InstrumentParameters
from widgets.volumeteric_acquisition import VolumetericAcquisition
from widgets.livestream import Livestream
from widgets.lasers import Lasers
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
            self.log = logging.getLogger("dispim")

            self.viewer = napari.Viewer(title='diSPIM control', ndisplay=2, axis_labels=('x', 'y'))

            self.instrument = dispim.Dispim(config_filepath=config_filepath,
                                            simulated=simulated)
            self.simulated = simulated
            self.cfg = self.instrument.cfg
            self.possible_wavelengths = self.cfg.cfg['imaging_specs']['possible_wavelengths']

            imaging = QDockWidget()
            imaging.setWindowTitle('Imaging')
            acquisition_block = self.volumeteric_acquisition()
            livestream_block = self.livestream_widget()
            imaging.setWidget(self.vol_acq_params.create_layout(struct='V',
                                                                acq =acquisition_block,
                                                                live = livestream_block
                                                                ))
            laser_block = self.laser_widget()
            self.imaging_specs = self.config_properties()

            dock = {'Imaging': imaging,
                    'Laser Slider': self.laser_slider,
                    'Imaging Specs': self.imaging_specs,
                    }

            self.imaging_dock = self.viewer.window.add_dock_widget(dock['Imaging'], name='Imaging')
            self.imaging_dock_params = self.viewer.window.add_dock_widget(dock['Imaging Specs'],
                                                                          name='Config Inputs', area='left')
            self.viewer.window.add_dock_widget(dock['Laser Slider'], name="Laser Current", area='bottom')

            self.laser_parameters.adding_wavelength_tabs(self.imaging_dock)

            self.viewer.scale_bar.visible = True
            self.viewer.scale_bar.unit = "um"
            self.viewer.window.qt_viewer.dockLayerControls.setVisible(False)
            self.viewer.add_shapes(name='hist')
            napari.run()

        finally:
            traceback.print_exc()
            self.close_instrument()
            self.viewer.close()


    def config_properties(self):
        instrument_params = InstrumentParameters(self.instrument.frame_grabber, self.cfg.sensor_column_count,
                                                 self.simulated)
        config_properties = instrument_params.scan_config(self.cfg)
        cpx_exposure_widget = instrument_params.frame_grabber_exposure_time()
        cpx_line_interval_widget = instrument_params.frame_grabber_line_interval()
        # instrument_params_widget = instrument_params.create_layout('V', exp=cpx_exposure_widget,
        #                                                line=cpx_line_interval_widget,
        #                                                prop=config_properties)
        instrument_params_widget = instrument_params.create_layout('V', params=config_properties)
        scroll_box = instrument_params.scroll_box(instrument_params_widget)
        instrument_params_dock = QDockWidget()
        instrument_params_dock.setWidget(scroll_box)

        return instrument_params_dock

    def livestream_widget(self):

        self.livestream_parameters = Livestream(self.viewer, self.cfg, self.instrument, self.simulated)

        widgets = {
                        'live_view': self.livestream_parameters.liveview_widget(),
                        'grid': self.livestream_parameters.grid_widget(),
                        'screenshot': self.livestream_parameters.screenshot_button()
                  }

        return self.livestream_parameters.create_layout(struct='V', **widgets)

    def volumeteric_acquisition(self):
        imaging = QDockWidget()
        imaging.setWindowTitle('Imaging')

        self.vol_acq_params = VolumetericAcquisition(self.viewer, self.cfg, self.instrument, self.simulated)
        widgets = {
                        'position': self.vol_acq_params.sample_stage_position(),
                        'volumetric_image': self.vol_acq_params.volumeteric_imaging_button(),
                        'waveform': self.vol_acq_params.waveform_graph(),
                   }

        return self.vol_acq_params.create_layout(struct = 'V', **widgets)

    def laser_widget(self):

        self.laser_parameters = Lasers(self.viewer, self.cfg, self.instrument, self.simulated)
        self.laser_slider = self.laser_parameters.laser_power_slider(self.instrument.lasers)
        self.laser_wl_tabs = self.laser_parameters.laser_wl_select()

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
