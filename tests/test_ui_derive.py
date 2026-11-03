"""UI presentation layer — display-level derivations (src/ui/derive.py).

Pure-function tests for the documented, deterministic definitions the UI
uses for derived presentation values. No fixture package is needed: inputs
are the served document shapes (Q1 partitions, Q6 calendar days, Q9 archive
records, canonical rows) exactly as the serving contracts return them.
"""

from __future__ import annotations

import unittest

from ui import derive


def row(date, family, symbol, series, open_v="100.00", close_v="104.00", high="105.00", low="99.00", vol="1000", turn="100000.00", flags=None, line=1, file="w/row.jsonl"):
    """One canonical-row-shaped dict as served by Q2/Q3 (raw_line excluded)."""
    return {
        "business_date": date,
        "format_family": family,
        "source_line_number": line,
        "source_values": {
            "listing_symbol": symbol,
            "series": series,
            "segment": "CM",
            "price_open": open_v,
            "price_high": high,
            "price_low": low,
            "price_close": close_v,
            "traded_quantity": vol,
            "traded_value": turn,
        },
        "flags": flags or [],
        "serving": {"query": "Q3-instrument", "source_file": file, "source_file_family": family, "source_file_year": date[0:4], "symbol": symbol, "series": series},
    }


class ToNumberTests(unittest.TestCase):
    def test_plain_decimal(self):
        self.assertEqual(derive.to_number("1040.00"), 1040.0)
        self.assertEqual(derive.to_number("1200000"), 1200000.0)

    def test_signs(self):
        self.assertEqual(derive.to_number("+5"), 5.0)
        self.assertEqual(derive.to_number("-0.5"), -0.5)

    def test_never_locale_never_default(self):
        self.assertIsNone(derive.to_number("1,234"))
        self.assertIsNone(derive.to_number("1 234"))
        self.assertIsNone(derive.to_number("12.34.56"))
        self.assertIsNone(derive.to_number("1e3"))
        self.assertIsNone(derive.to_number(""))
        self.assertIsNone(derive.to_number(None))
        self.assertIsNone(derive.to_number(5))


class PeriodSummaryTests(unittest.TestCase):
    def test_single_year_documented_semantics(self):
        rows = (
            row("2016-01-04", "legacy13", "A", "EQ", open_v="100.00", close_v="104.00", high="105.00", low="99.00", vol="1000", turn="100000.00"),
            row("2016-01-05", "legacy13", "A", "EQ", open_v="104.50", close_v="101.00", high="106.00", low="98.00", vol="2000", turn="200000.00", line=2),
        )
        s = derive.period_summary(rows)
        self.assertEqual(s["records"], 2)
        self.assertEqual(s["date_min"], "2016-01-04")
        self.assertEqual(s["date_max"], "2016-01-05")
        self.assertTrue(s["single_year"])
        self.assertEqual(s["year"], 2016)
        self.assertEqual(s["open_first"], 100.0)
        self.assertEqual(s["close_last"], 101.0)
        self.assertEqual(s["high"], 106.0)
        self.assertEqual(s["low"], 98.0)
        self.assertEqual(s["volume_total"], 3000.0)
        self.assertEqual(s["volume_count"], 2)
        self.assertEqual(s["turnover_total"], 300000.0)
        self.assertEqual(s["turnover_count"], 2)

    def test_multi_year_labeling(self):
        rows = (row("2016-01-04", "legacy13", "A", "EQ"), row("2017-02-06", "legacy13", "A", "EQ", line=2))
        s = derive.period_summary(rows)
        self.assertFalse(s["single_year"])
        self.assertIsNone(s["year"])
        self.assertEqual(s["date_min"], "2016-01-04")
        self.assertEqual(s["date_max"], "2017-02-06")

    def test_non_numeric_never_zero(self):
        rows = (row("2016-01-04", "legacy13", "A", "EQ", vol="N/A", turn=""),)
        s = derive.period_summary(rows)
        self.assertIsNone(s["volume_total"])
        self.assertEqual(s["volume_count"], 0)
        self.assertIsNone(s["turnover_total"])

    def test_absent_date_never_inferred(self):
        rows = ({},)
        s = derive.period_summary(rows)
        self.assertIsNone(s["date_min"])
        self.assertIsNone(s["date_max"])
        self.assertFalse(s["single_year"])
        self.assertEqual(s["records"], 1)

    def test_served_order_preserved(self):
        # open_first/close_last depend on served order, not on sorting
        rows = (
            row("2016-01-05", "legacy13", "A", "EQ", open_v="200.00", close_v="210.00"),
            row("2016-01-04", "legacy13", "A", "EQ", open_v="100.00", close_v="101.00", line=2),
        )
        s = derive.period_summary(rows)
        self.assertEqual(s["open_first"], 200.0)
        self.assertEqual(s["close_last"], 101.0)


class RowsByYearTests(unittest.TestCase):
    def test_groups_across_families(self):
        partitions = [
            {"family": "legacy13", "year": "2016", "row_files": 1, "row_count": 3, "instrument_pairs": 1},
            {"family": "udiff34", "year": "2016", "row_files": 1, "row_count": 2, "instrument_pairs": 1},
            {"family": "udiff34", "year": "2024", "row_files": 1, "row_count": 4, "instrument_pairs": 1},
        ]
        out = derive.rows_by_year(partitions)
        self.assertEqual(out, [{"year": 2016, "row_count": 5}, {"year": 2024, "row_count": 4}])

    def test_empty(self):
        self.assertEqual(derive.rows_by_year([]), [])
        self.assertEqual(derive.rows_by_year([{"bogus": 1}]), [])


