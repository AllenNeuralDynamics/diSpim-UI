from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider, QLineEdit
import numpy as np
from pyqtgraph import PlotWidget, mkPen
from dispim.compute_waveforms import generate_waveforms

class VolumetericAcquisition(WidgetBase):

    def __init__(self,viewer, cfg, instrument, simulated):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.cfg = cfg
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.pos_widget = {}
        self.waveform = {}
        self.selected = {}
        self.colors = None
        self.stage_position = None
        self.data_line = None       # Lines for graph

    def sample_stage_position(self):

        """Creates labels and boxs to indicate sample position"""

        directions = ['X', 'Y', 'Z']
        self.pos_widget = {}
        self.stage_position = self.instrument.get_sample_position()

        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction], QSpinBox, f'{direction}:')
            #self.pos_widget[direction].valueChanged.connect(self.stage_position_changed)

        self.pos_widget['update'] = QPushButton()
        self.pos_widget['update'].setText('Update')
        self.pos_widget['update'].clicked.connect(self.update_sample_pos)
        #TODO:When you update position you also change value which then moves stage.
        # How to get around? Spooked adam

        return self.create_layout(struct='H', **self.pos_widget)


    def update_sample_pos(self):
        """Update position widgets for volumetric imaging or manually moving"""

        sample_pos = self.instrument.get_sample_position()
        for direction, value in sample_pos.items():
            if direction in self.pos_widget:
                self.pos_widget[direction].setValue(value)

    def stage_position_changed(self):
        self.instrument.move_sample_absolute(self.pos_widget['X'].value(), self.pos_widget['Y'].value(),
                                             self.pos_widget['Z'].value())


        print(self.instrument.get_sample_position())

    def volumeteric_imaging_button(self):

        volumetric_image = {'start': QPushButton('Start Volumetric Imaging')}
        volumetric_image['start'].clicked.connect(self.run_volumeteric_imaging)
        # Put in seperate function so upon initiation of gui, run(0 funtion does not start

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






