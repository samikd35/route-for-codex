import copy
import unittest

from route.models import route_rows


class RouteCatalogTest(unittest.TestCase):
    def test_only_eligible_aliases_and_upgrades_are_published(self):
        base = dict(supported_in_api=True, shell_type='unified_exec',
                    supported_reasoning_levels=[{'effort': 'medium'}], context_window=500000)
        catalog = {'models': [
            dict(base, slug='gpt-6.1-terra', upgrade={'model': 'gpt-6.2-sol', 'migration_markdown': 'Sol'}),
            dict(base, slug='gpt-6.2-sol', upgrade={'model': 'gpt-7-next'}),
            dict(base, slug='gpt-6.2-astra'),
        ]}
        before = copy.deepcopy(catalog)
        key = {'data': [{'id': 'gpt-6.1-terra'}, {'id': 'gpt-6.2-sol'}]}
        terra, sol = route_rows(key, catalog)
        self.assertEqual(terra['upgrade']['model'], 'route-gpt-6.2-sol')
        self.assertEqual(terra['slug'], 'route-gpt-6.1-terra')
        self.assertEqual(terra['display_name'], 'Route 6.1 Terra')
        self.assertEqual(sol['description'], 'Uses your OpenAI API key')
        self.assertIsNone(sol['upgrade'])
        self.assertEqual(sol['supported_reasoning_levels'], base['supported_reasoning_levels'])
        self.assertEqual(sol['context_window'], base['context_window'])
        self.assertEqual(catalog, before)
        self.assertEqual(route_rows({'data': []}, catalog), [])
