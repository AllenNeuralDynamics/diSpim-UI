import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget, QLineEdit, QComboBox,QMessageBox,QCheckBox
import pyqtgraph.opengl as gl
import numpy as np
from napari.qt.threading import thread_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui
import qtpy.QtGui


class TissueMap(WidgetBase):

    def __init__(self, instrument):

        self.instrument = instrument
        self.cfg = self.instrument.cfg
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.pos = None
        self.plot = None
        self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]
        self.rotate = {}
        self.map = {}
        self.origin = {}

        # Initializing position shift of stage
        self.volume_pos_shift = self.remap_axis({'X': - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                            'Y': - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                            'Z': 0})


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

        self.map['color'] = QComboBox()
        self.map['color'].addItems(qtpy.QtGui.QColor.colorNames())

        self.map['mark'] = QPushButton('Set Point')
        self.map['mark'].clicked.connect(self.set_point)

        self.map['label'] = QLineEdit()
        self.map['label'].returnPressed.connect(self.set_point)

        self.map['tiling'] = QCheckBox('See Tiling')
        self.map['tiling'].stateChanged.connect(self.set_tiling)

        return self.create_layout(struct='H', **self.map)

    def set_tiling(self, state):

        # State is 2 if checkmark is pressed
        if state == 2:

            # Grid steps in samplepose coords
            self.x_grid_step_um, self.y_grid_step_um = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                        self.cfg.tile_overlap_y_percent)
            print(self.x_grid_step_um, self.y_grid_step_um)
            # Tile in sample pose coords
            self.xtiles, self.ytiles, self.ztiles = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                                                    self.cfg.tile_overlap_y_percent,
                                                                                    self.cfg.z_step_size_um,
                                                                                    self.cfg.volume_x_um,
                                                                                    self.cfg.volume_y_um,
                                                                                    self.cfg.volume_z_um)
        # State is 0 if checkmark is unpressed
        if state == 0:
            for item in self.plot.items:
                if type(item) == gl.GLBoxItem and item != self.scan_vol:
                    self.plot.removeItem(item)


    def set_point(self):

        """Set current position as point on graph"""

        coord = (self.map_pose['X'], self.map_pose['Y'], -self.map_pose['Z']) if not self.instrument.simulated else \
            np.random.randint(1000, 60000, 3)
        coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
        hue = str(self.map['color'].currentText())
        point = gl.GLScatterPlotItem(pos=coord, size=.5, color=qtpy.QtGui.QColor(hue), pxMode=False)
        info = self.map['label'].text()
        info_point = gl.GLTextItem(pos=coord, text=info, font=qtpy.QtGui.QFont('Helvetica', 10))
        self.plot.addItem(info_point)
        self.plot.addItem(point)

        self.map['label'].clear()

    @thread_worker
    def _map_pos_worker(self):
        """Update position of stage for tissue map"""

        while True:

            try:
                self.map_pose = self.instrument.sample_pose.get_position()
                #TODO: Map pose still in tigerbox coordinates need to rework when changed
                coord = {'x': self.map_pose['X'] * 0.0001,
                         'y': self.map_pose['Y'] * 0.0001,
                         'z': -self.map_pose['Z'] * 0.0001}  # if not self.instrument.simulated \
                #     else np.random.randint(-60000, 60000, 3)

                #gui_coord = self.remap_axis(coord)
                self.pos.setData(pos=[coord['x'], coord['y'], coord['z']])


                if self.instrument.start_pos == None:
                    for item in self.plot.items:
                        if type(item) == gl.GLBoxItem:
                            self.plot.removeItem(item)

                    volume_pos = {}
                    for k in coord.keys(): volume_pos[k] = self.volume_pos_shift[k]+coord[k]

                    scanning_volume = self.remap_axis({'X': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                                       'Y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                                       'Z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000})

                    self.scan_vol = self.draw_volume(volume_pos, scanning_volume)
                    self.plot.addItem(self.scan_vol)

                    if self.map['tiling'].isChecked():
                        self.draw_tiles(volume_pos)

                else:
                    #TODO: start still in tigerbox coordinates need to rework when changed
                    start = {}
                    for k in coord.keys(): start[k] = self.volume_pos_shift[k] + start[k]

                    if self.map['tiling'].isChecked():
                        self.draw_tiles(start)
                    self.draw_volume(start, self.remap_axis({'X': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                                             'Y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                                             'Z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000}))
            except:
                sleep(2)
            finally:
                sleep(.5)
                yield

    def draw_tiles(self, coord):

        "Coords in sample pose"
        # TODO: coords still in tigerbox coordinates need to rework when changed
        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            self.set_tiling(2)
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for item in self.plot.items:
            if type(item) == gl.GLBoxItem and item != self.scan_vol:
                self.plot.removeItem(item)

        for x in range(0, self.xtiles):
            for y in range(0, self.ytiles):

                tile_pos_shift = self.remap_axis({'X':(x * self.x_grid_step_um * .001),
                                                  'Y':(y * self.y_grid_step_um * .001),
                                                  'Z':0})
                tile_pos = {}
                for k in coord.keys(): tile_pos[k] = tile_pos_shift[k] + coord[k]


                tile_volume = self.remap_axis({'X':self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                               'Y':self.cfg.tile_specs['y_field_of_view_um'] * .001,
                                               'Z':0})
                tile = self.draw_volume(tile_pos,tile_volume)
                tile.setColor(qtpy.QtGui.QColor('cornflowerblue'))
                self.plot.addItem(tile)

    def draw_volume(self, coord: dict, size: dict):

        """draw and translate boxes in map. Expecting gui coordinate system"""

        box = gl.GLBoxItem()  # Representing scan volume
        box.translate(coord['x'],coord['y'],coord['z'])
        box.setSize(**size)
        return box

    def rotate_buttons(self):

        self.rotate['x-y'] = QPushButton("X/Y Plane")
        self.rotate['x-y'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(self.origin['x'], self.origin['y'], 0),
                                                  elevation=90,
                                                  azimuth = 0:
                                           self.rotate_graph(click, center, elevation, azimuth))

        self.rotate['x-z'] = QPushButton("X/Z Plane")
        self.rotate['x-z'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(self.origin['x'], 0, -self.origin['z']),
                                                  elevation=0,
                                                  azimuth = 90:
                                           self.rotate_graph(click, center, elevation, azimuth))

        self.rotate['y-z'] = QPushButton("Y/Z Plane")
        self.rotate['y-z'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(0, self.origin['y'], -self.origin['z']),
                                                  elevation=0,
                                                  azimuth = 0:
                                           self.rotate_graph(click, center, elevation, azimuth))

        return self.create_layout(struct='V', **self.rotate)

    def rotate_graph(self, click, center, elevation, azimuth):

        """Rotate graph to specific view"""

        self.plot.opts['center'] = center
        self.plot.opts['elevation'] = elevation
        self.plot.opts['azimuth'] = azimuth

    def remap_axis(self, coords: dict):

        """Remaps sample pose coordinates to gui 3d map coordinates.
        Sample pose comes in dictionary with uppercase keys and gui uses lowercase"""

        remap = {'x': 'Z', 'y': 'X', 'z': '-Y'}
        remap_coords = {}
        for k, v in remap.items():
            if '-' in v:
                v = v.lstrip('-')
                remap_coords[k] = -coords[v]
            else:
                remap_coords[k] = coords[v]

        return remap_coords

    def create_axes(self, rotation, size, translate, color=None):

        axes = gl.GLGridItem()
        axes.rotate(*rotation)
        axes.setSize(*size)
        axes.translate(*translate)  # Translate to lower end of x and origin of y and -z
        if color is not None: axes.setColor(qtpy.QtGui.QColor(color))
        self.plot.addItem(axes)

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40

        #TODO: Eventually need to be cognizant that axis will be in sample pose and change axis mapping accordingly
        dirs = ['x', 'y', 'z']
        low = {'X': 0, 'Y': 0, 'Z': 0} if self.instrument.simulated else \
            self.instrument.tigerbox.get_lower_travel_limit(*['x', 'y', 'z'])
        up = {'X': 60, 'Y': 60, 'Z': 60} if self.instrument.simulated else \
            self.instrument.tigerbox.get_upper_travel_limit(*['x', 'y', 'z'])

        print(low)
        print(up)

        axes_len = {}
        for directions in dirs:
            axes_len[directions] = (up[directions.upper()] - low[directions.upper()])
            self.origin[directions] = (low[directions.upper()] + (axes_len[directions] / 2))
        self.plot.opts['center'] = QtGui.QVector3D(self.origin['x'], self.origin['y'], -self.origin['z'])
        print(axes_len)
        print(self.origin)
        # Translate axis so origin of graph translate to center of stage limits
        # Z coords increase as stage moves down so z origin and coords are negative

        self.create_axes((90, 0, 1, 0), (axes_len['z'], axes_len['y']),(low['X'], self.origin['y'],-self.origin['z']))

        self.create_axes((90, 1, 0, 0), (axes_len['x'], axes_len['z']),(self.origin['x'], low['Y'], -self.origin['z']))

        self.create_axes((0, 0, 0, 0),(axes_len['x'],axes_len['y']), (self.origin['x'], self.origin['y'], -up['Z']))

        self.scan_vol = gl.GLBoxItem()  # Representing scan volume
        self.scan_vol.translate(self.origin['x'], self.origin['y'], -up['Z'])
        scanning_volume = self.remap_axis({'X': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                           'Y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                           'Z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000})
        self.scan_vol.setSize(**scanning_volume)
        self.plot.addItem(self.scan_vol)

        self.pos = gl.GLScatterPlotItem(pos=(1, 0, 0), size=.5, color=(1,0,0,1), pxMode=False)
        self.plot.addItem(self.pos)

        return self.plot




