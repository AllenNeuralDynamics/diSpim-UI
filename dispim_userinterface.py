import napari
from qtpy.QtWidgets import QPushButton, QMessageBox, QLineEdit, QCheckBox, QVBoxLayout, QDockWidget, QWidget, \
    QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QScrollArea
import dispim.dispim as dispim
import logging
from dispim.compute_waveforms import generate_waveforms
import numpy as np
from acquisition_params_tab import AcquisitionParamsTab
from initialize_acquisition_tab import InitializeAcquisitionTab
from laser_wavelength_param_tabs import LaserWavelengthParamTabs
from coloredlogs import ColoredFormatter
import ctypes
import logging
import argparse
import os
import sys


class UserInterface:

    def __init__(self, config_filepath: str,
                 log_filename: str = 'debug.log',
                 console_output: bool = True,
                 console_output_level: str = 'info',
                 simulated: bool = False):
        # TODO: Create logger tab at bottom of napari viewer
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

        laser_wavelength_params = LaserWavelengthParamTabs(self.cfg, self.instrument, self.viewer)
        laser_wavelength_params.adding_wavelength_tabs(self.wavelengths, dock, self.imaging_dock)

        self.viewer.scale_bar.visible = True
        self.viewer.scale_bar.unit = "um"
        napari.run()

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

        general_imaging = InitializeAcquisitionTab(self.wavelengths, self.possible_wavelengths, self.viewer, self.cfg,
                                                   self.instrument)
        general_imaging_tab = {'live_view': general_imaging.live_view_widget(),
                               'screenshot': general_imaging.screenshot_button(),
                               #'position': general_imaging.sample_stage_position(),
                               'volumetric_image': general_imaging.volumeteric_imaging_button(),
                               'waveform': general_imaging.waveform_graph()}
        general_imaging.laser_wl_select()
        general_imaging_tab_widget = general_imaging.create_layout(struct='V', **general_imaging_tab)
        imaging.setWidget(general_imaging_tab_widget)
        return imaging

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
