import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget
import pyqtgraph.opengl as gl
import numpy as np
from napari.qt.threading import thread_worker
from time import sleep
import qtpy.QtGui as QtGui


class TissueMap(WidgetBase):

    def __init__(self, instrument):

        self.instrument = instrument
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.pos = None
        self.plot = None

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)

    def stage_positon_map(self, index):
        last_index = len(self.tab_widget) - 1
        if index == last_index:
            self.map_pos_worker = self._map_pos_worker()
            self.map_pos_worker.start()
            # TODO: Start stage position worker
            # if start position is not none, update start position, volume, and
            # outline box which is going to be image

        else:
            if self.map_pos_worker is not None:
                self.map_pos_worker.quit()
            pass

    def mark_graph(self):

        """Mark graph with pertinent landmarks"""

        mark = QPushButton('Set Point')
        mark.clicked.connect(self.set_point)

        return mark

    def set_point(self):

        """Set current position as point on graph"""

        coord = (self.map_pose['X'], self.map_pose['Y'], self.map_pose['Z'])
        coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
        point = gl.GLScatterPlotItem(pos=coord, size=1, color=(1.0, 1.0, 0.0, 1.0), pxMode=False)
        self.plot.addItem(point)


    @thread_worker
    def _map_pos_worker(self):
        """Update position of stage for tissue map"""

        while True:
            self.map_pose = self.instrument.get_sample_position()
            coord = (self.map_pose['X'], self.map_pose['Y'], self.map_pose['Z'])
            coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
            self.pos.setData(pos=coord)
            sleep(.5)

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40
        self.plot.setWindowTitle('pyqtgraph example: GLScatterPlotItem')

        dirs = ['x', 'y', 'z']
        low = {'X': 0, 'Y': 0} if self.instrument.simulated else self.instrument.tigerbox.get_lower_travel_limit(*dirs)
        up = {'X': 60, 'Y': 60} if self.instrument.simulated else self.instrument.tigerbox.get_upper_travel_limit(*dirs)

        axes_len = {}
        origin = {}
        for directions in dirs:
            axes_len[directions] = up[directions.upper()] - low[directions.upper()]
            origin[directions] = low[directions.upper()] + (axes_len[directions]/2)

        self.plot.opts['center'] = QtGui.QVector3D(origin['x'], origin['y'], origin['z'])

        axes = gl.GLGridItem()
        axes.setSize(x=round(axes_len['x']), y=round(axes_len['y']))    # Setting axes size to bonds of stage
        axes.translate(origin['x'], origin['y'], origin['z'])   # Translating axes into stage coordinates
        self.plot.addItem(axes)

        coord = (1, 0, 0)
        size = 1
        color = (1.0, 0.0, 0.0, 0.5)

        self.pos = gl.GLScatterPlotItem(pos=coord, size=size, color=color, pxMode=False)
        self.plot.addItem(self.pos)

        return self.plot
