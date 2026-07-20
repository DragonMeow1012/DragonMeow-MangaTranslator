import asyncio
import unittest
from unittest.mock import patch

from server import main as server_main


class WebJobLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        for task in tuple(server_main._WEB_JOB_TASKS.values()):
            task.cancel()
        server_main._WEB_JOB_TASKS.clear()
        server_main._WEB_JOBS.clear()

    def test_prune_removes_only_expired_completed_jobs(self):
        server_main._WEB_JOBS.update({
            'expired': {'done': True, 'updatedAt': 10.0, 'createdAt': 1.0},
            'fresh': {'done': True, 'updatedAt': 95.0, 'createdAt': 1.0},
            'running': {'done': False, 'updatedAt': 1.0, 'createdAt': 1.0},
        })

        with patch.object(server_main, '_WEB_JOB_RETENTION_SEC', 20):
            server_main._prune_web_jobs(now=100.0)

        self.assertNotIn('expired', server_main._WEB_JOBS)
        self.assertIn('fresh', server_main._WEB_JOBS)
        self.assertIn('running', server_main._WEB_JOBS)

    async def test_cancel_endpoint_finishes_job_and_stops_runner(self):
        runner = asyncio.create_task(asyncio.Event().wait())
        server_main._WEB_JOBS['job'] = {
            'done': False,
            'status': 'processing',
            'error': None,
        }
        server_main._WEB_JOB_TASKS['job'] = runner

        payload = await server_main.cancel_translate_job('job')

        self.assertTrue(runner.cancelled())
        self.assertTrue(payload['done'])
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['error'], 'Translation job cancelled')

    async def test_cancel_all_endpoint_stops_every_runner(self):
        runners = {
            job_id: asyncio.create_task(asyncio.Event().wait())
            for job_id in ('one', 'two')
        }
        server_main._WEB_JOBS.update({
            job_id: {'done': False, 'status': 'queued', 'error': None}
            for job_id in runners
        })
        server_main._WEB_JOB_TASKS.update(runners)

        payload = await server_main.cancel_all_translate_jobs()

        self.assertEqual(payload, {'cancelled': 2})
        self.assertTrue(all(task.cancelled() for task in runners.values()))
        self.assertTrue(all(job['done'] for job in server_main._WEB_JOBS.values()))
        self.assertTrue(all(
            job['error'] == 'Translation job cancelled'
            for job in server_main._WEB_JOBS.values()
        ))


if __name__ == '__main__':
    unittest.main()
