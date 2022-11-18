from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider, QLineEdit
import numpy as np
from pyqtgraph import PlotWidget, mkPen
from dispim.compute_waveforms import generate_waveforms
import logging

class VolumetericAcquisition(WidgetBase):

    def __init__(self,viewer, cfg, instrument, simulated):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.cfg = cfg
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.waveform = {}
        self.selected = {}
        self.data_line = None       # Lines for graph

    def volumeteric_imaging_button(self):

        volumetric_image = {'start': QPushButton('Start Volumetric Imaging')}
        volumetric_image['start'].clicked.connect(self.run_volumeteric_imaging)
        # Put in seperate function so upon initiation of gui, run() funtion does not start

        return self.create_layout(struct='H', **volumetric_image)

    def run_volumeteric_imaging(self):

        self.instrument.run(overwrite=True)

        # TODO: Add a warning if about to overwrite

    def waveform_graph(self):

        """Generate a graph of waveform for sanity check"""
        # TODO: change colors and make it a different pop up window. As of now it will interfere with widget placement
        self.waveform['generate'] = QPushButton('Generate Waveforms')
        self.colors = np.random.randint(0, 255,
                                        [12, 3])  # rework this so the colors are set and laser colors are consistent
        self.waveform['graph'] = PlotWidget()
        self.waveform['generate'].clicked.connect(self.waveform_update)

        return self.waveform['generate']

    def waveform_update(self):
        t, voltages_t = generate_waveforms(self.cfg, 488) #TODO: Rework so it's using active laser

        self.waveform['graph'].clear()
        for index, ao_name in enumerate(self.cfg.daq_ao_names_to_channels.keys()):
            self.waveform['graph'].addLegend(offset=(365, .5), horSpacing=20, verSpacing=0, labelTextSize='8pt')
            self.waveform['graph'].plot(t, voltages_t[index], name=ao_name,
                                        pen=mkPen(color=self.colors[index], width=3))
        try:
            self.viewer.window.remove_dock_widget(self.waveform['graph'])
        except LookupError:
            pass
        finally:
            self.viewer.window.add_dock_widget(self.waveform['graph'])






