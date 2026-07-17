import unittest

from manga_translator.rendering.text_render import (
    _build_vertical_layout,
    _should_rotate_inline_block,
    auto_add_horizontal_tags,
)


class VerticalNumericRenderingTests(unittest.TestCase):
    def test_consecutive_numbers_are_automatically_grouped_horizontally(self):
        self.assertEqual(
            auto_add_horizontal_tags('\u7b2c12\u8a71'),
            '\u7b2c<T>12</T>\u8a71',
        )
        self.assertEqual(
            auto_add_horizontal_tags('\u7b2c\uff11\uff12\u8a71'),
            '\u7b2c<T>\uff11\uff12</T>\u8a71',
        )

    def test_single_number_keeps_a_single_vertical_slot(self):
        self.assertEqual(
            auto_add_horizontal_tags('\u7b2c1\u8a71'),
            '\u7b2c1\u8a71',
        )

    def test_explicit_numeric_horizontal_tags_are_preserved(self):
        self.assertEqual(
            auto_add_horizontal_tags('\u7b2c<H>12</H>\u8a71'),
            '\u7b2c<H>12</H>\u8a71',
        )
        self.assertEqual(
            auto_add_horizontal_tags('\u7b2c<h>\uff11\uff12</h>\u8a71'),
            '\u7b2c<h>\uff11\uff12</h>\u8a71',
        )
        self.assertEqual(
            auto_add_horizontal_tags('<H>1</H><H>1</H>'),
            '<H>1</H><H>1</H>',
        )

    def test_automatic_and_explicit_numeric_blocks_use_distinct_rotation(self):
        self.assertFalse(_should_rotate_inline_block('T', '12'))
        self.assertTrue(_should_rotate_inline_block('H', '12'))
        self.assertTrue(_should_rotate_inline_block('H', '\uff11\uff12'))

    def test_two_explicit_single_digit_blocks_stay_stacked(self):
        grouped = _build_vertical_layout(48, '<T>11</T>', 0, 0.0, 1.0, {})
        separated = _build_vertical_layout(48, '<H>1</H><H>1</H>', 0, 0.0, 1.0, {})
        self.assertGreater(separated['height'], grouped['height'])

    def test_latin_horizontal_blocks_keep_sideways_vertical_behavior(self):
        self.assertEqual(
            auto_add_horizontal_tags('\u7b2cABC\u8a71'),
            '\u7b2c<H>ABC</H>\u8a71',
        )
        self.assertTrue(_should_rotate_inline_block('H', 'ABC'))
        self.assertTrue(_should_rotate_inline_block('H', 'A12'))


if __name__ == '__main__':
    unittest.main()
