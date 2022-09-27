from qtpy.QtWidgets import QMessageBox, QLineEdit, QVBoxLayout, QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox, QScrollArea
from PyQt5.QtCore import Qt
from qtpy.QtWidgets import QPushButton, QMessageBox, QLineEdit, QCheckBox, QVBoxLayout, QDockWidget, QWidget, \
    QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QScrollArea


class Tab:

    def config_change(self, widget, attribute, instrument, kw, wl=None):

        """Changes instrument config when a changed value is entered
        :param widget: the widget which input changed
        :param attribute: the corresponding attribute that the widget represents
        :param instrument: instrument being used
        :param kw: the variable name in a nested dictionary
        :param wl: the wl which the kw applies to. Default is none if working with none wavelength related kw
        """

        value = float(widget.text())
        dictionary = getattr(self.cfg, attribute)
        path = self.pathFind(dictionary, wl)
        path = path + self.pathFind(dictionary, kw, path, True) if path is not None else self.pathFind(dictionary, kw)
        if self.pathGet(dictionary, path) - value != 0:
            self.pathSet(dictionary, path, value)

            try:
                if instrument.livestream_enabled.is_set():
                    instrument.stop_livestream()
                    instrument.start_livestream(wl)  # Need to make this more general
            except:
                instrument._setup_waveform_hardware(wl)

    def scan(self, dictionary: dict, attr: str, QDictionary: dict = None, WindowDictionary: dict = None, wl: str = None,
             input_type: str = QLineEdit, subdict: bool = False):

        """Scanning function to scan through dictionaries and create QWidgets for labels and inputs
        and save changes to config when done editing
        :param dictionary: dictionary which to scan through
        :param attr: attribute of config object
        :param QDictionary: dictionary which to place widgets
        :param WindowDictionary: dictionary which hols all the formatted widgets
        :param wl: specifies which wavelength parameter will map to
        :param input_type: type of QWidget that the input will be formatted to. Default is QLineEdit. Can support...
        :param subdict: if true, subdictionaries will also be scanned through. If false, those keys will be skipped
         """

        if QDictionary is None:
            QDictionary = {}

        if WindowDictionary is None:
            WindowDictionary = {}

        for keys in dictionary.keys():
            if type(dictionary[keys]) != dict:
                QDictionary[keys + '_label'], QDictionary[keys] = self.create_widget(dictionary[keys], keys, input_type)
                QDictionary[keys].editingFinished.connect((lambda widget=QDictionary[keys], kw=keys:
                                                           self.config_change(widget, attr, kw, wl)))

                WindowDictionary[keys] = self.create_layout(struct='H', label=QDictionary[keys + '_label'],
                                                            text=QDictionary[keys])
            elif subdict:
                self.scan(dictionary[keys], attr, QDictionary, WindowDictionary, wl=wl, subdict=True)
        return WindowDictionary

    def scroll_box(self, widget: QWidget):

        """Create a scroll box area to put large vertical widgets.
        :param widget: QWidget that holds multiple widgets in a set layout"""

        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setMinimumHeight(300)
        return scroll

    def adding_tabs(self, dock: dict, viewer):

        """Adds tabs to main dock in napari
        :param dock: dictionary of all the docks that you want to tabify in correct order
        :param viewer: napari viewer
        """
        keys = dock.keys()

        i = 1
        while i < len(keys):
            viewer.window._qt_window.tabifyDockWidget(dock[keys[0]], dock[keys[i]])

    def set_attribute(self, obj: object, var: str, widget: QWidget):

        """Sets an attribute value in the config object
        :param obj: object usually the config
        :param var: variable in the object to set
        :param widget: the widget that holds the new value to set to"""

        value_type = type(getattr(obj, var))
        value = value_type(widget.text())
        setattr(obj, var, value)

    def error_msg(self, title: str, msg: str):

        """Easy way to display error messages
        :param title: title of error message
        :param msg: message to display in the error message"""

        error = QMessageBox()
        error.setWindowTitle(title)
        error.setText(msg)
        error.exec()

    def pathFind(self, dictionary: dict, kw: str, path: list = None, preset_path: bool = False):

        """A recursive function to find the path to a keyword in a nested dictionary and returns a list of the path
        :param dictionary: dictionary which contains the keyword
        :param kw: keyword
        :param path: path to some subdictionary. Default is none
        :param preset_path: a boolean indicating if the  """

        if path is None:
            path = []

        if preset_path:
            dictionary = self.pathGet(dictionary, path)
            preset_path = False
            path = []

        for keys in dictionary.keys():
            if keys == kw:
                path.append(keys)
                return path

            elif type(dictionary[keys]) == dict and kw not in path:
                path.append(keys)
                self.pathFind(dictionary[keys], kw, path)
                if path[-1] != kw:
                    del path[-1]
                else:
                    return path

    def pathGet(self, dictionary, path):

        """Returns subdictionary based on a given path"""

        if path is None:
            return dictionary

        else:
            for k in path:
                dictionary = dictionary[k]
            return dictionary

    def pathSet(self, dictionary, path, setItem):

        """Set subdictionary value based on a path to the keyword"""

        key = path[-1]
        dictionary = self.pathGet(dictionary, path[:-1])
        dictionary[key] = setItem

    def create_layout(self, struct: str, **kwargs):

        """Creates a either a horizontal or vertical layout populated with widgets
        :param struct: specifies whether the layout will be horizontal or vertical
        :param kwargs: all widgets contained in layout"""

        widget = QWidget()
        if struct == 'H':
            layout = QHBoxLayout()
        else:
            layout = QVBoxLayout()
        for arg in kwargs.values():
            layout.addWidget(arg)
        widget.setLayout(layout)
        return widget

    def label_maker(self, string: str):

        """Removes underscores and capitalizes words in variable names"""
        label = string.split('_')
        label = [words.capitalize() for words in label]
        label = " ".join(label)
        return label

    def create_widget(self, value, attr, Qtype):

        """Create a label and input box for a variable
         :param value: value to preset input widget value
         :param attr: the variable name of the attribute referenced
         :param Qtype: type of QWidget """

        label = self.label_maker(attr)
        widget_label = QLabel(label)
        widget_input = Qtype()
        if isinstance(widget_input, QDoubleSpinBox):
            widget_input.setValue(value)
            widget_input.setSingleStep(.01)

        elif isinstance(widget_input, QLineEdit):
            widget_input.setText(str(value))

        return widget_label, widget_input
