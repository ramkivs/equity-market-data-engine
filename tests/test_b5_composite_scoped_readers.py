"""Composite Q6/Q8/Q9 evidence and request snapshot tests."""
import unittest
from pathlib import Path
from unittest import mock

from tests import test_b5_catalog_publication as catalog_tests
from serving.incremental_publication import active_snapshot, publish
from serving.incremental_staging import prepare
from serving.saved import execute_query_definition
from serving.query import QueryError


class ScopedCompositeReaderTests(unittest.TestCase):
    setUp = catalog_tests.CatalogPublicationTests.setUp
    tearDown = catalog_tests.CatalogPublicationTests.tearDown
    stage = catalog_tests.CatalogPublicationTests.stage
    init = catalog_tests.CatalogPublicationTests.init
    next_delta = catalog_tests.CatalogPublicationTests.next_delta
    def test_scoped_readers_and_snapshot(self):
        self.init(); first = publish(*self.args)
        old = active_snapshot(self.baseline, self.args[1], self.args[2])
        def query(mode, snapshot=None, params=None):
            return execute_query_definition(mode, params or {}, self.baseline, self.args[2], composite=snapshot)
        q6 = query('Q6-calendar', old, {'date_from':'2016-01-05','date_to':'2016-01-07'})
        self.assertEqual([(x['trade_date'], x['file_present']) for x in q6['records']], [('2016-01-05', True), ('2016-01-06', True), ('2016-01-07', False)])
        self.assertEqual(q6['records'][2]['label_status'], 'not-retrieved')
        q8 = query('Q8-data-quality', old)
        self.assertEqual(q8['flag_census'], old[1]['flag_census'])
        self.assertEqual(q8['reconciliation']['scope'], 'original-baseline-only')
        self.assertEqual(q8['unresolved']['incremental_availability'], 'not-published')
        q9 = query('Q9-archive-inventory', old)
        delta = [r for r in q9['archives'] if r['source_scope'].startswith('incremental')]
        self.assertEqual(len(delta), 1)
        self.assertIsNone(delta[0]['d01']); self.assertIsNone(delta[0]['archive_sha256_d01'])
        self.assertEqual(delta[0]['archive_sha256_observed_raw_bytes'], old[0].payload['candidates'][0]['digest'])
        self.assertIsNone(q9['summary']['archive_set_digest'])
        self.assertTrue(q9['summary']['baseline_archive_set_digest'])
        # A conflict is visible to a newly pinned request, but not an earlier one.
        name = 'fix-leg-2016-01-04.csv'
        Path(self.args[5]['LEGACY'], name).write_bytes(b'changed')
        self.assertEqual(prepare(*self.args, 'LEGACY', name, '2016-01-04', 'conflict')['status'], 'CHANGED-CONFLICT-UNRESOLVED')
        self.assertEqual(query('Q8-data-quality', old)['changed']['record_count'], 0)
        self.assertEqual(query('Q8-data-quality')['changed']['record_count'], 1)
        self.next_delta(); publish(*self.args)
        self.assertEqual(query('Q9-archive-inventory', old)['summary']['composite_generation'], first['generation'])
        new = query('Q6-calendar', params={'date_from':'2025-03-05','date_to':'2025-03-06'})
        self.assertEqual(new['records'][0]['label_status'], 'not-retrieved')
        self.assertTrue(new['records'][1]['file_present'])
        self.assertTrue(new['records'][1]['trad_dt_eq_biz_dt'])
        self.assertEqual(len(query('Q9-archive-inventory')['archives']), len(q9['archives']) + 1)

    def test_existing_calendar_holiday_and_unknown_retained(self):
        self.init(); publish(*self.args)
        selected = active_snapshot(self.baseline, self.args[1], self.args[2])
        def day(date, weekday, label, name=None):
            return {'trade_date':date,'weekday':weekday,'file_present':False,'missing_weekday':True,
                    'formats_present':[],'member_names':[], 'label_status':label,
                    'official_holiday_label':name,'label_circular':None,'label_registry_id':None,
                    'notes':['original note'],'trad_dt_eq_biz_dt':None}
        original = [(1, day('2016-01-05','Tuesday','not-retrieved')),
                    (2, day('2016-01-06','Wednesday','official-holiday','Holiday'))]
        with mock.patch('serving.composite_readers.parse_calendar', return_value=original), \
             mock.patch('serving.composite_readers._load_calendar_metrics'), \
             mock.patch('serving.composite_readers._cross_check_calendar'):
            result = execute_query_definition('Q6-calendar', {}, self.baseline, self.args[2], composite=selected)
        before, overlay = result['records'][:2]
        self.assertEqual(before['label_status'], 'not-retrieved')
        self.assertTrue(overlay['file_present'])
        self.assertEqual(overlay['official_holiday_label'], 'Holiday')
        self.assertEqual(overlay['label_status'], 'official-holiday')
        self.assertFalse(overlay['serving']['baseline_calendar_status']['file_present'])
        self.assertIn('original note', overlay['notes'])
