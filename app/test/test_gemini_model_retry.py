import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from manga_translator.translators.gemini_2stage import (
    Gemini2StageTranslator,
    UnifiedBBoxResult,
    UnifiedResponse,
    _AllKeys429Error,
    _UnifiedBatchBuffer,
    _is_failed_translation_output,
)


_STRUCTURE_JUNK = '%sxf_{ta}{text_id} (The ext_id_of_the_object)'


class GeminiModelRetryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _region(text='こんにちは', *, role='dialogue'):
        return SimpleNamespace(
            text=text,
            xyxy=(8, 8, 56, 56),
            _layout_role=role,
            _bubble_rect=(4, 4, 60, 60) if role == 'dialogue' else None,
            _bubble_rects=[],
            _synth_bubble=False,
        )

    @staticmethod
    def _translator(*retry_models):
        translator = Gemini2StageTranslator()
        translator.refine_model = 'model-primary'
        translator.translate_model = 'model-primary'
        translator._retry_models = list(retry_models)
        translator._batch_size = 1
        translator._batch_buffer = None
        return translator

    @staticmethod
    def _bbox(translated_text, *, corrected_text='こんにちは'):
        return UnifiedBBoxResult(
            bbox_id=0,
            corrected_text=corrected_text,
            translated_text=translated_text,
        )

    async def _run(self, translator, region=None):
        return await translator._unified_call(
            Image.new('RGB', (64, 64), 'white'),
            [region or self._region()],
            'Japanese',
            'Traditional Chinese',
            64,
            64,
        )

    def test_retry_model_config_is_distinct_and_capped_at_two_fallbacks(self):
        translator = self._translator()
        translator.parse_args(SimpleNamespace(
            llm_provider='gemini',
            llm_api_key='',
            llm_base_url=None,
            llm_send_image=True,
            parallel_bands=False,
            llm_model='model-primary',
            llm_retry_models=[
                'model-primary', 'model-alt-a', 'model-alt-a',
                'model-alt-b', 'model-alt-c',
            ],
        ))

        self.assertEqual(translator._retry_models, ['model-alt-a', 'model-alt-b'])

    def test_only_high_confidence_garbage_is_rejected(self):
        self.assertTrue(_is_failed_translation_output(_STRUCTURE_JUNK))
        self.assertTrue(_is_failed_translation_output('譯文\ufffd'))
        self.assertTrue(_is_failed_translation_output('譯文\ue123'))
        self.assertTrue(_is_failed_translation_output('OCR 漏抓的泡泡，請逐字讀出'))
        self.assertFalse(_is_failed_translation_output('R&'))
        self.assertFalse(_is_failed_translation_output('ドン'))
        self.assertFalse(_is_failed_translation_output('你好，老師。'))

    async def test_all_keys_429_fail_fast_without_quota_sleep(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        translator._provider = 'gemini'
        translator._api_keys = ['key-a', 'key-b', 'key-c']
        translator._call_idx = 0
        called_keys = []

        async def always_quota(*args, **kwargs):
            called_keys.append(args[0])
            raise RuntimeError('429 RESOURCE_EXHAUSTED')

        translator._call_gemini_native = always_quota
        sleep_mock = AsyncMock()
        with patch(
            'manga_translator.translators.gemini_2stage.asyncio.sleep',
            new=sleep_mock,
        ):
            with self.assertRaises(_AllKeys429Error):
                await translator._gemini_json_call(
                    model='model-primary',
                    system_instruction='system',
                    user_text='user',
                    fail_fast_on_all_429=True,
                )

        self.assertEqual(called_keys, ['key-a', 'key-b', 'key-c'])
        sleep_mock.assert_not_awaited()

    async def test_without_model_chain_keeps_existing_quota_backoff(self):
        translator = self._translator()
        translator._provider = 'gemini'
        translator._api_keys = ['key-a', 'key-b']
        translator._call_idx = 0
        called_keys = []

        async def always_quota(*args, **kwargs):
            called_keys.append(args[0])
            raise RuntimeError('429 RESOURCE_EXHAUSTED')

        translator._call_gemini_native = always_quota
        sleep_mock = AsyncMock()
        with (
            patch.dict(os.environ, {'GEMINI_429_RETRIES': '1'}),
            patch(
                'manga_translator.translators.gemini_2stage.asyncio.sleep',
                new=sleep_mock,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, '429 RESOURCE_EXHAUSTED'):
                await translator._gemini_json_call(
                    model='model-primary',
                    system_instruction='system',
                    user_text='user',
                )

        self.assertEqual(called_keys, ['key-a', 'key-b', 'key-a', 'key-b'])
        sleep_mock.assert_awaited_once()

    async def test_single_and_batch_vision_calls_enable_fast_429_switch(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        fast_flags = []

        async def fake_json_call(*args, **kwargs):
            fast_flags.append(kwargs.get('fail_fast_on_all_429'))
            if kwargs.get('schema') is UnifiedResponse:
                return SimpleNamespace(bboxes=[])
            return SimpleNamespace(pages=[])

        translator._gemini_json_call = fake_json_call
        payload = {
            'directive': 'directive',
            'system_instruction': 'system',
            'img_data': (b'image', 'image/png'),
            'n': 1,
        }

        await translator._call_llm_single(payload)
        await translator._call_llm_batched([(None, payload)])

        self.assertEqual(fast_flags, [True, True])

    async def test_batch_all_keys_429_skips_same_model_single_page_retry(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        buffer = _UnifiedBatchBuffer(translator)
        single_called = False

        async def batch_quota(batch):
            raise _AllKeys429Error(
                'model-primary', 3, RuntimeError('429 RESOURCE_EXHAUSTED'),
            )

        async def unexpected_single(payload, *, model=None):
            nonlocal single_called
            single_called = True
            return []

        translator._call_llm_batched = batch_quota
        translator._call_llm_single = unexpected_single
        future = asyncio.get_running_loop().create_future()

        await buffer._flush([(future, {'n': 1})])

        self.assertIsInstance(future.exception(), _AllKeys429Error)
        self.assertFalse(single_called)

    async def test_model_errors_switch_until_third_distinct_model_succeeds(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []

        async def fake_call(payload, *, model=None):
            current = model or translator.refine_model
            calls.append(current)
            if current != 'model-alt-b':
                raise RuntimeError(f'{current} failed')
            return [self._bbox('你好')]

        async def unexpected_fallback(*args, **kwargs):
            self.fail('existing fallback must not run after a retry model succeeds')

        translator._call_llm_single = fake_call
        translator._gt_then_polish = unexpected_fallback

        _, translations, explicit_skip = await self._run(translator)

        self.assertEqual(calls, ['model-primary', 'model-alt-a', 'model-alt-b'])
        self.assertEqual(translations, ['你好'])
        self.assertEqual(explicit_skip, set())

    async def test_all_nonquota_model_errors_use_existing_gt_fallback(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []

        async def fake_call(payload, *, model=None):
            current = model or translator.refine_model
            calls.append(current)
            raise RuntimeError(f'{current} DNS lookup failed')

        async def fake_fallback(src_texts, from_lang, to_lang):
            return ['既有回退譯文']

        translator._call_llm_single = fake_call
        translator._gt_then_polish = fake_fallback

        _, translations, _ = await self._run(translator)

        self.assertEqual(calls, ['model-primary', 'model-alt-a', 'model-alt-b'])
        self.assertEqual(translations, ['既有回退譯文'])

    async def test_exhausted_models_keep_primary_error_fallback_semantics(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []

        async def fake_call(payload, *, model=None):
            current = model or translator.refine_model
            calls.append(current)
            if current == 'model-primary':
                raise RuntimeError('429 quota exhausted')
            raise RuntimeError('DNS lookup failed')

        async def unexpected_fallback(*args, **kwargs):
            self.fail('primary quota errors must retain the existing page-retry path')

        translator._call_llm_single = fake_call
        translator._gt_then_polish = unexpected_fallback

        with self.assertRaisesRegex(RuntimeError, '429 quota exhausted'):
            await self._run(translator)

        self.assertEqual(calls, ['model-primary', 'model-alt-a', 'model-alt-b'])

    async def test_structure_junk_reruns_the_attachment_with_other_models(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []

        async def fake_call(payload, *, model=None):
            current = model or translator.refine_model
            calls.append(current)
            if current == 'model-primary':
                return [self._bbox(_STRUCTURE_JUNK)]
            if current == 'model-alt-a':
                return [self._bbox('譯文\ufffd')]
            return [self._bbox('你好')]

        async def unexpected_fallback(*args, **kwargs):
            self.fail('existing fallback must not run after malformed output is repaired')

        translator._call_llm_single = fake_call
        translator._gt_then_polish = unexpected_fallback

        _, translations, _ = await self._run(translator)

        self.assertEqual(calls, ['model-primary', 'model-alt-a', 'model-alt-b'])
        self.assertEqual(translations, ['你好'])

    async def test_exhausted_models_return_to_existing_fallback(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []
        fallback_sources = []

        async def fake_call(payload, *, model=None):
            current = model or translator.refine_model
            calls.append(current)
            return [self._bbox(_STRUCTURE_JUNK)]

        async def fake_fallback(src_texts, from_lang, to_lang):
            fallback_sources.append(src_texts)
            return ['既有回退譯文']

        translator._call_llm_single = fake_call
        translator._gt_then_polish = fake_fallback

        _, translations, _ = await self._run(translator)

        self.assertEqual(calls, ['model-primary', 'model-alt-a', 'model-alt-b'])
        self.assertEqual(fallback_sources, [['こんにちは']])
        self.assertEqual(translations, ['既有回退譯文'])

    async def test_source_equality_is_not_a_failure(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []

        async def fake_call(payload, *, model=None):
            calls.append(model or translator.refine_model)
            return [self._bbox('こんにちは', corrected_text='こんにちは')]

        async def unexpected_fallback(*args, **kwargs):
            self.fail('an unchanged but valid value must not trigger fallback')

        translator._call_llm_single = fake_call
        translator._gt_then_polish = unexpected_fallback

        _, translations, _ = await self._run(
            translator,
            self._region('こんにちは'),
        )

        self.assertEqual(calls, ['model-primary'])
        self.assertEqual(translations, ['こんにちは'])

    async def test_outside_sfx_passthrough_never_switches_models(self):
        translator = self._translator('model-alt-a', 'model-alt-b')
        calls = []

        async def fake_call(payload, *, model=None):
            calls.append(model or translator.refine_model)
            return [self._bbox('ドン', corrected_text='ドン')]

        async def unexpected_fallback(*args, **kwargs):
            self.fail('outside SFX must not be translated or sent to fallback')

        translator._call_llm_single = fake_call
        translator._gt_then_polish = unexpected_fallback

        _, translations, explicit_skip = await self._run(
            translator,
            self._region('ドン', role='outside_sfx'),
        )

        self.assertEqual(calls, ['model-primary'])
        self.assertEqual(translations, [''])
        self.assertEqual(explicit_skip, {0})


if __name__ == '__main__':
    unittest.main()
