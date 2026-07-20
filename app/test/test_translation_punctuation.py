import unittest

from manga_translator.translators.common import (
    CommonTranslator,
    normalize_translation_punctuation,
)


class TranslationPunctuationTests(unittest.TestCase):
    @staticmethod
    def _cleanup(text: str, language: str = 'CHT') -> str:
        class CleanupState:
            _normalize_punctuation = True

        return CommonTranslator._clean_translation_output(
            CleanupState(), '原文', text, language,
        )

    def test_converts_chinese_fullwidth_punctuation_only(self):
        self.assertEqual(
            normalize_translation_punctuation('真的嗎？可以！價格：１００，謝謝。'),
            '真的嗎?可以!價格:１００,謝謝.',
        )

    def test_compacts_spaced_fullwidth_dot_runs(self):
        self.assertEqual(
            normalize_translation_punctuation('就是這樣。 ． ． ． ．我開始生活'),
            '就是這樣...我開始生活',
        )

    def test_preserves_fullwidth_square_brackets_as_literal_text(self):
        self.assertEqual(
            normalize_translation_punctuation('第一行［BR］第二行？'),
            '第一行［BR］第二行?',
        )

    def test_existing_ascii_control_marker_is_untouched(self):
        self.assertEqual(
            normalize_translation_punctuation('第一行[BR]第二行？'),
            '第一行[BR]第二行?',
        )

    def test_chinese_cleanup_applies_normalization(self):
        self.assertEqual(
            self._cleanup('第一行？[BR]第二行！'),
            '第一行?[BR]第二行!',
        )

    def test_chinese_cleanup_is_disabled_by_default(self):
        self.assertEqual(
            CommonTranslator._clean_translation_output(
                None, '原文', '第一行？[BR]第二行！', 'CHT',
            ),
            '第一行？[BR]第二行！',
        )

    def test_non_chinese_targets_keep_native_punctuation(self):
        self.assertEqual(
            CommonTranslator._clean_translation_output(
                None, '原文', 'これは本当？', 'JPN',
            ),
            'これは本当？',
        )

    def test_cjk_text_does_not_gain_space_after_normalized_comma(self):
        self.assertEqual(
            self._cleanup('你好，世界。'),
            '你好,世界.',
        )

    def test_cyrillic_word_separator_still_gains_space(self):
        self.assertEqual(
            CommonTranslator._clean_translation_output(
                None, 'source', 'Привет,мир', 'RUS',
            ),
            'Привет, мир',
        )

    def test_latin_word_separator_still_gains_space(self):
        self.assertEqual(
            CommonTranslator._clean_translation_output(
                None, 'source', 'Hello,world', 'ENG',
            ),
            'Hello, world',
        )

    def test_decimal_does_not_gain_space(self):
        self.assertEqual(
            self._cleanup('數值２．０'),
            '數值２.０',
        )


if __name__ == '__main__':
    unittest.main()
