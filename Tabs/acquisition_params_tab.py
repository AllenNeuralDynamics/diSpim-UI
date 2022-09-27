from tab import Tab
from qtpy.QtWidgets import QLineEdit, QVBoxLayout,  QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox


def get_dict_attr(class_def, attr):
    # for obj in [obj] + obj.__class__.mro():
    for obj in [class_def] + class_def.__class__.mro():
        if attr in obj.__dict__:
            return obj.__dict__[attr]
    raise AttributeError

class AcquisitionParamsTab(Tab):

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
                    #Creates the attribute label and input box
                    imaging_specs[attr, '_label'], imaging_specs[attr] = \
                        self.create_widget(getattr(config, attr), attr,QLineEdit)
                    #Connects input box to changing config object when attribute value is changed
                    imaging_specs[attr].editingFinished.connect(lambda obj=config, var=attr, widget=imaging_specs[attr]:
                                                                self.set_attribute(obj, var, widget))
                    #formats label and input box vertically allined. Returns Qwidget
                    imaging_specs_widgets[attr] = self.create_layout(struct='H', label=imaging_specs[attr, '_label'],
                                                            text=imaging_specs[attr])
        return imaging_specs_widgets

    def imaging_specs_container(self, widget_dict: dict):

        """Creates a container widget for all config attribute label/input widget pairs
        :param widget_dict: dictionary containing config attribute label/input widget pairs """

        return self.create_layout(struct='V', **widget_dict)





