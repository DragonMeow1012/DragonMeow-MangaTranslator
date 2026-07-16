import asyncio
import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from manga_translator.manga_translator import MangaTranslator


translator_module = importlib.import_module('manga_translator.manga_translator')


class OcrTimeoutTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _translator():
        translator = MangaTranslator.__new__(MangaTranslator)
        translator._model_usage_timestamps = {}
        translator.verbose = False
        translator.result_sub_folder = ''
        translator.device = 'cpu'
        return translator

    @staticmethod
    def _config_and_context():
        config = SimpleNamespace(
            ocr=SimpleNamespace(ocr='paddle', ocr_device='cpu'),
            render=SimpleNamespace(font_color_fg=None, font_color_bg=None),
        )
        ctx = SimpleNamespace(img_rgb=object(), textlines=[object()])
        return config, ctx

    async def test_default_timeout_is_240_seconds(self):
        translator = self._translator()
        config, ctx = self._config_and_context()
        captured_timeout = None

        async def completed_ocr(*args, **kwargs):
            return []

        async def capture_wait_for(awaitable, timeout):
            nonlocal captured_timeout
            captured_timeout = timeout
            return await awaitable

        translator._run_async_in_thread = completed_ocr
        with patch.object(translator_module.asyncio, 'wait_for', capture_wait_for):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('MANGA_OCR_TIMEOUT', None)
                result = await translator._run_ocr(config, ctx)

        self.assertEqual(result, [])
        self.assertEqual(captured_timeout, 240)

    async def test_timeout_raises_for_retry_without_requiring_an_instance_logger(self):
        translator = self._translator()
        config, ctx = self._config_and_context()

        async def slow_ocr(*args, **kwargs):
            await asyncio.sleep(1)

        translator._run_async_in_thread = slow_ocr

        with (
            patch.dict(os.environ, {'MANGA_OCR_TIMEOUT': '0.001'}),
            patch.object(translator_module, 'logger') as mock_logger,
        ):
            with self.assertRaisesRegex(TimeoutError, '不會當成無文字頁跳過'):
                await translator._run_ocr(config, ctx)

        mock_logger.error.assert_called_once()
        self.assertIn('OCR 超過 0.001 秒', mock_logger.error.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
