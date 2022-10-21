from tab import Tab
from qtpy.QtWidgets import QLineEdit, QVBoxLayout,  QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox
from qtpy.QtGui import QIntValidator

def get_dict_attr(class_def, attr):
    # for obj in [obj] + obj.__class__.mro():
    for obj in [class_def] + class_def.__class__.mro():
        if attr in obj.__dict__:
            return obj.__dict__[attr]
    raise AttributeError

class AcquisitionParamsTab(Tab):

    def __init__(self, frame_grabber, column_pixels):
        self.frame_grabber = frame_grabber
        self.exposure_time = self.frame_grabber.exposure_time
        self.linerate = self.frame_grabber.line_interval
        self.column_pixels = column_pixels

        self.slit_width = {}
        self.exposure_time_cpx = {}


    def scan_config(self, config: object):

        """Scans config and finds property types with setter and getter attributes
        :param config: config object from the instrument class"""

        imaging_specs = {}      # dictionary to store attribute labels and input box
        imaging_specs_widgets = {}    # dictionary that holds layout of attribute labels/input pairs

        for attr in dir(config):
            value = getattr(config, attr)
            if isinstance(value,list):
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
        return imaging_specs_widgets

    def imaging_specs_container(self, widget_dict: dict):

        """Creates a container widget for all config attribute label/input widget pairs
        :param widget_dict: dictionary containing config attribute label/input widget pairs """

        return self.create_layout(struct='V', **widget_dict)

    def frame_grabber_exposure_time(self):

        """Setting CPX exposure time based on slit_width"""

        self.slit_width['label'], self.slit_width['widget'] = self.create_widget(self.exposure_time/self.linerate,
                                                                       QLineEdit, 'Slit Width')
        validator = QIntValidator(1, 999)
        self.slit_width['widget'].setValidator(validator)
        self.slit_width['widget'].editingFinished.connect(self.set_exposure_time)

        return self.create_layout(struct= 'H', **self.slit_width)


    def set_exposure_time(self):

        self.frame_grabber.exposure_time = int(self.slit_width['widget'].text())*self.frame_grabber.line_interval

    def frame_grabber_line_interval(self):

        """Setting CPX line interval based on exposure time and linerate"""

        self.exposure_time_cpx['label'], self.exposure_time_cpx['widget'] = self.create_widget(self.linerate*self.column_pixels,
                                                                                 QLineEdit, 'Exposure Time')
        self.exposure_time_cpx['widget'].editingFinished.connect(self.set_line_interval)
        return self.create_layout(struct='H', **self.exposure_time_cpx)

    def set_line_interval(self):

        self.frame_grabber.line_interval = self.frame_grabber.exposure_time/self.column_pixels




