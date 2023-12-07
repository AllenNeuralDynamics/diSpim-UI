import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget, QLineEdit, QComboBox, QMessageBox, QCheckBox
import pyqtgraph.opengl as gl
import numpy as np
import pyqtgraph as pg
from napari.qt.threading import thread_worker,create_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui
import qtpy.QtGui
import stl
from math import cos, sin, pi, tan, radians
import os
import blend_modes
import tifffile
import json
from nidaqmx.constants import TaskMode, FrequencyUnits, Level
from ispim.compute_waveforms import generate_waveforms

class TissueMap(WidgetBase):

    def __init__(self, instrument, viewer):

        self.instrument = instrument
        self.viewer = viewer
        self.cfg = self.instrument.cfg
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.pos = None
        self.plot = None
        self.gl_overview = []
        self.map_pos_alive = False
        self.overview_array = {}

        self.rotate = {}
        self.map = {}
        self.origin = {}
        self.overview = {}
        self.tiles = []
        self.scan_areas = []
        self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]
        self.tile_offset = self.remap_axis({'x': (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                            'y': (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                            'z': 0})
    def set_tab_widget(self, tab_widget: QTabWidget):

        """Set the tabwidget that contains main, wavelength, and tissue map tab"""

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)  # When tab bar is clicked see what tab its on

    def stage_positon_map(self, index):

        """Check if tab clicked is tissue map tab and start stage update when on tissue map tab
        :param index: clicked tab index. Tissue map is last tab"""

        sleep(1)
        last_index = len(self.tab_widget) - 1
        if index == last_index:  # Start stage update when on tissue map tab
            self.map_pos_worker = self._map_pos_worker()
            self.map_pos_alive = True
            self.map_pos_worker.finished.connect(self.map_pos_worker_finished)
            self.map_pos_worker.start()

        else:  # Quit updating tissue map if not on tissue map tab
            if self.map_pos_worker is not None:
                self.map_pos_worker.quit()

    def map_pos_worker_finished(self):
        """Sets map_pos_alive to false when worker finishes"""
        print('map_pos_worker_finished')
        self.map_pos_alive = False
        if self.instrument.stage_lock.locked():
            self.instrument.stage_lock.release()

    def overview_widget(self):

        """Widgets for setting up a quick scan"""

        self.overview['start'] = QPushButton('Start overview')
        self.overview['start'].pressed.connect(self.start_overview)
        self.overview['view'] = QComboBox()
        self.overview['view'].activated.connect(self.view_overview)

        return self.create_layout(struct='V', **self.overview)

    def start_overview(self):

        """Start overview function of instrument"""

        self.overview['start'].blockSignals(True)       # Block release signal so progress bar doesn't start

        if self.instrument.livestream_enabled.is_set():
            self.error_msg('Livestreaming',
                           'Please stop the livestream before starting overview.')
            self.overview['start'].blockSignals(False)
            return

        return_value = self.scan_summary()
        if return_value == QMessageBox.Cancel:
            self.overview['start'].blockSignals(False)
            return

        self.overview['start'].blockSignals(False)
        self.map_pos_worker.quit()  # Stopping tissue map update
        for i in range(0, len(self.tab_widget)): self.tab_widget.setTabEnabled(i, False)  # Disable tabs during scan

        self.overview_worker = self._overview_worker()
        self.overview_worker.finished.connect(lambda:self.overview_finish())    # Napari threads have finished signals
        self.overview_worker.start()
        sleep(2)
        self.viewer.layers.clear()     # Clear existing layers
        self.volumetric_image_worker = create_worker(self.instrument._acquisition_livestream_worker)
        self.volumetric_image_worker.yielded.connect(self.update_layer)
        self.volumetric_image_worker.start()

        self.overview['start'].released.emit()  # Start progress bar

    def overview_finish(self, overview_path = None):

        """Function to be executed at the end of the overview"""

        for i in range(0, len(self.tab_widget)): self.tab_widget.setTabEnabled(i, True)  # Enabled tabs

        self.set_tiling(2)  # Update tiles and gridsteps

        if overview_path != None:
            with tifffile.TiffFile(overview_path) as tif:
                tag = tif.pages[0].tags['ImageDescription']
                meta_dict = json.loads(tag.value)
                orientations = [overview_path[overview_path.find('overview_img_')-3:overview_path.find('overview_img_')-1]]
                self.overview_array[orientations[0]] = tif.asarray()
                self.xtiles = meta_dict['tile']['x']
                self.ytiles = meta_dict['tile']['y']
                z_volume = meta_dict['volume']['z']
                gui_coord = self.remap_axis({k: v * 0.0001 for k, v in meta_dict['position'].items()})
                wavelengths = [x for x in overview_path[:-5].split('_') if x.isdigit() and int(x) in self.cfg.laser_wavelengths]
                self.instrument.overview_imgs.append(overview_path)

                # only not x if yz and x scale doens't matter in that case
                x_px_len = self.overview_array[orientations[0]][0].shape[0] if orientations[0][0] == 'x' else 1
                # in xy and yz, y is always second dimension
                y_px_len = self.overview_array[orientations[0]][0].shape[1]
                z_px_len = self.overview_array[orientations[0]][0].shape[1] if orientations[0][0] == 'x' else \
                self.overview_array[orientations[0]][0].shape[0]

        else:
            z_volume = self.cfg.imaging_specs[f'volume_z_um']
            gui_coord = self.remap_axis({k: v * 0.0001 for k, v in self.map_pose.items()})
            wavelengths = self.cfg.imaging_wavelengths
            orientations = ['xy', 'xz', 'yz']
            x_px_len = self.overview_array['xz'][0].shape[0]
            y_px_len = self.overview_array['xy'][0].shape[1]
            z_px_len =  self.overview_array['xz'][0].shape[1]

            # Put nidaq in correct state for liveview.
            # Configuring the ni tasks during other threads is buggy so avoid doing if possible
            self.instrument._setup_waveform_hardware(self.cfg.imaging_wavelengths, live=True)

        scale_x = (((((self.xtiles - 1) * self.x_grid_step_um) + self.cfg.tile_size_x_um)) / x_px_len) / 1000
        scale_z = (((z_volume) / z_px_len)) / 1000
        scale_y = (((((self.ytiles - 1) * self.y_grid_step_um) + self.cfg.tile_size_y_um)) / y_px_len) / 1000
        overview_specs = {
            'xy':
                {'scale': (scale_y, scale_x, 1),
                 'rotation': (90, 0, 1, 0),
                 'k': 1
                 },
            'yz':
                {'scale': (scale_z, -scale_y, 1),
                 'rotation': (90, 1, 0, 0),
                 'k': 0
                 },
            'xz':
                {'scale': (scale_z, scale_x, 0),
                 'rotation': (0, 0, 0, 0),
                 'k': 3
                 }
        }

        colormap_array = {orientation:[None] * len(wavelengths) for orientation in orientations}
        final_RGBA = {}
        for orientation in orientations:
            # Auto contrasting image for tissue map
            j = 0
            for wl, array in zip(wavelengths, self.overview_array[orientation]):
                print(self.map_pos_alive)
                key = f'Overview {wl} {orientation}'
                self.viewer.add_image(np.rot90(array, overview_specs[orientation]['k']), name=key,
                                      scale=[round(overview_specs[orientation]['scale'][0] * 1000, 3),
                                             round(overview_specs[orientation]['scale'][1] * 1000, 3)])
                # scale so it won't be squished in viewer
                wl_color = 'purple'
                rgb = [x / 255 for x in qtpy.QtGui.QColor(wl_color).getRgb()]
                max = np.percentile(array, 90)
                min = np.percentile(array, 5)
                array.clip(min, max, out=array)
                array -= min
                array = np.floor_divide(array, (max - min) / 256, out=array, casting='unsafe')

                if orientation == 'xz':
                    overview_RGBA = \
                    pg.makeRGBA(np.flip(np.rot90(array, overview_specs[orientation]['k']), axis=1), levels=[0, 256])[0]
                elif orientation == 'xy':
                    overview_RGBA = pg.makeRGBA(np.flip(np.rot90(array, 1), axis=0), levels=[0, 256])[0]
                else:
                    overview_RGBA = pg.makeRGBA(np.flip(array, axis=0), levels=[0, 256])[0]

                for i in range(0, len(rgb)):
                    overview_RGBA[:, :, i] = overview_RGBA[:, :, i] * rgb[i]
                colormap_array[orientation][j] = overview_RGBA
                j += 1

            blended = colormap_array[orientation][0]
            for i in range(1, len(colormap_array[orientation])):
                alpha = 1 - (i / (i + 1))
                blended = blend_modes.darken_only(blended.astype('f8'), colormap_array[orientation][i].astype('f8'),
                                                  alpha)
            final_RGBA[orientation] = pg.makeRGBA(blended, levels=[0, 256])[0]
            final_RGBA[orientation][:, :, 3] = 200


            image = gl.GLImageItem(final_RGBA[orientation],
                                   glOptions='translucent')
            image.scale(overview_specs[orientation]['scale'][0],
                        overview_specs[orientation]['scale'][1],
                        overview_specs[orientation]['scale'][2], local=False)  # Scale Image
            image.rotate(*overview_specs[orientation]['rotation'])
            image.translate(gui_coord['x'] - self.tile_offset['x'],
                                           gui_coord['y'] - self.tile_offset['y'],
                                           gui_coord['z'] - self.tile_offset['z'])
            self.plot.addItem(image)
            self.gl_overview.append(image)
            self.overview['view'].addItem(str(len(self.gl_overview) - 1))
            self.overview['view'].setCurrentIndex(len(self.gl_overview)-1)

        self.map_pos_alive = True
        self.map_pos_worker = self._map_pos_worker()
        self.map_pos_worker.finished.connect(self.map_pos_worker_finished)
        self.map_pos_worker.start()  # Restart map update


    @thread_worker
    def _overview_worker(self):

        while self.map_pos_alive == True:   # Stalling til map pos worker quits
            sleep(.5)
        self.x_grid_step_um, self.y_grid_step_um = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                    self.cfg.tile_overlap_y_percent)


        self.overview_array = self.instrument.overview_scan()

        self.volumetric_image_worker.quit()

        # self.overview_array = {'xy': tifffile.imread(fr'C:\dispim_test\xy_overview_img_405_2023-10-27_14-57-52.tiff'),
        #                        'yz': tifffile.imread(fr'C:\dispim_test\yz_overview_img_405_2023-10-27_14-57-52.tiff'),
        #                        'xz': tifffile.imread(fr'C:\dispim_test\xz_overview_img_405_2023-10-27_14-57-52.tiff')}
        #print(self.overview_array)
    def view_overview(self, index):
        """Snap to specified overview for easier viewing"""
        transform = self.gl_overview[index].transform().data()
        self.gl_overview[index].transform()
        self.plot.opts['center'] = QtGui.QVector3D(
            transform[12] + ((self.gl_overview[index].data.shape[0] * transform[0]) / 2),
            transform[13] + (
                    (self.gl_overview[index].data.shape[1] * transform[5]) / 2),
            transform[14])
        self.plot.opts['elevation'] = 90 if transform[0] != 0 and transform[9] != -1 else 0
        self.plot.opts['azimuth'] = 90 if transform[0] != 0 and transform[9] != -1 else 0

        print(transform)
        transform_dim = 5 if transform[9] != -1 else 6
        shape_dim = 1 if transform[9] != -1 else 0
        print(self.plot.opts['elevation'], self.plot.opts['azimuth'], transform_dim, shape_dim)
        self.plot.opts['distance'] = (self.gl_overview[index].data.shape[shape_dim] * transform[transform_dim]) / (
            tan(0.5 * radians(self.plot.opts['fov'])))

    def scan_summary(self):

        x, y, z = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                           self.cfg.tile_overlap_y_percent,
                                                           .8 * 10,
                                                           self.cfg.volume_x_um,
                                                           self.cfg.volume_y_um,
                                                           self.cfg.volume_z_um)
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(f"Scan Summary\n"
                       f"Lasers: {self.cfg.imaging_wavelengths}\n"
                       f"Time: {round(self.instrument.acquisition_time(x, y, z), 3)} days\n"
                       f"X Tiles: {x}\n"
                       f"Y Tiles: {y}\n"
                       f"Z Tiles: {z}\n"
                       f"Saving as: {self.cfg.local_storage_dir}\overview_img_{'_'.join(map(str, self.cfg.imaging_wavelengths))}\n"
                       f"Press cancel to abort run")
        msgBox.setWindowTitle("Scan Summary")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def mark_graph(self):

        """Mark graph with pertinent landmarks"""

        self.map['color'] = QComboBox()
        self.map['color'].addItems(qtpy.QtGui.QColor.colorNames())  # Add all QtGui Colors to drop down box

        self.map['mark'] = QPushButton('Set Point')
        self.map['mark'].clicked.connect(self.set_point)  # Add point when button is presses

        self.map['label'] = QLineEdit()
        self.map['label'].returnPressed.connect(self.set_point)  # Add text when button is pressed

        self.checkbox = {}

        self.checkbox['tiling'] = QCheckBox('See Tiling')
        self.checkbox['tiling'].stateChanged.connect(self.set_tiling)  # Display tiling of scan when checked

        self.checkbox['objectives'] = QCheckBox('See Objectives')
        self.checkbox['objectives'].setChecked(True)
        self.checkbox['objectives'].stateChanged.connect(self.objective_display)

        self.checkbox['save_points'] = QPushButton('Save Points')
        self.checkbox['save_points'].clicked.connect(self.save_point)
        self.map['checkboxes'] = self.create_layout(struct='H', **self.checkbox)

        return self.create_layout(struct='V', **self.map)

    def save_point(self):
        """Save point plotted on the tissue map in txt file. To resee, drag file into map"""

        file = open(fr'{self.cfg.local_storage_dir}\tissue_map_points.txt', "w+")
        for item in self.plot.items:
            if type(item) == gl.GLScatterPlotItem:
                file.writelines(f'{list(item.pos)}\n')
        file.close()

    def load_points(self, file):
        """Load txt file of points into tissue map"""

        file = open(file, 'r')
        data = file.readlines()
        for line in data:
            coord = json.loads(line)
            point = gl.GLScatterPlotItem(pos=np.array(coord), size=.35, pxMode=False)
            self.plot.addItem(point)

    def objective_display(self, state):

        """ Toggle on or off weather objectives are visible or not"""

        if state == 2:
            self.objectives.setVisible(True)
            self.stage.setVisible(True)
        if state == 0:
            self.objectives.setVisible(False)

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
            for item in self.tiles:
                if item in self.plot.items:
                    self.plot.removeItem(item)
            self.tiles = []

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
        gui_coord = None
        stage_position = {}
        while True:
            try:
                with self.instrument.stage_lock:
                        stage_position = self.instrument.sample_pose.get_position()
                        sleep(.01)
                if self.map_pose != stage_position and self.instrument.scout_mode:
                    # if stage has moved and scout mode is on
                    self.start_stop_ni()
                self.map_pose = stage_position
                # Convert 1/10um to mm
                coord = {k: v * 0.0001 for k, v in self.map_pose.items()}  # if not self.instrument.simulated \
                #     else np.random.randint(-60000, 60000, 3)

                gui_coord = self.remap_axis(coord)  # Remap sample_pos to gui coords
                self.pos.setTransform(qtpy.QtGui.QMatrix4x4(cos(pi/4), 0, -sin(pi/4), gui_coord['x'] - self.tile_offset['x'],
                                                              0, 1, 0, gui_coord['y'] - self.tile_offset['y'],
                                                              sin(pi/4), 0, cos(pi/4), gui_coord['z']- self.tile_offset['z'],
                                                              0, 0, 0, 1))

                self.objectives.setTransform(qtpy.QtGui.QMatrix4x4(0, 0, 1, gui_coord['x'],
                                                              1, 0, 0, gui_coord['y'],
                                                              0, 1, 0, self.up['z'],
                                                              0, 0, 0, 1))
                self.stage.setTransform(qtpy.QtGui.QMatrix4x4(0, 0, 1, self.origin['x'],
                                                              1, 0, 0, self.origin['y'],
                                                              0, 1, 0, gui_coord['z'],
                                                              0, 0, 0, 1))
                yield

                if self.instrument.start_pos == None:

                    # Translate volume of scan to gui coordinate plane
                    scanning_volume = self.remap_axis({k: self.cfg.imaging_specs[f'volume_{k}_um'] * .001
                                                       for k in self.map_pose.keys()})

                    self.scan_vol.setSize(**scanning_volume)
                    self.scan_vol.setTransform(qtpy.QtGui.QMatrix4x4(1, 0, 0, gui_coord['x'] - self.tile_offset['x'],
                                                                     0, 1, 0, gui_coord['y'] - self.tile_offset['y'],
                                                                     0, 0, 1, gui_coord['z'] - self.tile_offset['z'],
                                                                     0, 0, 0, 1))
                    if self.checkbox['tiling'].isChecked():
                        if old_coord != gui_coord or self.tiles == [] or \
                                self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
                            self.draw_tiles(gui_coord)  # Draw tiles if checkbox is checked if something has changed
                    yield
                else:

                    # Remap start position and shift position of scan vol to center of camera fov and convert um to mm
                    start_pos = {k: v * 0.001 for k, v in self.instrument.start_pos.items()}  # start of scan coords
                    start_pos = self.remap_axis(
                        {'x': start_pos['x'] - self.tile_offset['x'],
                         'y': start_pos['y'] - self.tile_offset['y'],
                         'z': start_pos['z'] - self.tile_offset['z']})

                    if self.checkbox['tiling'].isChecked():
                        self.draw_tiles(start_pos)
                    self.draw_volume(start_pos, self.remap_axis({k: self.cfg.imaging_specs[f'volume_{k}_um'] * .001
                                                                 for k in self.map_pose.keys()}))
                    yield
            except Exception as e:
                print(e)
                if self.instrument.stage_lock.locked():
                    # release stage lock if try errors out before releasing
                    self.instrument.stage_lock.release()
                yield
            finally:
                old_coord = gui_coord
                yield  # Yield so thread can stop

    def draw_tiles(self, coord):

        """Draw tiles of proposed scan volume.
        :param coord: coordinates of bottom corner of volume in sample pose"""

        # Check if volume in config has changed
        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            self.set_tiling(2)  # Update grid steps and tile numbers
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for item in self.tiles:
            if item in self.plot.items:
                self.plot.removeItem(item)
        self.tiles.clear()
        for x in range(0, self.xtiles):
            for y in range(0, self.ytiles):
                tile_offset = self.remap_axis(
                    {'x': (x * self.x_grid_step_um * .001) - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                     'y': (y * self.y_grid_step_um * .001) - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                     'z': 0})
                tile_pos = {
                    'x': tile_offset['x'] + coord['x'],
                    'y': tile_offset['y'] + coord['y'],
                    'z': tile_offset['z'] + coord['z']
                }
                num_pos = [tile_pos['x'],
                           tile_pos['y'] + (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                           tile_pos['z'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um']))]

                tile_volume = self.remap_axis({'x': self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                               'y': self.cfg.tile_specs['y_field_of_view_um'] * .001,
                                               'z': self.ztiles * self.cfg.z_step_size_um * .001})
                self.tiles.append(self.draw_volume(tile_pos, tile_volume))
                self.tiles[-1].setColor(qtpy.QtGui.QColor('cornflowerblue'))
                self.plot.removeItem(self.objectives)
                self.plot.addItem(self.tiles[-1])
                self.plot.addItem(self.objectives)  # remove and add objectives to see tiles through objective
                self.tiles.append(gl.GLTextItem(pos=num_pos, text=str((self.xtiles*y)+x), font=qtpy.QtGui.QFont('Helvetica', 15)))
                self.plot.addItem(self.tiles[-1])       # Can't draw text while moving graph

    def draw_volume(self, coord: dict, size: dict):

        """draw and translate boxes in map. Expecting gui coordinate system"""

        box = gl.GLBoxItem()  # Representing scan volume
        box.translate(coord['x'], coord['y'], coord['z'])
        box.setSize(**size)
        return box

    def draw_configured_scans(self, scans: dict):
        """Draw configured scans in tissue map"""

        for scan in self.scan_areas:
            if scan in self.plot.items:
                self.plot.removeItem(scan)
        self.scan_areas = []
        for scan in scans.values():  # Scans is nested dictionaries outer dictionary key is the order of the scan
            # Remap start position and shift position of scan vol to center of camera fov and convert um to mm
            start_pos = self.remap_axis({k: v * 0.001 for k, v in scan['start_pos_um'].items()})  # start of scan coords
            start_pos = {'x': start_pos['x'] - self.tile_offset['x'],
                         'y': start_pos['y'] - self.tile_offset['y'],
                         'z': start_pos['z'] - self.tile_offset['z']}
            area = self.draw_volume(start_pos, self.remap_axis({'x': scan['volume_x_um'] * .001,
                                                         'y': scan['volume_y_um'] * .001,
                                                         'z': scan['volume_z_um'] * .001}))
            area.setColor(qtpy.QtGui.QColor('lime'))
            self.plot.addItem(area)
            self.scan_areas.append(area)


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

        remap = {'x': 'z', 'y': 'x', 'z': '-y'}     # TODO: Maybe make this config based
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
        self.map_pose = self.instrument.sample_pose.get_position()
        coord = {k: v * 0.0001 for k, v in self.map_pose.items()}
        gui_coord = self.remap_axis(coord)
        self.plot.opts['center'] = QtGui.QVector3D(gui_coord['x'], gui_coord['y'], gui_coord['z'])  #Centering map on stage position


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
        self.up = up
        self.axes_len = axes_len

        # Representing scan volume
        self.scan_vol = gl.GLBoxItem()
        self.scan_vol.setColor(qtpy.QtGui.QColor('gold'))
        self.scan_vol.translate(self.origin['x'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                self.origin['y'] - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                up['z'])
        scanning_volume = self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 0.001,
                                           'y': self.cfg.imaging_specs[f'volume_y_um'] * 0.001,
                                           'z': self.cfg.imaging_specs[f'volume_z_um'] * 0.001})

        self.scan_vol.setSize(**scanning_volume)
        self.plot.addItem(self.scan_vol)

        self.pos = gl.GLBoxItem()
        self.pos.setSize(**self.remap_axis({'x': 0.001 * self.cfg.tile_specs['x_field_of_view_um'],
                                            'y': 0.001 * self.cfg.tile_specs['y_field_of_view_um'],
                                            'z':0}))
        self.pos.setColor(qtpy.QtGui.QColor('red'))
        self.plot.addItem(self.pos)

        try:
            objectives = stl.mesh.Mesh.from_file(rf'C:\Users\{os.getlogin()}\Documents\dispim_files\di-spim-tissue-map.stl')
            points = objectives.points.reshape(-1, 3)
            faces = np.arange(points.shape[0]).reshape(-1, 3)

            objectives = gl.MeshData(vertexes=points, faces=faces)
            self.objectives = gl.GLMeshItem(meshdata=objectives, smooth=True, drawFaces=True, drawEdges=False, color=(0.5, 0.5, 0.5, 0.5),
                              shader='edgeHilight', glOptions='translucent')


            stage = stl.mesh.Mesh.from_file(rf'C:\Users\{os.getlogin()}\Documents\dispim_files\di-spim-holder.stl')
            points = stage.points.reshape(-1, 3)
            faces = np.arange(points.shape[0]).reshape(-1, 3)

            stage = gl.MeshData(vertexes=points, faces=faces)
            self.stage = gl.GLMeshItem(meshdata=stage, smooth=True, drawFaces=True, drawEdges=False, color=(0.5, 0.5, 0.5, 0.5),
                                       shader='edgeHilight',glOptions='translucent')
            self.plot.addItem(self.objectives)
            self.plot.addItem(self.stage)

        except FileNotFoundError:
            # Create self.objectives and self.stage objects but don't add them to graph
            self.objectives = gl.GLBoxItem()
            self.stage = gl.GLBoxItem()

        # Reassigning drag and drop function to be able to drop in overviews
        self.plot.setAcceptDrops(True)
        self.plot.dragEnterEvent = self.dragEnterEvent
        self.plot.dragMoveEvent = self.dragMoveEvent
        self.plot.dropEvent = self.dropEvent

        return self.plot

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):

        file_path = event.mimeData().urls()[0].toLocalFile()
        if file_path[-3:] == 'txt':
            self.load_points(file_path)

        else:
            try:

                self.map_pos_worker.finished.connect(lambda path = file_path: self.overview_finish(path))
                self.map_pos_worker.quit()
            except OSError:
                pass
            except:
                self.error_msg('Unusable Image', "Image dragged does not have the correct metadata. Tiff needs to have "
                                                 "position, volume, and tile data for x, y, z")
                self.map_pos_worker = self._map_pos_worker()
                self.map_pos_alive = True
                self.map_pos_worker.finished.connect(self.map_pos_worker_finished)
                self.map_pos_worker.start()  # Restart map update


        event.accept()