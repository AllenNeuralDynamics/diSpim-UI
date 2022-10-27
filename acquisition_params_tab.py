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

    def __init__(self, frame_grabber, column_pixels, simulated):

        self.frame_grabber = frame_grabber
        self.column_pixels = column_pixels
        self.simulated = simulated

        self.slit_width = {}
        self.exposure_time_cpx = {}

        self.camera_id = ['Right', 'Left']

    def scan_config(self, config: object):

        """Scans config and finds property types with setter and getter attributes
        :param config: config object from the instrument class"""

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

    def frame_grabber_exposure_time(self):

        """Setting CPX exposure time based on slit_width"""

        slit_widths = {}

        for stream_id in range(0, 2):

            value = self.frame_grabber.get_exposure_time(stream_id)/self.frame_grabber.get_line_interval(stream_id) \
                if not self.simulated else 1
            self.slit_width[f'{stream_id}label'], self.slit_width[f'{stream_id}widget'] = \
                self.create_widget(value, QLineEdit, f'Slit Width {self.camera_id[stream_id]}:')
            validator = QIntValidator(1, 999)
            self.slit_width[f'{stream_id}widget'].setValidator(validator)
            self.slit_width[f'{stream_id}widget'].editingFinished.connect(lambda stream=stream_id:
                                                                          self.set_exposure_time(stream))
            slit_widths[str(stream_id)] = self.create_layout(struct='H', label=self.slit_width[f'{stream_id}label'],
                                                             text=self.slit_width[f'{stream_id}widget'])

        return self.create_layout(struct='V', **slit_widths)

    def set_exposure_time(self, stream_id):

        self.frame_grabber.set_exposure_time(stream_id, int(self.slit_width[f'{stream_id}widget'].text())*
                                             self.frame_grabber.get_line_interval(stream_id))

    def frame_grabber_line_interval(self):

        """Setting CPX line interval based on exposure time and linerate"""

        exposure_times = {}

        for stream_id in range(0, 2):
            value = self.frame_grabber.get_line_interval(stream_id) * self.column_pixels if not self.simulated else 1 #TODO: make sure the pixels are right
            self.exposure_time_cpx[f'{stream_id}label'], self.exposure_time_cpx[f'{stream_id}widget'] = \
                self.create_widget(value, QLineEdit, f'Exposure Time {self.camera_id[stream_id]}:')
            self.exposure_time_cpx[f'{stream_id}widget'].editingFinished.connect(lambda stream=stream_id:
                                                                                 self.set_line_interval(stream))
            exposure_times[str(stream_id)] = self.create_layout(struct='H', label=self.exposure_time_cpx[f'{stream_id}label'],
                                                             text=self.exposure_time_cpx[f'{stream_id}widget'])
        return self.create_layout(struct='V', **exposure_times)

    def set_line_interval(self, stream_id):

        self.frame_grabber.set_line_interval(stream_id,int(self.exposure_time_cpx[f'{stream_id}widget'].text()) / self.column_pixels)
