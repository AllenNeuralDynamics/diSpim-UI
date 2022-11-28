import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget
import pyqtgraph.opengl as gl
import numpy as np
from napari.qt.threading import thread_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui


class TissueMap(WidgetBase):

    def __init__(self, instrument):

        self.instrument = instrument
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.sample_pos_worker = None
        self.pos = None
        self.plot = None

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)

    def stage_positon_map(self, index):
        last_index = len(self.tab_widget) - 1
        if index == last_index:
            self.sample_pos_worker = self._sample_pos_worker()
            self.sample_pos_worker.start()
            # TODO: Start stage position worker
            # if start position is not none, update start position, volume, and
            # outline box which is going to be image

        else:
            if self.sample_pos_worker is not None:
                self.sample_pos_worker.quit()
            pass

    def mark_graph(self):

        """Mark graph with pertinent landmarks"""

        mark = QPushButton('Set Point')
        mark.clicked.connect(self.set_point)

        return mark

    def set_point(self):

        """Set current position as point on graph"""

        sample_pos = self.instrument.get_sample_position()
        coord = (sample_pos['X'], sample_pos['Y'], sample_pos['Z'])
        coord = [i * 0.0001 for i in coord] # converting from 1/10um to mm
        point = gl.GLScatterPlotItem(pos=coord, size=1, color=(1.0, 1.0, 0.0, 1.0), pxMode=False)
        self.plot.addItem(point)


    @thread_worker
    def _sample_pos_worker(self):
        """Update position of stage for tissue map"""

        while True:
            self.sample_pos = self.instrument.get_sample_position()
            coord = (self.sample_pos['X'], self.sample_pos['Y'], self.sample_pos['Z'])
            coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
            self.pos.setData(pos=coord)
            sleep(.5)

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40
        self.plot.setWindowTitle('pyqtgraph example: GLScatterPlotItem')

        dirs = ['x', 'y']
        low = {'X': 0, 'Y': 0} if self.instrument.simulated else self.instrument.tigerbox.get_lower_travel_limit(*dirs)
        up = {'X': 60, 'Y': 60} if self.instrument.simulated else self.instrument.tigerbox.get_upper_travel_limit(*dirs)
        axes_size = {}
        for directions in dirs:
            axes_size[directions] = up[directions.upper()] - low[directions.upper()]

        axes = gl.GLGridItem()
        axes.setSize(x=axes_size['x'], y=axes_size['y'])
        self.plot.addItem(axes)

        coord = (1, 0, 0)
        size = 1
        color = (1.0, 0.0, 0.0, 0.5)

        self.pos = gl.GLScatterPlotItem(pos=coord, size=size, color=color, pxMode=False)
        self.plot.addItem(self.pos)

        return self.plot
