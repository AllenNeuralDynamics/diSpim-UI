import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget, QLineEdit, QComboBox, QMessageBox, QCheckBox
import pyqtgraph.opengl as gl
import numpy as np
import pyqtgraph as pg
from napari.qt.threading import thread_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui
import qtpy.QtGui
import stl
import cv2


class TissueMap(WidgetBase):

    def __init__(self, instrument):

        self.instrument = instrument
        self.cfg = self.instrument.cfg
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.pos = None
        self.plot = None

        self.rotate = {}
        self.map = {}
        self.origin = {}
        self.quick_scan = {}

        self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]
        self.sample_pose_remap = self.cfg.sample_pose_kwds['axis_map']
        self.og_axis_remap = {v: k for k, v in self.sample_pose_remap.items()}
        self.tiles = {}  # Tile in sample pose coords
        self.grid_step_um = {}  # Grid steps in samplepose coords
        self.scale = [self.cfg.tile_specs['x_field_of_view_um'] / self.cfg.sensor_row_count * 0.001,
                      self.cfg.tile_specs['y_field_of_view_um'] / self.cfg.sensor_column_count * 0.001]

    def set_tab_widget(self, tab_widget: QTabWidget):

        """Set the tabwidget that contains main, wavelength, and tissue map tab"""

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)  # When tab bar is clicked see what tab its on

    def stage_positon_map(self, index):

        """Check if tab clicked is tissue map tab and start stage update when on tissue map tab
        :param index: clicked tab index. Tissue map is last tab"""

        last_index = len(self.tab_widget) - 1
        if index == last_index:  # Start stage update when on tissue map tab
            self.map_pos_worker = self._map_pos_worker()
            self.map_pos_worker.start()

        else:  # Quit updating tissue map if not on tissue map tab
            if self.map_pos_worker is not None:
                self.map_pos_worker.quit()

            pass

    def quick_scan_widget(self):

        """Widgets for setting up a quick scan"""

        self.quick_scan['start'] = QPushButton('Start quick scan')
        self.quick_scan['start'].clicked.connect(self.overview)

        self.quick_scan['laser'] = QComboBox()
        self.quick_scan['laser'].addItems([str(x) for x in self.cfg.laser_wavelengths])

        return self.create_layout(struct='V', **self.quick_scan)

    def overview(self):

        """Start overview function of instrument"""
        self.map_pos_worker.quit()  # Stopping tissue map update
        for i in range(1, len(self.tab_widget)): self.tab_widget.setTabEnabled(i, False)  # Disable tabs during scan

        # overview_array, xtiles, ytiles = self.instrument.quick_scan()                     # returns np array of overview image
        # cv2.imwrite(
        #     fr'{self.cfg.local_storage_dir}\overview_img_{"_".join(map(str, self.cfg.imaging_wavelengths))}.tiff',
        #     overview_array)     # Save overview
        overview_array = cv2.imread(fr'{self.cfg.local_storage_dir}\overview_img_{"_".join(map(str, self.cfg.imaging_wavelengths))}.tiff', -1)
        overview_RGBA = pg.makeRGBA(np.rot90(overview_array) ,levels=[overview_array.min(), overview_array.max()])[0]   # GLImage needs to be RGBA
        gl_overview = gl.GLImageItem(overview_RGBA)
        gl_overview.scale((overview_RGBA.shape[1]/self.cfg.imaging_specs[f'volume_x_um'] * 0.001)/2,  # columns
                          (overview_RGBA.shape[0]/self.cfg.imaging_specs[f'volume_z_um'] * 0.001)/2,  # rows
                          0, local=False)  # Scale Image

        coord = {k: v * 0.0001 for k, v in self.map_pose.items()}
        gui_coord = self.remap_axis({'x': coord['x'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                      'y': coord['y'] - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                      'z': coord['z']})
        gl_overview.translate(gui_coord['x'], gui_coord['y'], gui_coord['z'])
        self.plot.addItem(gl_overview)

        for i in range(1, len(self.tab_widget)): self.tab_widget.setTabEnabled(i, True)  # Enabled tabs
        self.tab_widget.setCurrentIndex(len(self.tab_widget) - 1)

        self.map_pos_worker = self._map_pos_worker()
        self.map_pos_worker.start()  # Restart map update

    def mark_graph(self):

        """Mark graph with pertinent landmarks"""

        self.map['color'] = QComboBox()
        self.map['color'].addItems(qtpy.QtGui.QColor.colorNames())  # Add all QtGui Colors to drop down box

        self.map['mark'] = QPushButton('Set Point')
        self.map['mark'].clicked.connect(self.set_point)  # Add point when button is presses

        self.map['label'] = QLineEdit()
        self.map['label'].returnPressed.connect(self.set_point)  # Add text when button is pressed

        self.map['tiling'] = QCheckBox('See Tiling')
        self.map['tiling'].stateChanged.connect(self.set_tiling)  # Display tiling of scan when checked

        return self.create_layout(struct='V', **self.map)

    def set_tiling(self, state):

        """Calculate grid steps and number of tiles for scan volume in config.
        :param state: state of QCheckbox when clicked. State 2 means checkmark is pressed: state 0 unpressed"""

        # State is 2 if checkmark is pressed
        if state == 2:
            # Grid steps in sample pose coords
            self.x_grid_step_um, self.y_grid_step_um = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                        self.cfg.tile_overlap_y_percent)
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

        # Remap sample_pos to gui coords and convert 1/10um to mm
        gui_coord = self.remap_axis(
            {k: v * 0.0001 for k, v in self.map_pose.items()})  # if not self.instrument.simulated \
        #     else np.random.randint(-60000, 60000, 3)
        gui_coord = [i for i in gui_coord.values()]  # Coords for point needs to be a list
        hue = str(self.map['color'].currentText())  # Color of point determined by drop down box
        point = gl.GLScatterPlotItem(pos=gui_coord, size=.35, color=qtpy.QtGui.QColor(hue), pxMode=False)
        info = self.map['label'].text()  # Text comes from textbox
        info_point = gl.GLTextItem(pos=gui_coord, text=info, font=qtpy.QtGui.QFont('Helvetica', 15))
        self.plot.addItem(info_point)  # Add items to plot
        self.plot.addItem(point)

        self.map['label'].clear()  # Clear text box

    @thread_worker
    def _map_pos_worker(self):

        """Update position of stage for tissue map, draw scanning volume, and tiling"""

        while True:

            try:
                self.map_pose = self.instrument.sample_pose.get_position()
                # Convert 1/10um to mm
                coord = {k: v * 0.0001 for k, v in self.map_pose.items()}  # if not self.instrument.simulated \
                #     else np.random.randint(-60000, 60000, 3)

                gui_coord = self.remap_axis(coord)  # Remap sample_pos to gui coords
                
                self.stage = gl.GLMeshItem(meshdata=self.stage_data, smooth=True, drawFaces=True, drawEdges=False,
                                          color=(0.5, 0.5, 0.5, 0.5),
                                          shader='edgeHilight')
                self.stage.scale(.01, .01, .01)
                self.stage.translate(gui_coord['x'], gui_coord['y'], gui_coord['z'])
                self.plot.addItem(self.stage)
                # if self.instrument.start_pos == None:
                #     for item in self.plot.items:  # Remove previous scan vol and tiles
                #         if type(item) == gl.GLBoxItem and item != self.scan_vol:
                #             self.plot.removeItem(item)
                #
                #     # Shift position of scan vol to center of camera fov and convert um to mm
                #     volume_pos = {'x': coord['x'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                #                   'y': coord['y'] - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                #                   'z': coord['z']}
                #     # Translate volume of scan to gui coordinate plane
                #     scanning_volume = self.remap_axis({k : self.cfg.imaging_specs[f'volume_{k}_um'] * .001
                #                                        for k in self.map_pose.keys()})
                #
                #     self.scan_vol = self.draw_volume(self.remap_axis(volume_pos), scanning_volume)  # Draw volume
                #     self.plot.addItem(self.scan_vol)  # Add volume to graph
                #
                #     if self.map['tiling'].isChecked():
                #         self.draw_tiles(volume_pos)  # Draw tiles if checkbox is checked

                # else:
                #
                #     # Remap start position and shift position of scan vol to center of camera fov and convert um to mm
                #     start_pos = {k: v * 0.001 for k, v in self.instrument.start_pos.items()}  # start of scan coords
                #     start_pos = self.remap_axis(
                #         {'x': start_pos['x'] - (.5 * self.cfg.tile_specs['x_field_of_view_um']),
                #          'y': start_pos['y'] - (.5 * self.cfg.tile_specs['y_field_of_view_um']),
                #          'z': start_pos['z']})
                #
                #     if self.map['tiling'].isChecked():
                #         self.draw_tiles(start_pos)
                #     self.draw_volume(start_pos, self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 0.001,
                #                                                  'y': self.cfg.imaging_specs[f'volume_y_um'] * 0.001,
                #                                                  'z': self.cfg.imaging_specs[f'volume_z_um'] * 0.001}))
            # except:
            #     # In case Tigerbox throws an error
            #     sleep(2)
            #     yield  # Yield so thread can stop
            finally:
                sleep(.5)
                yield  # Yield so thread can stop

    def draw_tiles(self, coord):

        """Draw tiles of proposed scan volume.
        :param coord: coordinates of bottom corner of volume in sample pose"""

        # Check if volume in config has changed
        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            self.set_tiling(2)  # Update grid steps and tile numbers
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for item in self.plot.items:
            if type(item) == gl.GLBoxItem and item != self.scan_vol:
                self.plot.removeItem(item)

        for x in range(0, self.xtiles):
            for y in range(0, self.ytiles):
                tile_pos = self.remap_axis({'x': (x * self.x_grid_step_um * .001) + coord['x'],
                                            'y': (y * self.y_grid_step_um * .001) + coord['y'],
                                            'z': coord['z']})

                tile_volume = self.remap_axis({'x': self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                               'y': self.cfg.tile_specs['y_field_of_view_um'] * .001,
                                               'z': self.ztiles * self.cfg.z_step_size_um * .001})
                tile = self.draw_volume(tile_pos, tile_volume)
                tile.setColor(qtpy.QtGui.QColor('cornflowerblue'))
                self.plot.addItem(tile)

    def draw_volume(self, coord: dict, size: dict):

        """draw and translate boxes in map. Expecting gui coordinate system"""

        box = gl.GLBoxItem()  # Representing scan volume
        box.translate(coord['x'], coord['y'], coord['z'])
        box.setSize(**size)
        return box

    def rotate_buttons(self):

        self.rotate['x-y'] = QPushButton("X/Y Plane")
        self.rotate['x-y'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(self.origin['x'], self.origin['y'], 0),
                                                  elevation=90,
                                                  azimuth=0:
                                           self.rotate_graph(click, center, elevation, azimuth))

        self.rotate['x-z'] = QPushButton("X/Z Plane")
        self.rotate['x-z'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(self.origin['x'], 0, -self.origin['z']),
                                                  elevation=0,
                                                  azimuth=90:
                                           self.rotate_graph(click, center, elevation, azimuth))

        self.rotate['y-z'] = QPushButton("Y/Z Plane")
        self.rotate['y-z'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(0, self.origin['y'], -self.origin['z']),
                                                  elevation=0,
                                                  azimuth=0:
                                           self.rotate_graph(click, center, elevation, azimuth))

        return self.create_layout(struct='V', **self.rotate)

    def rotate_graph(self, click, center, elevation, azimuth):

        """Rotate graph to specific view"""

        self.plot.opts['center'] = center
        self.plot.opts['elevation'] = elevation
        self.plot.opts['azimuth'] = azimuth

    def create_axes(self, rotation, size, translate, color=None):

        axes = gl.GLGridItem()
        axes.rotate(*rotation)
        axes.setSize(*size)
        axes.translate(*translate)  # Translate to lower end of x and origin of y and -z
        if color is not None: axes.setColor(qtpy.QtGui.QColor(color))
        self.plot.addItem(axes)

    def remap_axis(self, coords: dict):

        """Remaps sample pose coordinates to gui 3d map coordinates.
        Sample pose comes in dictionary with uppercase keys and gui uses lowercase"""

        remap = {'x': 'z', 'y': 'x', 'z': '-y'}
        remap_coords = {}

        for k, v in remap.items():
            if '-' in v:
                v = v.lstrip('-')
                remap_coords[k] = [i * -1 for i in coords[v]] \
                    if type(coords[v]) is list else -coords[v]
            else:
                remap_coords[k] = [i for i in coords[v]] \
                    if type(coords[v]) is list else coords[v]

        return remap_coords

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40

        limits = self.remap_axis({'x': [0, 45], 'y': [0, 60], 'z': [0, 55]}) if self.instrument.simulated else \
            self.remap_axis(self.instrument.sample_pose.get_travel_limits(*['x', 'y', 'z']))

        low = {}
        up = {}
        axes_len = {}
        for dirs in limits:
            low[dirs] = limits[dirs][0] if limits[dirs][0] < limits[dirs][1] else limits[dirs][1]
            up[dirs] = limits[dirs][1] if limits[dirs][1] > limits[dirs][0] else limits[dirs][0]
            axes_len[dirs] = abs(round(up[dirs] - low[dirs]))
            self.origin[dirs] = low[dirs] + (axes_len[dirs] / 2)

        self.plot.opts['center'] = QtGui.QVector3D(self.origin['x'], self.origin['y'], self.origin['z'])

        # x axes: Translate axis so origin of graph translate to center of stage limits
        # Z coords increase as stage moves down so z origin and coords are negative
        self.create_axes((90, 0, 1, 0),
                         (axes_len['z'], axes_len['y']),
                         (low['x'], self.origin['y'], self.origin['z']))

        # y axes: Translate to lower end of y and origin of x and -z
        self.create_axes((90, 1, 0, 0),
                         (axes_len['x'], axes_len['z']),
                         (self.origin['x'], low['y'], self.origin['z']))

        # z axes: Translate to origin of x, y, z
        self.create_axes((0, 0, 0, 0),
                         (axes_len['x'], axes_len['y']),
                         (self.origin['x'], self.origin['y'], low['z']))

        # Representing scan volume
        self.scan_vol = gl.GLBoxItem()
        self.scan_vol.translate(self.origin['x']- (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                self.origin['y']- (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                up['z']-(axes_len['z']/2))
        scanning_volume = self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                           'y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                           'z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000})

        self.scan_vol.setSize(**scanning_volume)
        self.plot.addItem(self.scan_vol)

        stl_mesh = stl.mesh.Mesh.from_file(r'C:\Users\Administrator\Downloads\objective_1.stl')
        points = stl_mesh.points.reshape(-1, 3)
        faces = np.arange(points.shape[0]).reshape(-1, 3)

        mesh_data = gl.MeshData(vertexes=points, faces=faces)
        mesh = gl.GLMeshItem(meshdata=mesh_data, smooth=True, drawFaces=True, drawEdges=False, color=(0.5, 0.5, 0.5, 0.5),
                          shader='edgeHilight')
        mesh.scale(.05, .05, .05)
        mesh.translate(self.origin['x'], self.origin['y'], up['z'])
        self.plot.addItem(mesh)

        stl_mesh = stl.mesh.Mesh.from_file(r'C:\Users\Administrator\Downloads\objective_2.stl')
        points = stl_mesh.points.reshape(-1, 3)
        faces = np.arange(points.shape[0]).reshape(-1, 3)

        mesh_data = gl.MeshData(vertexes=points, faces=faces)
        mesh = gl.GLMeshItem(meshdata=mesh_data, smooth=True, drawFaces=True, drawEdges=False,
                             color=(0.5, 0.5, 0.5, 0.5),
                             shader='edgeHilight')
        mesh.scale(.05, .05, .05)
        mesh.translate(self.origin['x'], self.origin['y'], up['z'])
        self.plot.addItem(mesh)

        stl_mesh = stl.mesh.Mesh.from_file(r'C:\Users\Administrator\Downloads\stage.stl')
        points = stl_mesh.points.reshape(-1, 3)
        faces = np.arange(points.shape[0]).reshape(-1, 3)

        self.stage_data = gl.MeshData(vertexes=points, faces=faces)
        self.stage = gl.GLMeshItem(meshdata=self.stage_data, smooth=True, drawFaces=True, drawEdges=False,
                                   color=(0.5, 0.5, 0.5, 0.5),
                                   shader='edgeHilight')
        self.stage.scale(.01, .01, .01)
        self.plot.addItem(self.stage)

        return self.plot
