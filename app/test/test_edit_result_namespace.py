import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from server import main as server_main
from server.edit import (
    InvalidResultPath,
    RerenderRequest,
    _state_path,
    load_edit_state,
    resolve_result_folder,
)


class ResultFolderResolverTests(unittest.TestCase):
    def test_flat_result_path_remains_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            resolved = resolve_result_folder(root, '1700000000000-result-job')

            self.assertEqual(resolved, root.resolve() / '1700000000000-result-job')

    def test_result_path_can_be_scoped_to_a_discord_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_id = '404111257008865280'

            resolved = resolve_result_folder(root, 'result-job', user_id)

            self.assertEqual(resolved, root.resolve() / user_id / 'result-job')

    def test_uint64_max_is_a_valid_user_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            resolved = resolve_result_folder(
                root,
                'result-job',
                '18446744073709551615',
            )

            self.assertEqual(
                resolved,
                root.resolve() / '18446744073709551615' / 'result-job',
            )

    def test_invalid_discord_user_ids_are_rejected(self):
        invalid_ids = (
            '',
            '0',
            '00',
            '01',
            '-1',
            '+1',
            ' 1',
            '1 ',
            '１２３',
            'not-a-user',
            '18446744073709551616',
            '123456789012345678901',
        )
        with tempfile.TemporaryDirectory() as tmp:
            for user_id in invalid_ids:
                with self.subTest(user_id=user_id):
                    with self.assertRaises(InvalidResultPath):
                        resolve_result_folder(tmp, 'result-job', user_id)

    def test_folder_must_be_one_safe_ascii_leaf(self):
        invalid_folders = (
            '',
            '.',
            '..',
            '../result-job',
            'result-job/other',
            r'result-job\other',
            '/result-job',
            '_private',
            'result job',
            '結果',
        )
        with tempfile.TemporaryDirectory() as tmp:
            for folder in invalid_folders:
                with self.subTest(folder=folder):
                    with self.assertRaises(InvalidResultPath):
                        resolve_result_folder(tmp, folder, '404111257008865280')

    def test_nested_edit_state_is_loaded_from_the_user_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_id = '404111257008865280'
            folder = 'result-job'
            path = Path(_state_path(tmp, folder, user_id))
            path.parent.mkdir(parents=True)
            expected = {'sentinel': 'nested-state'}
            path.write_bytes(pickle.dumps(expected))

            loaded = load_edit_state(tmp, folder, user_id)

            self.assertEqual(loaded, expected)


class EditEndpointNamespaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_state_forwards_the_user_namespace(self):
        expected = {'width': 10, 'height': 20, 'regions': []}
        with patch('server.edit.state_to_json', return_value=expected) as state_to_json:
            actual = await server_main.edit_state(
                'result-job',
                '404111257008865280',
            )

        self.assertEqual(actual, expected)
        state_to_json.assert_called_once_with(
            server_main.RESULT_ROOT,
            'result-job',
            '404111257008865280',
        )

    async def test_rerender_saves_final_png_in_the_user_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_id = '404111257008865280'
            folder = 'result-job'
            result_dir = root / user_id / folder
            result_dir.mkdir(parents=True)
            rendered = Image.new('RGB', (3, 2), color=(12, 34, 56))
            rerender = AsyncMock(return_value=rendered)
            request = RerenderRequest(folder=folder, user_id=user_id)

            with (
                patch.object(server_main, 'RESULT_ROOT', root),
                patch('server.edit.rerender', rerender),
            ):
                await server_main.edit_rerender(request)

            final_path = result_dir / 'final.png'
            self.assertTrue(final_path.is_file())
            with Image.open(final_path) as saved:
                self.assertEqual(saved.size, (3, 2))
                self.assertEqual(saved.convert('RGB').getpixel((0, 0)), (12, 34, 56))
            rerender.assert_awaited_once_with(
                root,
                folder,
                [],
                [],
                [],
                user_id=user_id,
            )


if __name__ == '__main__':
    unittest.main()
