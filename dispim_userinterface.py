import napari
from qtpy.QtWidgets import QDockWidget, QTabWidget,QPlainTextEdit, QDialog, QFrame, QMessageBox, QInputDialog, \
    QLineEdit, QWidget
from PyQt5 import QtWidgets
import ispim.ispim as ispim
from widgets.instrument_parameters import InstrumentParameters
from widgets.volumeteric_acquisition import VolumetericAcquisition
from widgets.livestream import Livestream
from widgets.lasers import Lasers
from widgets.tissue_map import TissueMap
import traceback
import pyqtgraph.opengl as gl
import io
import logging
import numpy as np

class UserInterface:

    def __init__(self, config_filepath: str,
                 log_filename: str = 'debug.log',
                 console_output: bool = True,
                 console_output_level: str = 'info',
                 simulated: bool = False):

        #try:

            self.instrument = ispim.Ispim(config_filepath=config_filepath, simulated=simulated)
            self.simulated = simulated
            self.cfg = self.instrument.cfg
            self.viewer = napari.Viewer(title='ISPIM control', axis_labels=('y','x'))
            self.experimenters_name_popup()         # Popup for experimenters name.
                                                    # Determines what parameters will be exposed
            # Set up laser sliders and tabs
            self.laser_widget()

            # Set up automatically generated widget labels and inputs
            instr_params_window = self.instrument_params_widget()

            # Set up main window on gui which combines livestreaming and volumeteric imaging
            main_window = QDockWidget()
            main_window.setWindowTitle('Main')
            main_widgets = {
                'main_block': self.instrument_params.create_layout(struct='V',
                                                                      live = self.livestream_widget(),
                                                                      vol = self.volumeteric_acquisition_widget()),
                'stage_slider': self.livestream_parameters.move_stage_widget(),
            }
            main_widgets['stage_slider'].setMaximumWidth(100)
            main_window.setWidget(self.instrument_params.create_layout(struct='H', **main_widgets))

            # Set up laser window combining laser sliders and selection
            laser_window = QDockWidget()
            laser_widget = {
                'laser_slider': self.laser_slider,
                'laser_select': self.laser_wl_select,
            }
            laser_window.setWidget(self.laser_parameters.create_layout(struct='H', **laser_widget))

            # Set up tissue map widget
            self.tissue_map_window = self.tissue_map_widget()

            # Add dockwidgets to viewer
            tabbed_widgets = QTabWidget()  # Creating tab object
            tabbed_widgets.setTabPosition(QTabWidget.South)
            tabbed_widgets.addTab(main_window, 'Main Window')  # Adding main window tab
            tabbed_widgets = self.laser_parameters.add_wavelength_tabs(tabbed_widgets)  # Generate laser wl tabs
            tabbed_widgets.addTab(self.tissue_map_window, 'Tissue Map')  # Adding tissue map tab
            self.tissue_map.set_tab_widget(tabbed_widgets)  # Passing in tab widget to tissue map
            self.livestream_parameters.set_tab_widget(tabbed_widgets)  # Passing in tab widget to livestream
            self.vol_acq_params.set_tab_widget(tabbed_widgets)
            tabbed_widgets.setMinimumHeight(700)


            # Widget contains start/stop, wl select, and progress bar
            liveview_widget = self.livestream_parameters.create_layout(struct='V',
                                                                        wv = self.livestream_parameters.liveview_widget(),
                                                                        progress_bar = self.vol_acq_params.progress_bar_widget())
            liveview_widget.setMaximumHeight(70)

            main_page = self.livestream_parameters.create_layout(struct='V',
                                                            live=liveview_widget,
                                                            tab=tabbed_widgets)     # Adding liveview on top of tabs

            self.viewer.window.add_dock_widget(main_page, name=' ')  # Adding tabs to window

            # TODO: Move set scan to tissue map tab?

            self.viewer.window.add_dock_widget(instr_params_window, name='Instrument Parameters', area='left')
            self.viewer.window.add_dock_widget(laser_window, name="Laser Current", area='bottom')

            self.viewer.scale_bar.visible = True
            self.viewer.scale_bar.unit = "um"
            self.viewer.axes.visible = True

            # hide layers with <hidden> in name
            self.viewer.window.qt_viewer.layers.model().filterAcceptsRow = self._filter

        # finally:
        #     self.close_instrument()

    def instrument_params_widget(self):
        self.instrument_params = InstrumentParameters(self.instrument.frame_grabber, self.cfg.sensor_column_count,
                                                      self.simulated, self.instrument, self.cfg)

        tabbed_widgets = QTabWidget()  # Creating tab object
        tabbed_widgets.setTabPosition(QTabWidget.North)
        tabbed_widgets.addTab(self.instrument_params.joystick_remap_tab(), 'Joystick')
        x_game_mode = ['Micah Woodard', 'Xiaoyun Jiang', 'Adam Glaser', 'Joshua Vasquez', 'Kevin Cao', 'Christian Bonatto', 'Erica Peterson']
        if self.cfg.experimenters_name not in x_game_mode:
            widgets = {'config_properties': self.instrument_params.scan_config(self.cfg, False)}
            tabbed_widgets.setTabVisible(0, False) # Hide joystick
        else:
            widgets = {
                'filetype_widget': self.instrument_params.filetype_widget(),
                'cpx_scan_direction_widget': self.instrument_params.shutter_direction_widgets(),
                'cpx_line_interval_widget': self.instrument_params.exposure_time_widget(),
                'cpx_exposure_widget': self.instrument_params.slit_width_widget(),
                'config_properties': self.instrument_params.scan_config(self.cfg, x_game_mode),
            }


        instrument_params_widget = self.instrument_params.create_layout('V', **widgets)
        # Needs work to make this functional
        # instrument_params_widget.setAcceptDrops(True)
        # instrument_params_widget.dragEnterEvent = self.instrument_params.dragEnterEvent
        # instrument_params_widget.dragMoveEvent = self.instrument_params.dragMoveEvent
        # instrument_params_widget.dropEvent = self.instrument_params.dropEvent
        scroll_box = self.instrument_params.scroll_box(instrument_params_widget)
        instrument_params_dock = QDockWidget()
        instrument_params_dock.setWidget(scroll_box)
        tabbed_widgets.addTab(instrument_params_dock, 'Parameters')
        tabbed_widgets.setCurrentIndex(1)

        return tabbed_widgets

    def livestream_widget(self):

        self.livestream_parameters = Livestream(self.viewer, self.cfg, self.instrument, self.simulated)

        widgets = {
            'screenshot': self.livestream_parameters.screenshot_button(),
            'position': self.livestream_parameters.sample_stage_position(),
        }

        return self.livestream_parameters.create_layout(struct='V', **widgets)

    def volumeteric_acquisition_widget(self):

        self.vol_acq_params = VolumetericAcquisition(self.viewer, self.cfg, self.instrument, self.simulated)
        widgets = {
            'volumetric_image': self.vol_acq_params.volumeteric_imaging_button(),
            'waveform': self.vol_acq_params.waveform_graph(),
        }

        return self.vol_acq_params.create_layout(struct='V', **widgets)

    def laser_widget(self):

        self.laser_parameters = Lasers(self.viewer, self.cfg, self.instrument, self.simulated)

        if 'main' in self.cfg.laser_specs.keys():
            widgets = {
                'splitter': self.laser_parameters.laser_power_splitter(),
                'power': self.laser_parameters.laser_power_slider(),
            }
        else:
            widgets = {
                'power': self.laser_parameters.laser_power_slider(),
            }
        self.laser_wl_select = self.laser_parameters.laser_wl_select()
        self.laser_slider = self.laser_parameters.create_layout(struct='H', **widgets)

    def tissue_map_widget(self):

        self.tissue_map = TissueMap(self.instrument, self.viewer)
        quick_scan_widget = self.tissue_map.overview_widget()
        # Connect quick scan to progress bar
        quick_scan_widget.children()[1].released.connect(lambda: self.vol_acq_params._progress_bar_worker().start())
        # Add scans to tissue map
        self.vol_acq_params.volumetric_image['start'].menu().aboutToHide.connect(lambda:self.tissue_map.draw_configured_scans(self.vol_acq_params.acquisition_order))
        self.vol_acq_params.volumetric_image['start'].menu().actions()[0].triggered.connect(lambda:self.tissue_map.draw_configured_scans(self.vol_acq_params.acquisition_order))
        widgets = {
            'graph': self.tissue_map.graph(),
            'functions': self.tissue_map.create_layout
            (struct='H',point=self.tissue_map.mark_graph(),
                                                       quick_scan = quick_scan_widget)
        }

        widgets['functions'].setMaximumHeight(100)

        return self.tissue_map.create_layout(struct='V', **widgets)


    def experimenters_name_popup(self):

        """Pop up window asking for experimenters name"""

        text, pressed = QInputDialog.getText(QWidget(), "Experimenter's Name",
                                             "Please Enter Experimenter's Name")

        if pressed is False or (text == '' and pressed is True):
            self.experimenters_name_popup()

        self.cfg.experimenters_name = text

    def _filter(self,row, parent):
        return "<hidden>" not in self.viewer.layers[row].name

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
