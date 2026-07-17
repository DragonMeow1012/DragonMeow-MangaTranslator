import unittest

import numpy as np

from manga_translator.rendering import (
    _has_manual_foreground_color,
    _resolve_region_stroke_width,
    resolve_region_render_colors,
)
from manga_translator.utils.textblock import TextBlock
from server.edit import RegionEdit, _apply_edit, _region_json


def _region(fg=(255, 255, 255), bg=(0, 0, 0)):
    return TextBlock(
        lines=[[[0, 0], [100, 0], [100, 200], [0, 200]]],
        texts=['source'],
        translation='translation',
        fg_color=fg,
        bg_color=bg,
        default_stroke_width=0.2,
    )


class RenderColorOverrideTests(unittest.TestCase):
    def test_manual_black_text_on_white_background_keeps_stroke(self):
        for background, expected_bg in (
            ('#ffffff', (255, 255, 255)),
            ('#fefefe', (254, 254, 254)),
        ):
            with self.subTest(background=background):
                region = _region()
                region.font_color = '#000000'
                region.background_color = background
                region.adjust_bg_color = False

                # Reproduce the stale sampled state that made TextBlock.stroke_width return 0.
                region.fg_colors = np.array((255, 255, 255), dtype=np.uint8)
                region.bg_colors = np.array((255, 255, 255), dtype=np.uint8)

                fg, bg = resolve_region_render_colors(region, disable_font_border=False)

                self.assertTrue(_has_manual_foreground_color(region))
                self.assertEqual(fg, (0, 0, 0))
                self.assertEqual(bg, expected_bg)
                self.assertAlmostEqual(_resolve_region_stroke_width(region, fg, bg), 0.2)

    def test_manual_white_text_on_black_background_keeps_stroke(self):
        region = _region()
        region.font_color = '#ffffff'
        region.background_color = '#000000'
        region.adjust_bg_color = False

        fg, bg = resolve_region_render_colors(region, disable_font_border=False)

        self.assertEqual(fg, (255, 255, 255))
        self.assertEqual(bg, (0, 0, 0))
        self.assertAlmostEqual(_resolve_region_stroke_width(region, fg, bg), 0.2)

    def test_automatic_color_mode_remains_binary(self):
        cases = (
            ((0, 0, 0), ((0, 0, 0), (255, 255, 255))),
            ((255, 255, 255), ((255, 255, 255), (0, 0, 0))),
        )
        for sampled_fg, expected in cases:
            with self.subTest(sampled_fg=sampled_fg):
                region = _region(fg=sampled_fg, bg=sampled_fg)
                self.assertEqual(
                    resolve_region_render_colors(region, disable_font_border=False),
                    expected,
                )

    def test_disabled_background_disables_stroke(self):
        region = _region()
        region.font_color = '#000000'
        region.background_color = '#ffffff'
        region.adjust_bg_color = False

        fg, bg = resolve_region_render_colors(region, disable_font_border=True)

        self.assertEqual(fg, (0, 0, 0))
        self.assertIsNone(bg)
        self.assertEqual(_resolve_region_stroke_width(region, fg, bg), 0)

    def test_editor_state_reports_the_actual_automatic_pair(self):
        region = _region(fg=(255, 255, 255), bg=(255, 255, 255))

        data = _region_json(
            region,
            idx=0,
            was_skipped=False,
            default_background_enabled=True,
        )

        self.assertEqual(data['color'], '#ffffff')
        self.assertEqual(data['background_color'], '#000000')

    def test_editor_state_hides_internal_numeric_layout_marker(self):
        region = _region()
        region.translation = '\u7b2c<T>11</T>\u5e74'

        data = _region_json(
            region,
            idx=0,
            was_skipped=False,
            default_background_enabled=True,
        )

        self.assertEqual(data['translation'], '\u7b2c11\u5e74')

    def test_server_edit_uses_manual_pair_as_the_render_source(self):
        region = _region()
        edit = RegionEdit(
            id=0,
            color='#000000',
            background_enabled=True,
            background_color='#ffffff',
        )

        _apply_edit(region, edit)
        fg, bg = resolve_region_render_colors(region, disable_font_border=False)

        self.assertEqual(fg, (0, 0, 0))
        self.assertEqual(bg, (255, 255, 255))
        self.assertFalse(region.adjust_bg_color)
        self.assertFalse(region.disable_font_border)
        self.assertAlmostEqual(_resolve_region_stroke_width(region, fg, bg), 0.2)


if __name__ == '__main__':
    unittest.main()
