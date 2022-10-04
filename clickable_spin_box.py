from PyQt5 import QtCore, QtWidgets

class ClickableSpinBox(QtWidgets.QSpinBox):
    clicked = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        last_value = self.value()
        #super(ClickableSpinBox, self).mousePressEvent(event)
        self.clicked.emit()
