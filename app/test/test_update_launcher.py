import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import main as server_main
from server import update


class UpdateLauncherTests(unittest.TestCase):
    def test_launches_the_shared_batch_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            updater = root / 'update.bat'
            updater.write_text('@echo off\n', encoding='utf-8')

            with (
                patch.object(update, 'ROOT_DIR', root),
                patch.object(update, 'UPDATE_BAT', updater),
                patch.object(update.sys, 'platform', 'win32'),
                patch.object(update.subprocess, 'Popen') as popen,
            ):
                result = update.launch_updater()

        self.assertEqual(result, {'launched': True, 'updater': 'update.bat'})
        command = popen.call_args.args[0]
        self.assertEqual(command[:4], ['cmd.exe', '/d', '/s', '/c'])
        self.assertIn(str(updater), command[4])
        self.assertIn('--from-web', command[4])
        self.assertEqual(popen.call_args.kwargs['cwd'], str(root))

    def test_non_windows_platform_is_rejected(self):
        with patch.object(update.sys, 'platform', 'linux'):
            with self.assertRaisesRegex(RuntimeError, 'Windows only'):
                update.launch_updater()


class UpdateEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_endpoint_delegates_to_the_shared_updater(self):
        expected = {'launched': True, 'updater': 'update.bat'}
        with patch.object(update, 'launch_updater', return_value=expected) as launch:
            result = await server_main.update_launch()

        self.assertEqual(result, expected)
        launch.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
