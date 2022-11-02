from tab import Tab
from qtpy.QtWidgets import QLineEdit, QVBoxLayout, QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox
from qtpy.QtGui import QIntValidator


def get_dict_attr(class_def, attr):
    # for obj in [obj] + obj.__class__.mro():
    for obj in [class_def] + class_def.__class__.mro():
        if attr in obj.__dict__:
            return obj.__dict__[attr]
    raise AttributeError


class AcquisitionParamsTab(Tab):

    def __init__(self, frame_grabber, column_pixels, simulated, instrument, config):

        self.frame_grabber = frame_grabber
        self.column_pixels = column_pixels
        self.simulated = simulated
        self.instrument = instrument
        self.cfg = config
        self.slit_width = {}
        self.exposure_time = {}

        self.camera_id = ['Right', 'Left']

    def scan_config(self, config: object):

        """Scans config and finds property types with setter and getter attributes
        :param config: config object from the instrument class"""
        #TODO: change config to self.cfg
        imaging_specs = {}  # dictionary to store attribute labels and input box
        imaging_specs_widgets = {}  # dictionary that holds layout of attribute labels/input pairs

        for attr in dir(config):
            value = getattr(config, attr)

            if isinstance(value, list):
                continue
            elif isinstance(getattr(type(config), attr, None), property):
                prop_obj = get_dict_attr(config, attr)

                if prop_obj.fset is not None and prop_obj.fget is not None:
                    imaging_specs[attr, '_label'], imaging_specs[attr] = \
                        self.create_widget(getattr(config, attr), QLineEdit, label=attr)

                    imaging_specs[attr].editingFinished.connect(lambda obj=config, var=attr, widget=imaging_specs[attr]:
                                                                self.set_attribute(obj, var, widget))

                    imaging_specs[attr].setToolTip(prop_obj.__doc__)

                    imaging_specs_widgets[attr] = self.create_layout(struct='H', label=imaging_specs[attr, '_label'],
                                                                     text=imaging_specs[attr])
        return self.create_layout(struct='V', **imaging_specs_widgets)

    def slit_width_widget(self):

        """Setting CPX exposure time based on slit_width"""

        value = self.cfg.slit_width
        self.slit_width['label'], self.slit_width['widget'] = \
            self.create_widget(int(value), QLineEdit, 'Slit Width:')
        validator = QIntValidator()
        self.slit_width['widget'].setValidator(validator)
        self.slit_width['widget'].editingFinished.connect(self.set_cpx_exposure_time)

        return self.create_layout(struct='H', **self.slit_width)

    def set_cpx_exposure_time(self):

        """Setting CPX exposure time based on slit_width and cpx line rate"""

        #TODO: This is assuming that the line_interval is set the same in
        # both cameras. Should have some fail safe in case not?
        cpx_line_interval = self.frame_grabber.get_line_interval()
        self.frame_grabber.set_exposure_time(int(self.slit_width['widget'].text())*
                                             cpx_line_interval[0],
                                             live = self.instrument.live_status )

        self.cfg.slit_width = int(self.slit_width['widget'].text())

        if self.instrument.live_status:
            self.instrument._setup_waveform_hardware(
                self.instrument.active_laser,
                live=True)

    def exposure_time_widget(self):

        """Setting CPX line interval based on gui exposure time and column pix"""


        value = self.cfg.exposure_time
        #TODO: make sure the pixels are right
        self.exposure_time['label'], self.exposure_time['widget'] = \
            self.create_widget(value, QLineEdit, 'Exposure Time (s):')
        self.exposure_time['widget'].editingFinished.connect(self.set_cpx_line_interval)

        return self.create_layout(struct='H', **self.exposure_time)

    def set_cpx_line_interval(self):

        """Setting CPX line interval based on gui exposure time and column pix"""

        self.frame_grabber.set_line_interval(
            (float(self.exposure_time['widget'].text())*1000000) /
            self.column_pixels,
            live = self.instrument.live_status)

        self.cfg.exposure_time = float(self.exposure_time['widget'].text())

        if self.instrument.live_status:
            self.instrument._setup_waveform_hardware(
                self.instrument.active_laser,
                live=True)

