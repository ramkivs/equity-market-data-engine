"""B2 symbol-resolution tests, entirely synthetic and disposable."""
import json
import tempfile
import unittest
from pathlib import Path

from tests import serving_fixtures
from serving.baseline import open_baseline
from serving.index import build_index, write_index
from serving.query import QueryError, query_instrument, query_filters, query_associations
from serving.saved import create_saved, execute_saved


class FakeBaseline:
    def __init__(self, root):
        self.root = str(root)
        self.manifest_digest = 'synthetic'
    def path(self, relative):
        return str(Path(self.root) / relative)


def row(date, symbol, isin, validity='VALID', raw=None):
    return {'business_date': date, 'format_family': 'legacy13', 'source_line_number': 1,
            'isin_normalized': isin, 'isin_validity': validity,
            'source_values': {'listing_symbol': symbol if raw is None else raw,
                              'underlying_symbol': None, 'series': 'EQ', 'security_isin': isin}}


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.baseline = FakeBaseline(self.root)
        self.path = 'rows.jsonl'
        self.index = {'files': {self.path: {'family': 'legacy13', 'year': '2020', 'instruments': []}}}

    def tearDown(self):
        self.temp.cleanup()

    def set_rows(self, rows):
        (self.root / self.path).write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        self.index['files'][self.path]['instruments'] = [[r['source_values']['listing_symbol'], 'EQ'] for r in rows]
        # Each test uses one package identity; invalidate the process cache when
        # changing synthetic data (real baselines are immutable).
        self.baseline.manifest_digest += 'x'

    def test_rename_boundary_q3_q4_and_invalid_unlinked(self):
        self.set_rows([row('2020-01-01', 'OLD', 'ISIN-A'), row('2020-01-02', 'NEW', 'ISIN-A'),
                       row('2020-01-03', 'NEW', 'BAD', 'INVALID_LENGTH')])
        rows = query_instrument(self.baseline, self.index, 'NEW', 'EQ')
        self.assertEqual([r['source_values']['listing_symbol'] for r in rows], ['OLD', 'NEW', 'NEW'])
        self.assertEqual(rows[0]['serving']['symbol_resolution']['basis'], 'valid-isin-correlation')
        self.assertEqual(rows[-1]['serving']['symbol_resolution']['basis'], 'exact-observation')
        self.assertIsNone(rows[-1]['serving']['symbol_resolution']['correlation_identity'])
        filtered = query_filters(self.baseline, self.index, {'symbol': 'OLD', 'series': 'EQ'})
        self.assertEqual([r['source_values']['listing_symbol'] for r in filtered], ['OLD', 'NEW'])

    def test_ticker_reuse_and_overlapping_observations_fail_closed(self):
        self.set_rows([row('2020-01-01', 'SHARED', 'ISIN-A'), row('2021-01-01', 'SHARED', 'ISIN-B')])
        with self.assertRaisesRegex(QueryError, 'multiple valid ISINs'):
            query_instrument(self.baseline, self.index, 'SHARED', 'EQ')
        with self.assertRaisesRegex(QueryError, 'multiple valid ISINs'):
            query_filters(self.baseline, self.index, {'symbol': 'SHARED', 'series': 'EQ'})
        with self.assertRaisesRegex(QueryError, 'multiple valid ISINs'):
            query_associations(self.baseline, self.index, symbol='SHARED', series='EQ', documents=[(1, {'security_id': 'ISIN-A', 'associations': []})])
        self.set_rows([row('2020-01-01', 'OLD', 'ISIN-A'), row('2020-01-02', 'NEW', 'ISIN-A'),
                       row('2020-01-03', 'OLD', 'ISIN-A')])
        with self.assertRaisesRegex(QueryError, 'overlapping observed ticker ranges'):
            query_instrument(self.baseline, self.index, 'NEW', 'EQ')
        self.set_rows([row('2020-01-01', 'OLD', 'ISIN-A'), row('2020-01-01', 'NEW', 'ISIN-A')])
        with self.assertRaisesRegex(QueryError, 'overlapping observed ticker ranges'):
            query_instrument(self.baseline, self.index, 'NEW', 'EQ')

    def test_q5_dated_association_projection(self):
        self.set_rows([row('2020-01-01', 'OLD', 'ISIN-A'), row('2020-01-02', 'NEW', 'ISIN-A')])
        doc = {'security_id': 'ISIN-A', 'is_valid_isin_format': True, 'associations': [
            {'symbol': 'OLD', 'series': 'EQ', 'observed_from': '2020-01-01', 'observed_to': '2020-01-01'},
            {'symbol': 'NEW', 'series': 'EQ', 'observed_from': '2020-01-02', 'observed_to': '2020-01-02'}]}
        out = query_associations(self.baseline, self.index, symbol='NEW', series='EQ', documents=[(1, doc)])
        self.assertEqual([item['symbol'] for item in out], ['OLD', 'NEW'])
        self.assertEqual([item['serving']['trading_symbol']['observed_symbols'] for item in out], [['OLD'], ['NEW']])

    def test_saved_queries_and_legacy_index(self):
        pkg = self.root / 'pkg'
        facts = serving_fixtures.build_fixture_package(str(pkg))
        baseline = open_baseline(str(pkg), spec=facts['spec'])
        index = build_index(baseline)
        state, saved = self.root / 'state', self.root / 'saved'
        write_index(str(state), index)
        create_saved(str(saved), 'ticker', 'Q3-instrument', {'symbol': 'RELIANCE', 'series': 'EQ'})
        out = execute_saved(str(saved), 'ticker', baseline, str(state))
        self.assertEqual(len(out['rows']), 4)
        self.assertEqual(index['format'], 'serving-index/1.2')
        self.assertEqual(out['rows'][-1]['source_values']['listing_symbol'], '500325')
        self.assertEqual(out['rows'][-1]['source_values']['underlying_symbol'], 'RELIANCE')
        create_saved(str(saved), 'legacy-id', 'Q3-instrument', {'symbol': '500325', 'series': 'EQ'})
        self.assertEqual(len(execute_saved(str(saved), 'legacy-id', baseline, str(state))['rows']), 1)
        create_saved(str(saved), 'filters', 'Q4-filter', {'filters': {'symbol': 'RELIANCE', 'series': 'EQ'}})
        self.assertEqual(len(execute_saved(str(saved), 'filters', baseline, str(state))['rows']), 4)
        create_saved(str(saved), 'associations', 'Q5-association', {'symbol': 'RELIANCE', 'series': 'EQ'})
        self.assertEqual(execute_saved(str(saved), 'associations', baseline, str(state))['record_count'], 2)

    def test_missing_identity_and_date_never_create_links(self):
        self.set_rows([row('2020-01-01', 'OLD', 'ISIN-A'), row('', 'NEW', 'ISIN-A'),
                       row('2020-01-02', 'NEW', '', 'BLANK')])
        results = query_instrument(self.baseline, self.index, 'NEW', 'EQ')
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['serving']['symbol_resolution']['basis'] == 'exact-observation' for r in results))


if __name__ == '__main__':
    unittest.main()
