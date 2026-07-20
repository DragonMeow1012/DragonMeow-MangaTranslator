import asyncio
import unittest

from manga_translator.mode.share import MangaShare


class ShareStreamCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_closing_progress_stream_cancels_worker_task(self):
        share = object.__new__(MangaShare)
        queue = asyncio.Queue()
        run_task = asyncio.create_task(asyncio.Event().wait())
        stream = share.progress_stream(queue, run_task)
        consumer = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)

        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)

        self.assertTrue(run_task.cancelled())


if __name__ == '__main__':
    unittest.main()
