import pyqtgraph.opengl as gl

from src.constants import GRID_SIZE, GRID_SPACING


class GridFloor:
    """Flat grid on the XZ plane to give spatial reference."""

    def __init__(self):
        self.grid_item = gl.GLGridItem()
        self.grid_item.setSize(GRID_SIZE, GRID_SIZE)
        self.grid_item.setSpacing(GRID_SPACING, GRID_SPACING)
        self.grid_item.setColor((60, 60, 60, 100))

    def add_to(self, widget: gl.GLViewWidget):
        widget.addItem(self.grid_item)
