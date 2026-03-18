import numpy as np
import pyqtgraph.opengl as gl


class TrajectoryRenderer:
    """Renders trajectory curves as GL line plots in the 3D viewport."""

    def __init__(self):
        self._items: dict[int, gl.GLLinePlotItem] = {}

    def update(self, track_id: int, points: np.ndarray, color: tuple, widget: gl.GLViewWidget):
        """Update or create the trajectory line for a given track.

        points: Nx3 array of (x, y, z) positions.
        """
        if points is None or len(points) < 2:
            self.remove(track_id, widget)
            return

        r, g, b = color
        gl_color = (r / 255.0, g / 255.0, b / 255.0, 0.5)

        if track_id in self._items:
            self._items[track_id].setData(pos=points, color=gl_color)
        else:
            item = gl.GLLinePlotItem(pos=points, color=gl_color, width=2.0, antialias=True)
            self._items[track_id] = item
            widget.addItem(item)

    def remove(self, track_id: int, widget: gl.GLViewWidget):
        if track_id in self._items:
            widget.removeItem(self._items[track_id])
            del self._items[track_id]

    def clear(self, widget: gl.GLViewWidget):
        for item in self._items.values():
            widget.removeItem(item)
        self._items.clear()
