from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QLineEdit, QVBoxLayout, QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox, QDial, QToolButton
from qtpy.QtGui import QIntValidator
from tigerasi.device_codes import JoystickInput
import qtpy.QtCore as QtCore
from ispim.ispim_config import IspimConfig

def get_dict_attr(class_def, attr):
    # for obj in [obj] + obj.__class__.mro():
    for obj in [class_def] + class_def.__class__.mro():
        if attr in obj.__dict__:
            return obj.__dict__[attr]
    raise AttributeError

class InstrumentParameters(WidgetBase):

    def __init__(self, frame_grabber, column_pixels, simulated, instrument, config):

        self.frame_grabber = frame_grabber
        self.column_pixels = column_pixels
        self.simulated = simulated
        self.instrument = instrument
        self.cfg = config
        self.slit_width = {}
        self.exposure_time = {}
        self.imaging_specs = {}

    def scan_config(self, config: object, x_game_mode: bool = True):

        """Scans config and finds property types with setter and getter attributes
        :param config: config object from the instrument class"""

        self.imaging_specs = {}  # dictionary to store attribute labels and input box
        imaging_specs_widgets = {}  # dictionary that holds layout of attribute labels/input pairs

        if not x_game_mode:
            weenie_hut_jr_param = ['ext_storage_dir', 'immersion_medium', 'local_storage_dir',
                                  'subject_id', 'tile_prefix', 'volume_x_um', 'volume_y_um',
                                  'volume_z_um']
            directory = [i for i in dir(config) if i in weenie_hut_jr_param]
        else:
            cpx_attributes = ['exposure_time_s', 'slit_width_pix', 'line_time_us', 'scan_direction']
            directory = [i for i in dir(config) if i not in cpx_attributes]

        for attr in directory:
            value = getattr(config, attr)
            if isinstance(value, list):
                continue
            elif isinstance(getattr(type(config), attr, None), property):
                prop_obj = get_dict_attr(config, attr)

                if prop_obj.fset is not None and prop_obj.fget is not None:
                    self.imaging_specs[attr, '_label'], self.imaging_specs[attr] = \
                        self.create_widget(getattr(config, attr), QLineEdit, label=attr)

                    self.imaging_specs[attr].editingFinished.connect \
                        (lambda obj=config, var=attr, widget=self.imaging_specs[attr]:
                         self.set_attribute(obj, var, widget))

                    self.imaging_specs[attr].setToolTip(prop_obj.__doc__)

                    imaging_specs_widgets[attr] = self.create_layout(struct='H',
                                                                     label=self.imaging_specs[attr, '_label'],
                                                                     text=self.imaging_specs[attr])
        return self.create_layout(struct='V', **imaging_specs_widgets)

    def slit_width_widget(self):

        """Setting CPX exposure time based on slit_width"""

        value = self.cfg.slit_width_pix
        self.slit_width['label'], self.slit_width['widget'] = \
            self.create_widget(int(value), QLineEdit, 'Slit Width [px]:')
        validator = QIntValidator()
        self.slit_width['widget'].setValidator(validator)
        self.slit_width['widget'].editingFinished.connect(self.set_cpx_exposure_time)

        return self.create_layout(struct='H', **self.slit_width)

    def set_cpx_exposure_time(self):

        """Setting CPX exposure time based on slit_width and cpx line rate"""

        # TODO: This is assuming that the line_interval is set the same in
        # both cameras. Should have some fail safe in case not?
        set_sw = self.cfg.slit_width_pix
        new_sw = int(self.slit_width['widget'].text())
        if set_sw != new_sw:
            cpx_line_interval = self.frame_grabber.get_line_interval()
            self.frame_grabber.set_exposure_time(new_sw * cpx_line_interval[0],
                                                 live=self.instrument.livestream_enabled.is_set())
            self.cfg.slit_width_pix = new_sw

            if self.instrument.livestream_enabled.is_set():
                self.instrument._setup_waveform_hardware(
                    self.instrument.active_lasers,
                    live=True)

    def exposure_time_widget(self):

        """Setting CPX line interval based on gui exposure time and column pix"""

        value = self.cfg.exposure_time
        # TODO: make sure the pixels are right
        self.exposure_time['label'], self.exposure_time['widget'] = \
            self.create_widget(value, QLineEdit, 'Exposure Time [s]:')
        self.exposure_time['widget'].editingFinished.connect(self.set_cpx_line_interval)

        return self.create_layout(struct='H', **self.exposure_time)

    def set_cpx_line_interval(self):

        """Setting CPX line interval based on gui exposure time and column pix.
        Setting exposure time and line time in config object"""

        set_et = self.cfg.exposure_time
        new_et = float(self.exposure_time['widget'].text())
        if set_et != new_et:
            line_interval = (new_et * 1000000) / self.column_pixels
            self.frame_grabber.set_line_interval(line_interval, live=self.instrument.livestream_enabled.is_set())
            self.frame_grabber.set_exposure_time(int(self.slit_width['widget'].text()) *
                                                 line_interval,
                                                 live=self.instrument.livestream_enabled.is_set())
            self.cfg.line_time_us = line_interval
            self.cfg.exposure_time_s = new_et

            if self.instrument.livestream_enabled.is_set():
                self.instrument._setup_waveform_hardware(
                    self.instrument.active_lasers,
                    live=True)

    def shutter_direction_widgets(self):

        """"Setting shutter direction for each camera"""
        self.scan_widgets = {}
        self.scan_direction = {}
        directions = ['FORWARD', 'BACKWARD']

        value = self.cfg.camera_specs['scan_direction']
        index = directions.index(value)
        self.scan_widgets['label'], self.scan_widgets['widget'] = \
            self.create_widget(None, QComboBox, 'scan_direction:')
        self.scan_widgets['widget'].addItems(directions)
        self.scan_widgets['widget'].setCurrentIndex(index)
        self.scan_widgets['widget'].currentIndexChanged.connect(lambda index=None, camera=0:
                                                                            self.set_shutter_direction(index,
                                                                                                       camera))
        self.scan_direction['widget'] = self.create_layout(struct='H',
                                                            label=self.scan_widgets['label'],
                                                            widget=
                                                            self.scan_widgets['widget'])

        return self.create_layout(struct='V', **self.scan_direction)

    def set_shutter_direction(self, index, stream_id):

        direction = self.scan_widgets[f'widget'].currentText()
        self.frame_grabber.set_scan_direction(stream_id, direction, self.instrument.livestream_enabled.is_set())
        self.cfg.scan_direction = direction

        if self.instrument.livestream_enabled.is_set():
            self.instrument._setup_waveform_hardware(
                self.instrument.active_lasers,
                live=True)

    def filetype_widget(self):

        self.filetype_widgets = {}
        filetypes = ['Tiff', 'Zarr', 'ZarrBlosc1ZstdByteShuffle']

        value = self.cfg.imaging_specs['filetype']
        index = filetypes.index(value)
        self.filetype_widgets['label'], self.filetype_widgets['widget'] = \
            self.create_widget(None, QComboBox, 'filtype:')
        self.filetype_widgets['widget'].addItems(filetypes)
        self.filetype_widgets['widget'].setCurrentIndex(index)
        self.filetype_widgets['widget'].currentIndexChanged.connect(self.set_filetype)

        return self.create_layout(struct='H', **self.filetype_widgets)

    def set_filetype(self, index):

        filetype = self.filetype_widgets[f'widget'].currentText()
        self.cfg.imaging_specs['filetype'] = filetype


    def joystick_remap_tab(self):

        """Tab to remap joystick"""


        tiger_axes = [k for k,v in self.instrument.tigerbox.get_joystick_axis_mapping().items() if v == JoystickInput.NONE]
        tiger_axes.append('NONE')

        joystick_mapping = self.instrument.tigerbox.get_joystick_axis_mapping()
        self.joystick_axes = {'JOYSTICK_X':'', 'JOYSTICK_Y':'', 'Z_WHEEL':'', 'F_WHEEL':''}

        self.axis_combobox = {}
        combobox_layout = {}
        for axis in self.joystick_axes.keys():
            self.axis_combobox[axis] = QComboBox()
            self.axis_combobox[axis].addItems(tiger_axes)
            if JoystickInput[axis] in joystick_mapping.values():
                current_text = list(joystick_mapping.keys())[list(joystick_mapping.values()).index(JoystickInput[axis])]
                self.axis_combobox[axis].addItem(current_text)
            else:
                current_text = 'NONE'
            self.joystick_axes[axis] = current_text
            self.axis_combobox[axis].setCurrentText(current_text)
            label = QLabel(f'{axis}:')
            combobox_layout[axis] = self.create_layout(struct='H',
                                                       label=label,
                                                       combobox=self.axis_combobox[axis])
            self.axis_combobox[axis].currentTextChanged.connect(lambda index = None,
                                                                           axis = axis
                                                                    : self.change_joystick_mapping(index, axis))

        left = QToolButton()
        left.setArrowType(QtCore.Qt.ArrowType.LeftArrow)
        right = QToolButton()
        right.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        right_left = self.create_layout(struct='H',
                                        left=left,
                                        right=right,
                                        box=combobox_layout['JOYSTICK_X'])

        up = QToolButton()
        up.setArrowType(QtCore.Qt.ArrowType.UpArrow)
        down = QToolButton()
        down.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        up_down = self.create_layout(struct='H', up=up,
                                     down=down,
                                     box=combobox_layout['JOYSTICK_Y'])

        left_dial = self.create_layout(struct='H', dial=QDial(),
                                       box=combobox_layout['Z_WHEEL'])
        right_dial = self.create_layout(struct='H', dial=QDial(),
                                        box=combobox_layout['F_WHEEL'])

        all = self.create_layout(struct='V', ud=up_down, rl=right_left, ldial=left_dial, rdial=right_dial)
        all.children()[0].addStretch()
        all.children()[0].addSpacing(0)
        all.children()[0].setAlignment(QtCore.Qt.AlignLeft)
        return all

    def change_joystick_mapping(self, index, joystick_axis):

        stage_ax = self.axis_combobox[joystick_axis].currentText()
        if stage_ax == 'NONE':
            # Unmap previous coordinate and add coordinate to all comboboxes
            self.instrument.tigerbox.bind_axis_to_joystick_input(**{self.joystick_axes[joystick_axis]: JoystickInput.NONE})
            for joystick, box in self.axis_combobox.items():
                if joystick == joystick_axis:
                    continue # don't add duplicate of axis
                box.blockSignals(True)
                box.addItem(self.joystick_axes[joystick_axis])
                box.blockSignals(False)
        elif self.joystick_axes[joystick_axis] == 'NONE':
            # Map new stage axis to joystick
            self.instrument.tigerbox.bind_axis_to_joystick_input(
                **{stage_ax: JoystickInput[joystick_axis]})
            for joystick, box in self.axis_combobox.items():
                if joystick == joystick_axis:
                    continue  # don't add duplicate of axis
                box.blockSignals(True)
                box.removeItem(box.findText(stage_ax))
                box.blockSignals(False)
        else:       # Neither stageax or joystick is none
            #Set previous stage axis to map to none and set new axis to joystick axis
            self.instrument.tigerbox.bind_axis_to_joystick_input(**{self.joystick_axes[joystick_axis]:JoystickInput.NONE,
                                                                        stage_ax:JoystickInput[joystick_axis]})
            for joystick, box in self.axis_combobox.items():
                if joystick == joystick_axis:
                    continue  # don't add duplicate of axis
                box.blockSignals(True)
                box.removeItem(box.findText(stage_ax))
                box.addItem(self.joystick_axes[joystick_axis])
                box.blockSignals(False)

        # Update joystick axis
        self.joystick_axes[joystick_axis] = stage_ax

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):

        file_path = event.mimeData().urls()[0].toLocalFile()
        # Load new config
        new_cfg = IspimConfig(file_path)
        for k, v in new_cfg.__dict__.items():
            if k == 'path':
                self.cfg.__dict__[k] = v





