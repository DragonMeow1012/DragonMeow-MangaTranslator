import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from manga_translator import Context
from manga_translator.manga_translator import MangaTranslator


def _translator_with_stale_flag(value: bool) -> MangaTranslator:
    translator = MangaTranslator.__new__(MangaTranslator)
    translator.verbose = False
    translator.result_sub_folder = None
    translator._current_image_context = {}
    translator._is_streaming_mode = value
    translator._result_path = lambda name: name
    return translator


def _config(web_optimized: bool):
    return SimpleNamespace(
        upscale=SimpleNamespace(revert_upscaling=False),
        _web_frontend_optimized=web_optimized,
    )


def _context() -> Context:
    ctx = Context()
    ctx.result = Image.new('RGB', (12, 18), color='white')
    return ctx


class StreamingModeIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_result_ignores_stale_shared_web_flag(self):
        translator = _translator_with_stale_flag(True)
        ctx = await translator._revert_upscale(_config(False), _context())

        self.assertEqual(ctx.result.size, (12, 18))
        self.assertFalse(getattr(ctx, 'use_placeholder', False))

    async def test_web_result_uses_its_own_request_flag(self):
        translator = _translator_with_stale_flag(False)
        with patch(
            'manga_translator.manga_translator.cv2.imwrite',
            return_value=True,
        ):
            ctx = await translator._revert_upscale(_config(True), _context())

        self.assertEqual(ctx.result.size, (1, 1))
        self.assertTrue(ctx.use_placeholder)


if __name__ == '__main__':
    unittest.main()
