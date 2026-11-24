import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from route.client_catalog import model_list, verify


class ClientCatalogTest(unittest.TestCase):
    clients = [('Codex service', None, '0.172.0')]
    route = {'route-gpt-6.2-sol': 'Route 6.2 Sol'}
    native = {'gpt-6.2-sol': 'GPT-6.2-Sol'}
    catalogs = {'0.172.0': [{'slug': 'route-gpt-6.2-sol', 'display_name': 'Route 6.2 Sol'}]}

    def test_stale_service_is_reloaded_and_checked_again(self):
        with patch('route.client_catalog.read_service', side_effect=[self.native, self.native | self.route]) as read:
            verify(self.clients, self.catalogs, True, {'socketPath': 'socket'})
            read.assert_called_with('socket', reload_provider=True)

    def test_partial_or_unbranded_picker_cannot_pass(self):
        for visible in (self.route, self.native, self.native | {'route-gpt-6.2-sol': 'Sol'}):
            with self.subTest(visible=visible), patch('route.client_catalog.read_service', return_value=visible):
                with self.assertRaisesRegex(RuntimeError, 'has not loaded'):
                    verify(self.clients, self.catalogs, True, {'socketPath': 'socket'})

    def test_respects_a_different_configured_provider(self):
        request = AsyncMock(side_effect=[{'result': {}}, {'result': {'config': {'model_provider': 'other'}}}])
        with self.assertRaisesRegex(RuntimeError, 'different provider'):
            asyncio.run(model_list(request, reload_provider=True))
        self.assertEqual(request.await_count, 2)

    def test_key_only_and_paginated_model_list(self):
        request = AsyncMock(side_effect=[{'result': {}}, {'result': {'data': [], 'nextCursor': 'second'}},
                   {'result': {'data': [{'model': 'route-gpt-6.2-sol', 'displayName': 'Route 6.2 Sol'}]}}])
        rows = asyncio.run(model_list(request))
        self.assertEqual(request.await_args.args[0]['params']['cursor'], 'second')
        with patch('route.client_catalog.read_service', return_value=rows) as read:
            verify(self.clients, self.catalogs, False, {'socketPath': 'socket'})
            read.assert_called_once()
