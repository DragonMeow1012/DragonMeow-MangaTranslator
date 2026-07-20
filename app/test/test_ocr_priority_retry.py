import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from server import myqueue


class OcrPriorityRetryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _task():
        return SimpleNamespace(
            image=b'image',
            config=SimpleNamespace(translator=SimpleNamespace(batch_group='book-a')),
            _retries=0,
            _ocr_retries=0,
            is_client_disconnected=AsyncMock(return_value=False),
        )

    @staticmethod
    def _queue():
        queue = Mock()
        queue.get_pos.return_value = 0
        queue.remove = AsyncMock(return_value=True)
        queue.add_task = Mock()
        return queue

    async def test_ocr_error_retries_at_front_before_succeeding(self):
        task = self._task()
        queue = self._queue()
        instance = SimpleNamespace(
            sent=AsyncMock(side_effect=[RuntimeError('OCR model failed'), b'ok']),
        )
        executors = SimpleNamespace(
            free_executors=Mock(return_value=1),
            find_executor=AsyncMock(return_value=instance),
            free_executor=AsyncMock(),
        )

        with (
            patch.object(myqueue, 'task_queue', queue),
            patch.object(myqueue, 'executor_instances', executors),
            patch.dict(os.environ, {'MT_OCR_RETRIES': '2'}),
        ):
            result = await myqueue.wait_in_queue(task, None)

        self.assertEqual(result, b'ok')
        self.assertEqual(task._ocr_retries, 1)
        queue.add_task.assert_called_once_with(task, priority=True)
        self.assertEqual(executors.free_executor.await_count, 2)

    async def test_exhausted_ocr_error_releases_book_tail(self):
        task = self._task()
        queue = self._queue()
        instance = SimpleNamespace(
            sent_stream=AsyncMock(side_effect=RuntimeError('OCR crashed')),
        )
        executors = SimpleNamespace(
            free_executors=Mock(return_value=1),
            find_executor=AsyncMock(return_value=instance),
            free_executor=AsyncMock(),
        )
        frames = []

        def notify(code, data):
            frames.append((code, data.decode('utf-8', errors='replace')))

        with (
            patch.object(myqueue, 'task_queue', queue),
            patch.object(myqueue, 'executor_instances', executors),
            patch.dict(os.environ, {'MT_OCR_RETRIES': '1'}),
            patch(
                'manga_translator.translators.notify_batch_page_skipped',
                new=AsyncMock(),
            ) as skipped,
        ):
            await myqueue.wait_in_queue(task, notify)

        self.assertEqual(task._ocr_retries, 1)
        queue.add_task.assert_called_once_with(task, priority=True)
        skipped.assert_awaited_once_with(task.config.translator)
        self.assertTrue(any(code == 1 and '優先重試' in text for code, text in frames))
        self.assertEqual(frames[-1][0], 2)


if __name__ == '__main__':
    unittest.main()