class SegmentCountsTests(unittest.TestCase):
    def test_from_d01_series_counts(self):
        archives = [
            {"member_name": "a.zip", "d01": {"series_counts": {"CM": 700, "FO": 300}}},
            {"member_name": "b.zip", "d01": {"series_counts": {"CM": 100}}},
            {"member_name": "c.zip", "d01": None},
        ]
        out = derive.segment_archive_counts(archives)
        self.assertEqual(
            out,
            [
                {"segment": "CM", "archive_count": 2, "row_count": 800},
                {"segment": "FO", "archive_count": 1, "row_count": 300},
            ],
        )

    def test_no_d01_facts_means_unavailable(self):
        self.assertEqual(derive.segment_archive_counts([{"member_name": "a.zip", "d01": None}]), [])


class CoverageSummaryTests(unittest.TestCase):
    def test_with_calendar(self):
        partitions = [{"family": "legacy13", "year": "2016", "row_files": 1, "row_count": 3, "instrument_pairs": 1}]
        calendar = [{"trade_date": "2016-01-04"}, {"trade_date": "2016-01-05"}]
        archives = [{"d01": {"series_counts": {"CM": 3}}}][0:1]
        out = derive.coverage_summary(partitions, calendar, archives, {"row_count": 3, "instrument_pairs": 1})
        self.assertEqual(out["start_date"], "2016-01-04")
        self.assertEqual(out["end_date"], "2016-01-05")
        self.assertEqual(out["trading_days"], 2)
        self.assertEqual(out["total_archives"], 1)
        self.assertEqual(out["total_rows"], 3)
        self.assertEqual(out["instruments"], 1)
        self.assertEqual(out["exchange_segments"], ["CM"])
        self.assertEqual(out["partition_years"], [2016])

    def test_without_calendar_never_inferred(self):
        out = derive.coverage_summary([{"family": "f", "year": "2016", "row_files": 1, "row_count": 3, "instrument_pairs": 1}], [], [], {"row_count": 3, "instrument_pairs": 1})
        self.assertIsNone(out["start_date"])
        self.assertIsNone(out["end_date"])
        self.assertIsNone(out["trading_days"])
        self.assertIsNone(out["exchange_segments"])


class FlagStatusTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(derive.flag_status([]), {"state": "clean", "text": "no flags"})
        self.assertEqual(derive.flag_status(None), {"state": "clean", "text": "no flags"})

    def test_flagged_sorted_dedup(self):
        out = derive.flag_status([{"name": "b"}, {"name": "a"}, {"name": "a"}])
        self.assertEqual(out, {"state": "flagged", "text": "a, b"})


class PricePointsTests(unittest.TestCase):
    def test_excludes_and_counts(self):
        rows = (
            row("2016-01-04", "legacy13", "A", "EQ", close_v="104.00"),
            row("2016-01-05", "legacy13", "A", "EQ", close_v="N/A", line=2),
            {"business_date": None, "source_values": {"price_close": "1.0"}},
        )
        out = derive.price_points(rows, "price_close")
        self.assertEqual(out["points"], [{"date": "2016-01-04", "value": 104.0}])
        self.assertEqual(out["omitted"], 2)


class LatestYearsTests(unittest.TestCase):
    def test_window(self):
        self.assertEqual(derive.latest_years_params(2024, 5), {"date_from": "2020-01-01", "date_to": "2024-12-31"})
        self.assertEqual(derive.latest_years_params(2024, 1), {"date_from": "2024-01-01", "date_to": "2024-12-31"})

    def test_unavailable(self):
        self.assertIsNone(derive.latest_years_params(None, 5))
        self.assertIsNone(derive.latest_years_params(2024, 7))
        self.assertIsNone(derive.latest_years_params(1001, 3))


class QuickFilterTests(unittest.TestCase):
    def test_q4_presets(self):
        self.assertEqual(derive.quick_filter_params("EQ (all)"), {"mode": "Q4-filter", "params": {"filters": {"series": "EQ"}}})
        self.assertEqual(derive.quick_filter_params("CM segment"), {"mode": "Q4-filter", "params": {"filters": {"segment": "CM"}}})
        self.assertIsNone(derive.quick_filter_params("FO segment"))
        self.assertIsNone(derive.quick_filter_params("Debt"))
        self.assertIsNone(derive.quick_filter_params("Currency"))

    def test_latest_presets(self):
        self.assertEqual(derive.quick_filter_params("Latest 10Y", 2026), {"mode": "Q2-date-range", "params": {"date_from": "2017-01-01", "date_to": "2026-12-31"}})
        self.assertIsNone(derive.quick_filter_params("Latest 10Y", None))

    def test_reliable_only_unavailable(self):
        self.assertIsNone(derive.quick_filter_params("Reliable Only"))

    def test_unknown_unavailable(self):
        self.assertIsNone(derive.quick_filter_params("Everything"))


class DeterminismTests(unittest.TestCase):
    def test_pure_and_stable(self):
        partitions = [{"family": "f", "year": "2016", "row_files": 1, "row_count": 3, "instrument_pairs": 1}]
        archives = [{"d01": {"series_counts": {"CM": 3}}}][0:1]
        rows = (row("2016-01-04", "legacy13", "A", "EQ"),)
        for _ in range(2):
            a = derive.rows_by_year(partitions)
            b = derive.rows_by_year(partitions)
            self.assertEqual(a, b)
            self.assertEqual(derive.segment_archive_counts(archives), derive.segment_archive_counts(archives))
            self.assertEqual(derive.period_summary(rows), derive.period_summary(rows))
            self.assertEqual(derive.price_points(rows, "price_close"), derive.price_points(rows, "price_close"))


if __name__ == "__main__":
    unittest.main()
