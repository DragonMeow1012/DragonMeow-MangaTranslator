import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import AsyncMock

from manga_translator.config import Translator, TranslatorConfig
from manga_translator.translators import (
    _clear_grouped_translator_cache,
    _get_request_translator,
    notify_batch_page_skipped,
)
from manga_translator.translators.gemini_2stage import _UnifiedBatchBuffer


class TranslationBatchGroupTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        _clear_grouped_translator_cache()

    def test_only_identical_book_and_config_share_a_translator(self):
        with patch.dict(os.environ, {'GEMINI_2STAGE_BATCH_SIZE': '5'}):
            first = _get_request_translator(
                Translator.gemini_2stage,
                TranslatorConfig(
                    batch_group='book-a', batch_total_pages=31,
                    batch_pages=3, batch_wait_ms=50_000,
                ),
            )
            same = _get_request_translator(
                Translator.gemini_2stage,
                TranslatorConfig(
                    batch_group='book-a', batch_total_pages=31,
                    batch_pages=3, batch_wait_ms=50_000,
                ),
            )
            other_book = _get_request_translator(
                Translator.gemini_2stage,
                TranslatorConfig(batch_group='book-b', batch_total_pages=31),
            )
            other_language = _get_request_translator(
                Translator.gemini_2stage,
                TranslatorConfig(
                    batch_group='book-a', batch_total_pages=31, target_lang='CHT',
                ),
            )

        self.assertIs(first, same)
        self.assertIsNot(first, other_book)
        self.assertIsNot(first, other_language)
        self.assertEqual(first._batch_size, 3)
        self.assertEqual(first._batch_wait_s, 50.0)

    def test_book_keeps_first_runtime_batch_setting(self):
        first = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-stable', batch_total_pages=31,
                batch_pages=3, batch_wait_ms=50_000,
            ),
        )
        changed_mid_book = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-stable', batch_total_pages=31,
                batch_pages=5, batch_wait_ms=90_000,
            ),
        )
        self.assertIs(first, changed_mid_book)
        self.assertEqual(changed_mid_book._batch_size, 3)
        self.assertEqual(changed_mid_book._batch_wait_s, 50.0)

    def test_book_keeps_first_send_image_setting(self):
        first = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-stable-image-mode', batch_total_pages=12,
                batch_pages=3, llm_send_image=True,
            ),
        )
        changed_mid_book = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-stable-image-mode', batch_total_pages=12,
                batch_pages=3, llm_send_image=False,
            ),
        )

        self.assertIs(first, changed_mid_book)
        self.assertTrue(changed_mid_book._send_image)

    def test_missing_book_group_forces_single_page_mode(self):
        with patch.dict(os.environ, {'GEMINI_2STAGE_BATCH_SIZE': '5'}):
            translator = _get_request_translator(
                Translator.gemini_2stage,
                TranslatorConfig(),
            )
        self.assertEqual(translator._batch_size, 1)

    async def test_31_pages_with_size_5_flushes_tail_immediately(self):
        class FakeTranslator:
            _batch_size = 5
            _batch_wait_s = 60

            async def _call_llm_batched(self, batch):
                return [[item[1]['page']] for item in batch]

        buffer = _UnifiedBatchBuffer(FakeTranslator())
        tasks = [
            asyncio.create_task(buffer.submit({
                'page': page,
                'batch_total_pages': 31,
            }))
            for page in range(1, 32)
        ]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        self.assertEqual(results[-1], [31])
        self.assertEqual(buffer._items, [])

    async def test_confirmed_blank_pages_do_not_consume_batch_slots(self):
        config = TranslatorConfig(
            batch_group='book-with-blanks', batch_total_pages=7,
        )
        with patch.dict(os.environ, {'GEMINI_2STAGE_BATCH_SIZE': '5'}):
            translator = _get_request_translator(Translator.gemini_2stage, config)

        batches = []
        batch_images = []

        async def fake_batch(batch):
            batches.append([item[1]['page'] for item in batch])
            batch_images.append([item[1]['img_data'] for item in batch])
            return [[item[1]['page']] for item in batch]

        translator._call_llm_batched = fake_batch
        translator._batch_wait_s = 60
        translator._batch_total_pages = 7
        buffer = _UnifiedBatchBuffer(translator)
        translator._batch_buffer = buffer

        # 只有三頁 OCR 成功；其餘四頁確定無字。空白頁不會湊成 5 頁，
        # 但會完成本書總頁數並立即放行三頁尾批。
        tasks = [
            asyncio.create_task(buffer.submit({
                'page': page,
                'batch_total_pages': 7,
                'img_data': (f'image-{page}'.encode(), 'image/jpeg'),
            }))
            for page in range(1, 4)
        ]
        for _ in range(4):
            await notify_batch_page_skipped(config)
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        self.assertEqual(batches, [[1, 2, 3]])
        self.assertEqual(len(results), 3)
        self.assertEqual(buffer._skipped_count, 4)
        self.assertEqual(batch_images, [[
            (b'image-1', 'image/jpeg'),
            (b'image-2', 'image/jpeg'),
            (b'image-3', 'image/jpeg'),
        ]])

    async def test_batched_vision_sends_one_image_per_ocr_page_in_order(self):
        translator = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-images', batch_total_pages=3,
                batch_pages=3, batch_wait_ms=50_000,
                llm_send_image=True,
            ),
        )
        response = SimpleNamespace(pages=[
            SimpleNamespace(page_id=2, bboxes=['bbox-3']),
            SimpleNamespace(page_id=0, bboxes=['bbox-1']),
            SimpleNamespace(page_id=1, bboxes=['bbox-2']),
        ])
        translator._gemini_json_call = AsyncMock(return_value=response)
        payloads = [
            (
                None,
                {
                    'directive': f'page {page}',
                    'system_instruction': 'same rules',
                    'img_data': (f'image-{page}'.encode(), 'image/jpeg'),
                    'n': 1,
                },
            )
            for page in range(1, 4)
        ]

        results = await translator._call_llm_batched(payloads)

        self.assertEqual(results, [['bbox-1'], ['bbox-2'], ['bbox-3']])
        kwargs = translator._gemini_json_call.await_args.kwargs
        self.assertEqual(
            kwargs['image_data_list'],
            [
                (b'image-1', 'image/jpeg'),
                (b'image-2', 'image/jpeg'),
                (b'image-3', 'image/jpeg'),
            ],
        )
        self.assertEqual(kwargs['user_text'].count('==== 第 '), 3)

    async def test_malformed_batch_image_fails_before_any_llm_request(self):
        translator = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-invalid-image', batch_total_pages=2,
                batch_pages=2, batch_wait_ms=30_000,
            ),
        )
        translator._gemini_json_call = AsyncMock()
        payloads = [
            (None, {
                'directive': 'page 1', 'system_instruction': 'rules',
                'img_data': (b'image-1', 'image/jpeg'), 'n': 1,
            }),
            (None, {
                'directive': 'page 2', 'system_instruction': 'rules',
                'img_data': (b'', 'image/jpeg'), 'n': 1,
            }),
        ]

        with self.assertRaisesRegex(ValueError, 'page_id=1'):
            await translator._call_llm_batched(payloads)
        translator._gemini_json_call.assert_not_awaited()

    async def test_no_image_five_pages_share_one_text_request(self):
        translator = _get_request_translator(
            Translator.gemini_2stage,
            TranslatorConfig(
                batch_group='book-text-only', batch_total_pages=5,
                batch_pages=5, batch_wait_ms=90_000,
                llm_send_image=False,
            ),
        )
        response = SimpleNamespace(pages=[
            SimpleNamespace(
                page_id=page_id,
                translated_texts=[
                    SimpleNamespace(text_id=0, translated_text=f'譯文-{page_id + 1}')
                ],
            )
            for page_id in reversed(range(5))
        ])
        translator._gemini_json_call = AsyncMock(return_value=response)
        buffer = _UnifiedBatchBuffer(translator)
        translator._batch_buffer = buffer

        tasks = [
            asyncio.create_task(buffer.submit({
                'batch_kind': 'text',
                'src_texts': [f'原文-{page}'],
                'from_lang': 'Japanese',
                'to_lang': 'Traditional Chinese',
                'batch_total_pages': 5,
            }))
            for page in range(1, 6)
        ]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        self.assertEqual(results, [[f'譯文-{page}'] for page in range(1, 6)])
        translator._gemini_json_call.assert_awaited_once()
        kwargs = translator._gemini_json_call.await_args.kwargs
        self.assertIsNone(kwargs['image_data'])
        self.assertNotIn('image_data_list', kwargs)
        self.assertEqual(kwargs['user_text'].count('"page_id"'), 6)

    async def test_no_image_text_tail_flushes_without_waiting(self):
        class FakeTextTranslator:
            _batch_size = 5
            _batch_wait_s = 90

            def __init__(self):
                self.batches = []

            async def _call_text_llm_batched(self, batch):
                pages = [item[1]['page'] for item in batch]
                self.batches.append(pages)
                return [[page] for page in pages]

        translator = FakeTextTranslator()
        buffer = _UnifiedBatchBuffer(translator)
        tasks = [
            asyncio.create_task(buffer.submit({
                'batch_kind': 'text',
                'page': page,
                'src_texts': [str(page)],
                'batch_total_pages': 7,
            }))
            for page in range(1, 8)
        ]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        self.assertEqual(translator.batches, [[1, 2, 3, 4, 5], [6, 7]])
        self.assertEqual(results, [[page] for page in range(1, 8)])
        self.assertEqual(buffer._items, [])


if __name__ == '__main__':
    unittest.main()
