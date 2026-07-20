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
    _UnifiedBatchBuffer,
    _get_key_limiter,
    _is_failed_translation_output,
    _is_quota_error,
    _openai_token_param,
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
    def _translator():
        translator = Gemini2StageTranslator()
        translator.refine_model = 'model-primary'
        translator.translate_model = 'model-primary'
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

    def test_parse_args_uses_only_the_configured_model_for_both_stages(self):
        translator = self._translator()
        translator.parse_args(SimpleNamespace(
            llm_provider='gemini',
            llm_api_key='',
            llm_base_url=None,
            llm_send_image=True,
            parallel_bands=False,
            llm_model='gemma-user-choice',
        ))

        self.assertEqual(translator.refine_model, 'gemma-user-choice')
        self.assertEqual(translator.translate_model, 'gemma-user-choice')

    def test_only_high_confidence_garbage_is_rejected(self):
        self.assertTrue(_is_failed_translation_output(_STRUCTURE_JUNK))
        self.assertTrue(_is_failed_translation_output('譯文\ufffd'))
        self.assertTrue(_is_failed_translation_output('譯文\ue123'))
        self.assertTrue(_is_failed_translation_output('OCR 漏抓的泡泡，請逐字讀出'))
        self.assertFalse(_is_failed_translation_output('R&'))
        self.assertFalse(_is_failed_translation_output('ドン'))
        self.assertFalse(_is_failed_translation_output('你好，老師。'))

    async def test_configured_model_keeps_existing_quota_backoff(self):
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

    async def test_single_and_batch_vision_calls_use_only_configured_model(self):
        translator = self._translator()
        called_models = []

        async def fake_json_call(*args, **kwargs):
            called_models.append(kwargs.get('model'))
            self.assertNotIn('fail_fast_on_all_429', kwargs)
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

        self.assertEqual(called_models, ['model-primary', 'model-primary'])

    async def test_batch_quota_error_does_not_launch_another_model_call(self):
        translator = self._translator()
        buffer = _UnifiedBatchBuffer(translator)
        single_called = False

        async def batch_quota(batch):
            raise RuntimeError('429 RESOURCE_EXHAUSTED')

        async def unexpected_single(payload):
            nonlocal single_called
            single_called = True
            return []

        translator._call_llm_batched = batch_quota
        translator._call_llm_single = unexpected_single
        future = asyncio.get_running_loop().create_future()

        await buffer._flush([(future, {'n': 1})])

        self.assertRegex(str(future.exception()), '429 RESOURCE_EXHAUSTED')
        self.assertFalse(single_called)

    async def test_cancelled_last_batch_waiter_stops_flush_retries(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class SlowTranslator:
            _batch_size = 1
            _batch_wait_s = 0

            async def _call_llm_batched(self, batch):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        buffer = _UnifiedBatchBuffer(SlowTranslator())
        waiter = asyncio.create_task(buffer.submit({'n': 1}))
        await asyncio.wait_for(started.wait(), timeout=1)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        await asyncio.wait_for(cancelled.wait(), timeout=1)
        await asyncio.sleep(0)

        self.assertFalse(buffer._flush_tasks)

    async def test_key_limiter_is_shared_and_caps_same_key(self):
        active = 0
        peak = 0

        async def one_call():
            nonlocal active, peak
            async with _get_key_limiter('gemini', 'same-secret'):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        with patch.dict(os.environ, {'GEMINI_KEY_CONCURRENCY': '1'}):
            await asyncio.gather(one_call(), one_call(), one_call())

        self.assertEqual(peak, 1)

    def test_quota_detection_walks_wrapped_exception_chain(self):
        try:
            try:
                raise RuntimeError('429 RESOURCE_EXHAUSTED')
            except RuntimeError as inner:
                raise TimeoutError('batch deadline') from inner
        except TimeoutError as outer:
            self.assertTrue(_is_quota_error(outer))

    def test_openai_modern_models_use_supported_token_parameter_first(self):
        self.assertEqual(
            _openai_token_param('openai', 'https://api.openai.com/v1', 'gpt-5.1'),
            'max_completion_tokens',
        )
        self.assertEqual(
            _openai_token_param('openrouter', 'https://openrouter.ai/api/v1', 'gpt-5.1'),
            'max_completion_tokens',
        )

    async def test_model_error_does_not_call_another_model(self):
        translator = self._translator()
        calls = []

        async def fake_call(payload):
            calls.append(translator.refine_model)
            raise RuntimeError('configured model DNS lookup failed')

        async def fake_fallback(src_texts, from_lang, to_lang):
            return ['既有回退譯文']

        translator._call_llm_single = fake_call
        translator._gt_then_polish = fake_fallback

        _, translations, _ = await self._run(translator)

        self.assertEqual(calls, ['model-primary'])
        self.assertEqual(translations, ['既有回退譯文'])

    async def test_structure_junk_does_not_call_another_model(self):
        translator = self._translator()
        calls = []

        async def fake_call(payload):
            calls.append(translator.refine_model)
            return [self._bbox(_STRUCTURE_JUNK)]

        translator._call_llm_single = fake_call

        _, translations, _ = await self._run(translator)

        self.assertEqual(calls, ['model-primary'])
        self.assertEqual(translations, ['こんにちは'])

    async def test_source_equality_is_not_a_failure(self):
        translator = self._translator()
        calls = []

        async def fake_call(payload):
            calls.append(translator.refine_model)
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

    async def test_outside_sfx_passthrough_uses_only_configured_model(self):
        translator = self._translator()
        calls = []

        async def fake_call(payload):
            calls.append(translator.refine_model)
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
