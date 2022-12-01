import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget, QLineEdit
import pyqtgraph.opengl as gl
import numpy as np
from napari.qt.threading import thread_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui
import qtpy.QtGui as QtGui


class TissueMap(WidgetBase):

    def __init__(self, instrument):

        self.instrument = instrument
        self.cfg = self.instrument.cfg
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.pos = None
        self.plot = None

        self.map = {}

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

        self.map['mark'] = QPushButton('Set Point')
        self.map['mark'].clicked.connect(self.set_point)

        self.map['label'] = QLineEdit()
        self.map['label'].editingFinished.connect(self.set_point)

        return self.create_layout(struct='H', **self.map)

    def set_point(self):

        """Set current position as point on graph"""

        coord = (self.map_pose['X'], self.map_pose['Y'], -self.map_pose['Z'])
        coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
        point = gl.GLScatterPlotItem(pos=coord, size=.2, color=(1.0, 1.0, 0.0, 1.0), pxMode=False)
        info = self.map['label'].text()
        info_point = gl.GLTextItem(pos=coord, text=info, font=QtGui.QFont('Helvetica', 10))
        self.plot.addItem(info_point)
        self.plot.addItem(point)

        self.map['label'].clear()

    @thread_worker
    def _map_pos_worker(self):
        """Update position of stage for tissue map"""

        while True:
            self.map_pose = self.instrument.get_sample_position()
            coord = (self.map_pose['X'], self.map_pose['Y'], -self.map_pose['Z'])
            coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
            self.pos.setData(pos=coord)
            if self.instrument.start_pos == None:
                self.plot.removeItem(self.scan_vol)
                self.scan_vol = gl.GLBoxItem()  # Representing scan volume
                self.scan_vol.translate(coord[0], coord[1], coord[2])
                self.scan_vol.setSize(x=self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000,
                                      y=self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                      z=self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000)
                self.plot.addItem(self.scan_vol)
            sleep(.5)
            yield

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40

        dirs = ['x', 'y', 'z']
        low = {'X': 0, 'Y': 0, 'Z': 0} if self.instrument.simulated else \
            self.instrument.tigerbox.get_lower_travel_limit(*dirs)
        up = {'X': 60, 'Y': 60, 'Z': 60} if self.instrument.simulated else \
            self.instrument.tigerbox.get_upper_travel_limit(*dirs)
        axes_len = {}
        origin = {}
        for directions in dirs:
            axes_len[directions] = up[directions.upper()] - low[directions.upper()]
            origin[directions] = low[directions.upper()] + (axes_len[directions] / 2)

        self.plot.opts['center'] = QtGui.QVector3D(origin['x'], origin['y'], -origin['z'])

        # Translate axis so origin of graph translate to center of stage limits
        # Z coords increase as stage moves down so z origin and coords are negative

        axes_x = gl.GLGridItem()
        axes_x.rotate(90, 0, 1, 0)
        axes_x.setSize(x=round(axes_len['z']), y=round(axes_len['y']))
        axes_x.translate(low['X'], origin['y'], -low['Z'])  # Translate to lower end of x and z and origin of y
        self.plot.addItem(axes_x)

        axes_y = gl.GLGridItem()
        axes_y.rotate(90, 1, 0, 0)
        axes_y.setSize(x=round(axes_len['x']), y=round(axes_len['z']))
        axes_y.translate(origin['x'], low['Y'], -low['Z'])  # Translate to lower end of y and z and origin of x
        self.plot.addItem(axes_y)

        axes_z = gl.GLGridItem()
        axes_z.setSize(x=round(axes_len['x']), y=round(axes_len['y']))
        axes_z.translate(origin['x'], origin['y'], -origin['z'])  # Translate to origin of x, y, z
        self.plot.addItem(axes_z)
        coord = (1, 0, 0)
        size = 1
        color = (1.0, 0.0, 0.0, 0.5)

        self.scan_vol = gl.GLBoxItem()      # Representing scan volume
        self.scan_vol.translate(origin['x'], origin['y'], -origin['z'])
        self.scan_vol.setSize(x=self.cfg.imaging_specs[f'volume_z_um']*1/1000,
                              y=self.cfg.imaging_specs[f'volume_x_um']*1/1000,
                              z=self.cfg.imaging_specs[f'volume_y_um']*1/1000)
        #Remapping tiger axis to sample ['z', 'x', 'y']
        self.plot.addItem(self.scan_vol)

        self.pos = gl.GLScatterPlotItem(pos=coord, size=size, color=color, pxMode=False)
        self.plot.addItem(self.pos)

        return self.plot
