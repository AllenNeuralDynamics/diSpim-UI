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

    def set_tab_widget(self, tab_widget:QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)

    def stage_positon_map(self, index):
        last_index = len(self.tab_widget) - 1
        if index == last_index:
            print(index)

    # @thread_worker
    # def _sample_pos_worker(self): #TODO: Make part of widget base?
    #     """Update position widgets for volumetric imaging or manually moving"""
    #
    #     while self.instrument.livestream_enabled.is_set():
    #         self.sample_pos = self.instrument.get_sample_position()
    #         for direction, value in self.sample_pos.items():
    #             if direction in self.pos_widget:
    #                 self.pos_widget[direction].setValue(value * 1 / 10)  # Units in microns
    #
    #         sleep(.5)


    def graph(self):

        w = gl.GLViewWidget()
        w.opts['distance'] = 40
        w.setWindowTitle('pyqtgraph example: GLScatterPlotItem')

        g = gl.GLGridItem()
        w.addItem(g)

        pos = np.empty((53, 3))
        size = np.empty((53))
        color = np.empty((53, 4))
        pos[0] = (1,0,0); size[0] = 0.5;   color[0] = (1.0, 0.0, 0.0, 0.5)
        pos[1] = (0,1,0); size[1] = 0.2;   color[1] = (0.0, 0.0, 1.0, 0.5)
        pos[2] = (0,0,1); size[2] = 2./3.; color[2] = (0.0, 1.0, 0.0, 0.5)

        z = 0.5
        d = 6.0
        for i in range(3,53):
            pos[i] = (0,0,z)
            size[i] = 2./d
            color[i] = (0.0, 1.0, 0.0, 0.5)
            z *= 0.5
            d *= 2.0

        sp1 = gl.GLScatterPlotItem(pos=pos, size=size, color=color, pxMode=False)
        sp1.translate(5,5,0)
        w.addItem(sp1)

        return w
