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

        try:
            self.log = logging.getLogger("dispim")  # TODO: Create logger tab at bottom of napari viewer
            self.instrument = dispim.Dispim(config_filepath=config_filepath, simulated=simulated)
            self.simulated = simulated
            self.cfg = self.instrument.cfg
            self.possible_wavelengths = self.cfg.cfg['imaging_specs']['possible_wavelengths']
            self.viewer = napari.Viewer(title='diSPIM control', ndisplay=2, axis_labels=('x', 'y'))

            # Set up main window on gui which has livestreaming capability and volumeteric imaging button
            main_window = QDockWidget()
            main_window.setWindowTitle('Main')
            main_widgets = {
                                'livestream_block': self.livestream_widget(),
                                'acquisition_block': self.volumeteric_acquisition(),
                            }
            main_window.setWidget(self.vol_acq_params.create_layout(struct='V', **main_widgets))
            # Set up laser sliders and tabs
            self.laser_widget()
            # Set up automatically generated widget labels and inputs
            instr_params_window = self.instrument_params()

            # Add dockwidgets to viewer
            main_dock = self.viewer.window.add_dock_widget(main_window, name='Main Window')
            self.laser_parameters.adding_wavelength_tabs(main_dock)  # Adding laser wavelength tabs
            self.viewer.window.add_dock_widget(instr_params_window, name='Instrument Parameters', area='left')
            self.viewer.window.add_dock_widget(self.laser_slider, name="Laser Current", area='bottom')

            self.viewer.scale_bar.visible = True
            self.viewer.scale_bar.unit = "um"
            self.viewer.add_shapes(name='hist')
            napari.run()

        finally:
            traceback.print_exc()
            self.close_instrument()
            self.viewer.close()

    def instrument_params(self):
        instrument_params = InstrumentParameters(self.instrument.frame_grabber, self.cfg.sensor_column_count,
                                                 self.simulated, self.instrument, self.cfg)
        config_properties = instrument_params.scan_config(self.cfg)
        cpx_exposure_widget = instrument_params.slit_width_widget()
        cpx_line_interval_widget = instrument_params.exposure_time_widget()
        instrument_params_widget = instrument_params.create_layout('V', exp=cpx_exposure_widget,
                                                                   line=cpx_line_interval_widget,
                                                                   prop=config_properties)
        # instrument_params_widget = instrument_params.create_layout('V', params=config_properties)
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

        return self.vol_acq_params.create_layout(struct='V', **widgets)

    def laser_widget(self):

        self.laser_parameters = Lasers(self.viewer, self.cfg, self.instrument, self.simulated)
        self.laser_slider = self.laser_parameters.laser_power_slider(self.instrument.lasers)
        self.laser_wl_tabs = self.laser_parameters.laser_wl_select()

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
