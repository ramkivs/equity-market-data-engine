"""Row-local ticker projection tests; not identity-continuity validation."""
import tempfile
import unittest
from pathlib import Path

from tests import serving_fixtures
from serving.baseline import open_baseline
from serving.detail import query_record_detail
from serving.index import build_index
from serving.query import query_date_range, query_filters, query_instrument
from serving.symbols import observed_trading_symbol


class ObservedTickerTests(unittest.TestCase):
    def test_source_selection_and_no_inference(self):
        def row(family, listing, ticker, segment='CM', kind='STK', isin=''):
            return {'format_family': family, 'source_values': {'listing_symbol': listing,
                    'underlying_symbol': ticker, 'segment': segment, 'instrument_type': kind,
                    'security_isin': isin}}
        self.assertEqual(observed_trading_symbol(row('legacy13', 'OLD', None))['observed_symbol'], 'OLD')
        projected = observed_trading_symbol(row('udiff34', '123', 'NEW'))
        self.assertEqual((projected['observed_symbol'], projected['source_column']), ('NEW', 'TckrSymb'))
        self.assertEqual(observed_trading_symbol(row('udiff34', '123', '', isin='invalid'))['status'], 'unavailable')
        self.assertEqual(observed_trading_symbol(row('udiff34', '123', 'UNDERLYING', 'FO', 'FUT'))['status'], 'unavailable')
        # Different ISINs with the same symbol are only observations: no link or
        # identity conclusion is produced by this projection.
        self.assertEqual(observed_trading_symbol(row('udiff34', '1', 'REUSED', isin='A')),
                         observed_trading_symbol(row('udiff34', '2', 'REUSED', isin='B')))
        self.assertNotIn('identity', projected)

    def test_q2_q3_q4_and_detail_projection_preserves_raw_values(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / 'pkg'
            facts = serving_fixtures.build_fixture_package(str(package))
            baseline = open_baseline(str(package), spec=facts['spec'])
            index = build_index(baseline)
            original = {p.relative_to(package): p.read_bytes() for p in package.rglob('*') if p.is_file()}
            q3 = query_instrument(baseline, index, '500325', 'EQ', year=2024)[0]
            q2 = query_date_range(baseline, index, '2024-03-05', '2024-03-05')
            q4 = query_filters(baseline, index, {'segment': 'CM'})
            source = q3['serving']['source_file']
            line = q3['source_line_number']
            q7 = query_record_detail(baseline, index, source, line)['row']
            match = lambda result: next(r for r in result if r['serving']['source_file'] == source and r['source_line_number'] == line)
            expected = q3['serving']['trading_symbol']
            self.assertEqual(expected['observed_symbol'], 'RELIANCE')
            for row in (match(q2), match(q4), q7):
                self.assertEqual(row['serving']['trading_symbol'], expected)
                self.assertEqual(row['source_values'], q3['source_values'])
            self.assertEqual(q3['source_values']['listing_symbol'], '500325')
            self.assertEqual(q3['source_values']['underlying_symbol'], 'RELIANCE')
            self.assertEqual(original, {p.relative_to(package): p.read_bytes() for p in package.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
