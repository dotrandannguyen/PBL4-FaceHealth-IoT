"""Hardware-free tests for the responsive AI1 standalone window layout."""

import inspect
import unittest
from types import SimpleNamespace

import numpy as np

from ai1_gui_core.gui import AI1Gui


class FakeWidget:
    def __init__(self, master=None):
        self.master = master
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class FakeCanvas(FakeWidget):
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height
        self.scroll = None

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def yview_scroll(self, amount, unit):
        self.scroll = (amount, unit)


class GuiLayoutTests(unittest.TestCase):
    def test_control_layout_adapts_to_three_two_and_one_columns(self):
        self.assertEqual(AI1Gui._layout_columns_for_width(1240), 3)
        self.assertEqual(AI1Gui._layout_columns_for_width(900), 2)
        self.assertEqual(AI1Gui._layout_columns_for_width(819), 1)

    def test_preview_follows_source_aspect_without_stretching(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.content_canvas = FakeCanvas(1000, 700)
        gui.current_packet = SimpleNamespace(
            frame=np.zeros((480, 640, 3), dtype=np.uint8)
        )
        gui.preview_host = FakeWidget()
        gui.preview_hint_label = FakeWidget()
        gui.result_detail_label = FakeWidget()
        gui.enrollment_info_labels = []

        gui._resize_preview()
        width, height = gui._preview_size
        self.assertAlmostEqual(width / height, 4 / 3, places=2)
        self.assertLessEqual(height, 560)

        gui.current_packet.frame = np.zeros((360, 640, 3), dtype=np.uint8)
        gui._resize_preview()
        width, height = gui._preview_size
        self.assertAlmostEqual(width / height, 16 / 9, places=2)
        self.assertLessEqual(width, 958)

    def test_mousewheel_scrolls_only_for_widgets_inside_page_content(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.scroll_content = FakeWidget()
        gui.content_canvas = FakeCanvas(800, 600)
        child = FakeWidget(master=gui.scroll_content)

        handled = gui._on_content_mousewheel(SimpleNamespace(widget=child, delta=-120, num=None))
        self.assertEqual(handled, "break")
        self.assertEqual(gui.content_canvas.scroll, (1, "units"))

        other = FakeWidget()
        self.assertIsNone(gui._on_content_mousewheel(
            SimpleNamespace(widget=other, delta=-120, num=None)
        ))

    def test_layout_keeps_existing_controls_and_callbacks_wired(self):
        source = inspect.getsource(AI1Gui._build_ui)
        self.assertIn("self.content_canvas", source)
        self.assertIn("self.camera_stage", source)
        self.assertNotIn("side = tk.Frame(body", source)
        for callback in (
            "self._change_camera", "self._begin_registration", "self._recognize",
            "self._refresh", "self._delete_selected", "self._select_employee",
            "self._retake_pose", "self._cancel_enrollment", "self._retry_save",
            "self._on_close",
        ):
            with self.subTest(callback=callback):
                self.assertIn(callback, source)


if __name__ == "__main__":
    unittest.main()
