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

        self.pos_widget = {}
        self.waveform = {}
        self.selected = {}
        self.pos_widget = {}    # Holds widgets related to sample position
        self.set_volume = {}    # Holds widgets related to setting volume limits during scan
        self.volume = {}        # Dictionary of x, y, z volume for scan
        self.colors = None
        self.stage_position = None
        self.data_line = None       # Lines for graph

    def sample_stage_position(self):

        """Creates labels and boxs to indicate sample position"""

        directions = ['X', 'Y', 'Z']
        self.stage_position = self.instrument.get_sample_position()

        #Create X, Y, Z labels and displays for where stage is
        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction], QSpinBox, f'{direction}:')
            self.pos_widget[direction].setReadOnly(True)

        # Update sample position in gui when pressed
        self.set_volume['update'] = QPushButton()
        self.set_volume['update'].setText('Update')
        self.set_volume['update'].clicked.connect(self.update_sample_pos)
        #TODO:When you update position you also change value which then moves stage.
        # How to get around? Spooked adam

        # Sets start position of scan to current position of sample
        self.set_volume['set_start'] = QPushButton()
        self.set_volume['set_start'].setText('Set Scan Start')

        # Sets start position of scan to current position of sample
        self.set_volume['set_end'] = QPushButton()
        self.set_volume['set_end'].setText('Set Scan End')
        self.set_volume['set_end'].setHidden(True)

        self.pos_widget['volume_widgets'] = self.create_layout(struct='V', **self.set_volume)

        return self.create_layout(struct='H', **self.pos_widget)


    def update_sample_pos(self):
        """Update position widgets for volumetric imaging or manually moving"""

        sample_pos = self.instrument.get_sample_position()
        for direction, value in sample_pos.items():
            if direction in self.pos_widget:
                self.pos_widget[direction].setValue(value)

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






