"""Serving slice — Q6 calendar query (D16-10 Q6; D23 §18).

All cases run against the synthetic fixture package (tests/serving_fixtures.py)
— never against, and never represented as, the qualified M2 baseline. The
real-package leg is D24_M2_ROOT-gated in tests/test_serving_m2_integration.py.

Fixture Q6 strategy (D36 record §2.8): the base fixture package carries NO
calendar — an engine-derived calendar over the fixture's actual file set would
require fabricated circular evidence for its ~2,000 in-scope missing weekdays
(prohibited; D05 §3.4 "never invent"), so the absent state is the base
package's legitimate Q6 state (the qualified M2 package carries the real
calendar — exercised by the gated leg). The present-state cases are exercised
by test variants (the established D34/D35 pattern) whose calendars are
fixture-declared miniatures in the exact 12-key schema, self-describing, with
fixture-prefixed circular references — never authoritative calendar facts:

* Variant A (present era, 10 weekdays, 2024-02-26…2024-03-08): one present
  day (2024-03-05 — the fixture's real UDiff member; declared a fixture
  circular holiday with file present — the divergence case; trad true); nine
  missing days: two official-holiday (sourced, circular + registry), one
  unexplained-by-obtained-circulars (null label), six not-retrieved.
* Variant B (legacy era, 2016-01-04…2017-02-06): the fixture's three real
  legacy member dates as present days (trad null — legacy N/A; LEGACY
  format); every other weekday missing and not-retrieved (before the
  labelling scope — the engine's own rule).
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import replace

from tests import serving_fixtures
from serving import cli as serving_cli
from serving.archive import query_archive_inventory
from serving.baseline import open_baseline
from serving.detail import query_record_detail
from serving.index import build_index, write_index
from serving.quality import query_data_quality
from serving.query import (
    CALENDAR_FILE,
    CALENDAR_QUERY_ID,
    METRICS_FILE,
    QueryError,
    parse_calendar,
    query_associations,
    query_calendar,
    query_dataset_summary,
    query_date_range,
    query_filters,
    query_instrument,
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
NOT_RETRIEVED_NOTE = "legacy-era gap: cause NOT retrieved and MUST NOT be invented (D05 §3.4)"
UNEXPLAINED_NOTE = "absence not explained by the obtained circulars; kept unresolved (D07-OPEN-8) and never assigned a cause"
PRESENCE_NOTE = (
    "file_present (D01 inventory presence on the date) is the trading-session signal; the annual "
    "circular is a label only and MUST NOT be used to predict file presence (D05 §3.4)"
)


def _day(trade_date, file_present, label_status, label=None, circular=None, registry=None,
         formats=(), members=(), trad=None, notes=()):
    """One fixture-declared CalendarDay in the exact 12-key schema."""
    d = datetime.date.fromisoformat(trade_date)
    return {
        "file_present": file_present,
        "formats_present": list(formats),
        "label_circular": circular,
        "label_registry_id": registry,
        "label_status": label_status,
        "member_names": list(members),
        "missing_weekday": not file_present,
        "notes": list(notes),
        "official_holiday_label": label,
        "trad_dt_eq_biz_dt": trad,
        "trade_date": trade_date,
        "weekday": WEEKDAYS[d.weekday()],
    }


def _variant_a_days():
    return [
        _day("2024-02-26", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]),
        _day("2024-02-27", False, "official-holiday", label="Makar Sankranti (fixture declared)",
             circular="FIX-CIRC-2024-001", registry="FIX-REG-001"),
        _day("2024-02-28", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]),
        _day("2024-02-29", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]),
        _day("2024-03-01", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]),
        _day("2024-03-04", False, "official-holiday", label="official holiday (circular)",
             circular="FIX-CIRC-2024-002", registry="FIX-REG-002"),
        _day("2024-03-05", True, "official-holiday", label="2024-03-05",
             circular="fixture circular holiday with file present (FIX-CIRC-2024-003)",
             formats=["UDIFF"], members=["fix-udf-2024-03-05.csv"], trad=True,
             notes=["fixture: circular holiday with a file present (divergence stored, not reconciled)",
                    PRESENCE_NOTE]),
        _day("2024-03-06", False, "unexplained-by-obtained-circulars", notes=[UNEXPLAINED_NOTE]),
        _day("2024-03-07", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]),
        _day("2024-03-08", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]),
    ]


def _variant_b_days():
    """The fixture's three real legacy member dates as present days; every
    other weekday of the span missing and not-retrieved."""
    file_dates = {
        "2016-01-04": "fix-leg-2016-01-04.csv",
        "2016-01-05": "fix-leg-2016-01-05.csv",
        "2017-02-06": "fix-leg-2017-02-06.csv",
    }
    days = []
    cursor = datetime.date(2016, 1, 4)
    end = datetime.date(2017, 2, 6)
    while cursor <= end:
        if cursor.weekday() <= 4:
            iso = cursor.isoformat()
            if iso in file_dates:
                days.append(_day(iso, True, "not-applicable", formats=["LEGACY"],
                                 members=[file_dates[iso]], notes=[PRESENCE_NOTE]))
            else:
                days.append(_day(iso, False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE]))
        cursor += datetime.timedelta(days=1)
    return days


def _calendar_metrics(days, files):
    present = [d for d in days if d["file_present"]]
    counts = {}
    for d in days:
        counts[d["label_status"]] = counts.get(d["label_status"], 0) + 1
    return {
        "calendar_totals": {
            "days": len(days),
            "files": files,
            "first_date": days[0]["trade_date"],
            "last_date": days[-1]["trade_date"],
            "missing_weekdays": len(days) - len(present),
            "present_days": len(present),
            "span_weekdays": len(days),
            "unresolved_dates": [d["trade_date"] for d in days if d["label_status"] == "unexplained-by-obtained-circulars"],
        },
        "label_status_counts": counts,
    }


class Q6Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d36-serving-calendar-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        self.index = build_index(self.handle)
        self.state = os.path.join(self.root, "state")
        write_index(self.state, self.index)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def package_digests(self, root=None):
        root = root or self.pkg
        digests = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, root).replace(os.sep, "/")
                with open(full, "rb") as handle:
                    digests[relative] = hashlib.sha256(handle.read()).hexdigest()
        return digests

    def copy_variant(self, name):
        variant = os.path.join(self.root, name)
        shutil.copytree(self.pkg, variant)
        return variant

    def resign_package(self, variant: str):
        """Re-sign a variant package after a test-controlled file change."""
        manifest_path = os.path.join(variant, "PACKAGE_MANIFEST.sha256")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")

        def sha(path):
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()

        manifests_dir = os.path.join(variant, "manifests")
        if os.path.isdir(manifests_dir):
            for name in sorted(os.listdir(manifests_dir)):
                if not name.endswith(".sha256"):
                    continue
                full = os.path.join(manifests_dir, name)
                re_signed = []
                with open(full, "r", encoding="utf-8") as handle:
                    for line in handle:
                        digest, relative = line.rstrip("\n").split("  ", 1)
                        re_signed.append(
                            "%s  %s\n" % (sha(os.path.join(variant, relative.replace("/", os.sep))), relative)
                        )
                with open(full, "w", encoding="utf-8", newline="") as handle:
                    handle.write("".join(re_signed))

        entries = []
        total_bytes = 0
        file_count = 0
        for dirpath, dirnames, filenames in os.walk(variant):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, variant).replace(os.sep, "/")
                if relative in ("PACKAGE_MANIFEST.sha256", "RUN_COMPLETE.json"):
                    continue
                total_bytes += os.path.getsize(full)
                file_count += 1
                entries.append("%s  %s" % (sha(full), relative))
        manifest_text = "".join(line + "\n" for line in sorted(entries))
        with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(manifest_text)
        manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        with open(marker_path, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
        marker["package_manifest_sha256"] = manifest_digest
        marker_text = json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n"
        with open(marker_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(marker_text)
        total_bytes += len(manifest_text.encode("utf-8")) + len(marker_text.encode("utf-8"))
        file_count += 2  # manifest + marker (the pinned count includes both)
        spec = replace(
            self.spec,
            manifest_sha256=manifest_digest,
            total_bytes=total_bytes,
            file_count=file_count,
        )
        return open_baseline(variant, spec=spec)

    def calendar_variant(self, name, days, metrics=None, calendar_lines=None, metrics_text=None):
        """A variant package with a test-controlled w2/calendar.jsonl (+
        w2/metrics.json), re-signed and opened. ``calendar_lines`` /
        ``metrics_text`` escape hatches for malformed cases."""
        variant = self.copy_variant(name)
        os.makedirs(os.path.join(variant, "w2"), exist_ok=True)
        if calendar_lines is not None:
            text = "".join(line + "\n" for line in calendar_lines)
        else:
            text = "".join(
                json.dumps(day, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
                for day in days
            )
        with open(os.path.join(variant, "w2", "calendar.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if metrics is not None:
            mtext = metrics if isinstance(metrics, str) else (
                json.dumps(metrics, sort_keys=True, separators=(",", ":")) + "\n"
            )
        else:
            mtext = metrics_text
        if mtext is not None:
            with open(os.path.join(variant, "w2", "metrics.json"), "w", encoding="utf-8", newline="") as handle:
                handle.write(mtext)
        return self.resign_package(variant)

    def variant_a(self, name="pkg-cal-a"):
        days = _variant_a_days()
        return self.calendar_variant(name, days, metrics=_calendar_metrics(days, files=1))

    def variant_b(self, name="pkg-cal-b"):
        days = _variant_b_days()
        return self.calendar_variant(name, days, metrics=_calendar_metrics(days, files=3))

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = serving_cli.main(list(args))
        return code, buf.getvalue()

    def cli_state_for(self, handle, name):
        state = os.path.join(self.root, name)
        write_index(state, build_index(handle))
        return state


class Q6CalendarQueryTests(Q6Base):
    """(1) valid lookup; (2) multiple records; (3) boundaries; (4) sourced
    labels; (5) unexplained; (6) not-retrieved; (7) the distinction; (10)
    null/missing values; (11) ordering."""

    def test_full_calendar_serves_all_days_as_published(self):
        handle = self.variant_a()
        days = query_calendar(handle, self.index)
        self.assertEqual(len(days), 10)
        self.assertEqual(days[0]["trade_date"], "2024-02-26")
        self.assertEqual(days[-1]["trade_date"], "2024-03-08")
        for day in days:
            self.assertEqual(
                sorted(day.keys()),
                ["file_present", "formats_present", "label_circular", "label_registry_id", "label_status",
                 "member_names", "missing_weekday", "notes", "official_holiday_label", "serving",
                 "trad_dt_eq_biz_dt", "trade_date", "weekday"],
            )
            self.assertEqual(day["serving"]["query"], CALENDAR_QUERY_ID)
            self.assertEqual(day["serving"]["source_file"], CALENDAR_FILE)
            self.assertIsNone(day["serving"]["date_from"])
            self.assertIsNone(day["serving"]["date_to"])
        self.assertEqual(days[0]["serving"]["source_line_number"], 1)
        self.assertEqual(days[-1]["serving"]["source_line_number"], 10)

    def test_serving_order_is_file_order_ascending(self):
        handle = self.variant_a()
        days = query_calendar(handle, self.index)
        dates = [d["trade_date"] for d in days]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(set(dates)), len(dates))
        # variant B: the legacy span at scale, still strictly ascending
        handle_b = self.variant_b()
        dates_b = [d["trade_date"] for d in query_calendar(handle_b, self.index)]
        self.assertEqual(dates_b, sorted(dates_b))
        self.assertGreater(len(dates_b), 200)

    def test_range_boundaries_are_inclusive(self):
        handle = self.variant_a()
        days = query_calendar(handle, self.index, date_from="2024-03-04", date_to="2024-03-06")
        self.assertEqual([d["trade_date"] for d in days], ["2024-03-04", "2024-03-05", "2024-03-06"])
        single = query_calendar(handle, self.index, date_from="2024-03-06", date_to="2024-03-06")
        self.assertEqual([d["trade_date"] for d in single], ["2024-03-06"])
        # inverted range: empty, not an error
        self.assertEqual(query_calendar(handle, self.index, date_from="2024-03-08", date_to="2024-03-04"), ())
        # out-of-span bounds: empty
        self.assertEqual(query_calendar(handle, self.index, date_from="2030-01-01", date_to="2030-01-05"), ())
        self.assertEqual(query_calendar(handle, self.index, date_from="2020-01-01", date_to="2020-01-05"), ())
        # a range inside the legacy span
        handle_b = self.variant_b()
        legacy_range = query_calendar(handle_b, self.index, date_from="2016-01-04", date_to="2016-01-07")
        self.assertEqual([d["trade_date"] for d in legacy_range], ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-07"])

    def test_sourced_official_holiday_labels(self):
        handle = self.variant_a()
        by_date = {d["trade_date"]: d for d in query_calendar(handle, self.index)}
        sourced = by_date["2024-02-27"]
        self.assertEqual(sourced["label_status"], "official-holiday")
        self.assertEqual(sourced["official_holiday_label"], "Makar Sankranti (fixture declared)")
        self.assertEqual(sourced["label_circular"], "FIX-CIRC-2024-001")
        self.assertEqual(sourced["label_registry_id"], "FIX-REG-001")
        self.assertFalse(sourced["file_present"])
        # a sourced holiday whose circular record carries no circular reference:
        # label_circular may be null; the label itself must not be
        holiday2 = by_date["2024-03-04"]
        self.assertEqual(holiday2["official_holiday_label"], "official holiday (circular)")

    def test_circular_holiday_with_file_present_divergence(self):
        # the divergence is served as stored: file present AND official-holiday,
        # label = the date, the divergence note carried — never reconciled away
        handle = self.variant_a()
        (present_day,) = query_calendar(handle, self.index, date_from="2024-03-05", date_to="2024-03-05")
        self.assertTrue(present_day["file_present"])
        self.assertEqual(present_day["label_status"], "official-holiday")
        self.assertEqual(present_day["official_holiday_label"], "2024-03-05")
        self.assertTrue(any("divergence" in note for note in present_day["notes"]))
        self.assertEqual(present_day["formats_present"], ["UDIFF"])
        self.assertEqual(present_day["member_names"], ["fix-udf-2024-03-05.csv"])
        self.assertIs(present_day["trad_dt_eq_biz_dt"], True)

    def test_unexplained_state_served_with_null_label(self):
        handle = self.variant_a()
        (day,) = query_calendar(handle, self.index, date_from="2024-03-06", date_to="2024-03-06")
        self.assertEqual(day["label_status"], "unexplained-by-obtained-circulars")
        self.assertIsNone(day["official_holiday_label"])  # the cause is never filled in
        self.assertIsNone(day["label_circular"])
        self.assertIsNone(day["label_registry_id"])
        self.assertFalse(day["file_present"])

    def test_not_retrieved_state_served_with_null_label(self):
        handle = self.variant_a()
        days = [d for d in query_calendar(handle, self.index) if d["label_status"] == "not-retrieved"]
        self.assertEqual(len(days), 6)
        for day in days:
            self.assertIsNone(day["official_holiday_label"])
            self.assertIsNone(day["trad_dt_eq_biz_dt"])
            self.assertFalse(day["file_present"])
        # variant B: the legacy-era scale case, and the legacy present days
        # carry trad_dt_eq_biz_dt null (N/A, never defaulted)
        handle_b = self.variant_b()
        all_days = query_calendar(handle_b, self.index)
        not_retrieved = [d for d in all_days if d["label_status"] == "not-retrieved"]
        present = [d for d in all_days if d["file_present"]]
        self.assertGreater(len(not_retrieved), 200)
        self.assertEqual(len(present), 3)
        for day in present:
            self.assertIsNone(day["trad_dt_eq_biz_dt"])
            self.assertEqual(day["label_status"], "not-applicable")
            self.assertEqual(day["formats_present"], ["LEGACY"])

    def test_unexplained_and_not_retrieved_are_distinct(self):
        handle = self.variant_a()
        days = query_calendar(handle, self.index)
        unexplained = [d for d in days if d["label_status"] == "unexplained-by-obtained-circulars"]
        not_retrieved = [d for d in days if d["label_status"] == "not-retrieved"]
        self.assertEqual([d["trade_date"] for d in unexplained], ["2024-03-06"])
        self.assertEqual(len(not_retrieved), 6)
        self.assertFalse(set(d["trade_date"] for d in unexplained) & set(d["trade_date"] for d in not_retrieved))
        # the states are served exactly as published — never conflated, never
        # relabelled: a re-run serves the identical statuses
        again = query_calendar(handle, self.index)
        self.assertEqual([d["label_status"] for d in again], [d["label_status"] for d in days])

    def test_null_fields_served_as_null_never_defaulted(self):
        handle = self.variant_a()
        days = query_calendar(handle, self.index)
        for day in days:
            for field in ("official_holiday_label", "label_circular", "label_registry_id"):
                value = day[field]
                self.assertTrue(
                    value is None or (isinstance(value, str) and value),
                    "%s must stay null or a non-empty string, got %r" % (field, value),
                )
            # trad_dt_eq_biz_dt is a governed boolean: true (UDiff,
            # corpus-proven) or null (never defaulted to false)
            self.assertIn(day["trad_dt_eq_biz_dt"], (True, None))
            if day["missing_weekday"]:
                self.assertEqual(day["formats_present"], [])
                self.assertEqual(day["member_names"], [])


class Q6AbsentAndMetricsTests(Q6Base):
    """(8) absent files; (12) metrics behavior and consistency."""

    def test_absent_calendar_files_are_a_legitimate_state(self):
        self.assertIsNone(parse_calendar(self.handle))
        self.assertEqual(query_calendar(self.handle, self.index), ())
        self.assertEqual(
            query_calendar(self.handle, self.index, date_from="2024-02-26", date_to="2024-03-08"), ()
        )
        code, out = self.run_cli("query", "--package", self.pkg, "--state", self.state, "--calendar")
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["query"], CALENDAR_QUERY_ID)
        self.assertFalse(envelope["calendar_present"])
        self.assertEqual(envelope["record_count"], 0)
        self.assertEqual(envelope["records"], [])

    def test_metrics_consistency_passes_for_both_variants(self):
        handle_a = self.variant_a()
        self.assertGreater(len(query_calendar(handle_a, self.index)), 0)
        handle_b = self.variant_b()
        self.assertGreater(len(query_calendar(handle_b, self.index)), 0)

    def test_totals_mismatch_fails_closed(self):
        days = _variant_a_days()
        metrics = _calendar_metrics(days, files=1)
        metrics["calendar_totals"]["present_days"] = 2  # contradicts the records
        handle = self.calendar_variant("pkg-badtotals", days, metrics=metrics)
        with self.assertRaises(QueryError) as ctx:
            query_calendar(handle, self.index)
        self.assertEqual(ctx.exception.check, "calendar-metrics")
        self.assertIn("present_days", str(ctx.exception))

    def test_unresolved_dates_mismatch_fails_closed(self):
        days = _variant_a_days()
        metrics = _calendar_metrics(days, files=1)
        metrics["calendar_totals"]["unresolved_dates"] = ["2024-02-26"]
        handle = self.calendar_variant("pkg-badunresolved", days, metrics=metrics)
        with self.assertRaises(QueryError) as ctx:
            query_calendar(handle, self.index)
        self.assertEqual(ctx.exception.check, "calendar-metrics")
        self.assertIn("unresolved_dates", str(ctx.exception))

    def test_label_status_counts_mismatch_fails_closed(self):
        days = _variant_a_days()
        metrics = _calendar_metrics(days, files=1)
        metrics["label_status_counts"]["not-retrieved"] = 5  # contradicts the 6
        handle = self.calendar_variant("pkg-badcounts", days, metrics=metrics)
        with self.assertRaises(QueryError) as ctx:
            query_calendar(handle, self.index)
        self.assertEqual(ctx.exception.check, "calendar-metrics")
        self.assertIn("label_status_counts", str(ctx.exception))

    def test_files_arithmetic_mismatch_fails_closed(self):
        days = _variant_a_days()
        metrics = _calendar_metrics(days, files=1)
        metrics["calendar_totals"]["files"] = 2  # > present, no multi-member day
        handle = self.calendar_variant("pkg-badfiles", days, metrics=metrics)
        with self.assertRaises(QueryError) as ctx:
            query_calendar(handle, self.index)
        self.assertEqual(ctx.exception.check, "calendar-metrics")
        self.assertIn("files", str(ctx.exception))

    def test_calendar_without_metrics_fails_closed(self):
        handle = self.calendar_variant("pkg-no-metrics", _variant_a_days(), metrics=None)
        with self.assertRaises(QueryError) as ctx:
            query_calendar(handle, self.index)
        self.assertEqual(ctx.exception.check, "calendar-metrics")
        self.assertIn(METRICS_FILE, str(ctx.exception))

    def test_metrics_without_calendar_fails_closed(self):
        # a package with w2/metrics.json but no w2/calendar.jsonl: the runner
        # writes both, so the pair inconsistency is detected at the parse
        # boundary (fail closed, no partial output)
        variant = self.copy_variant("pkg-no-calendar")
        os.makedirs(os.path.join(variant, "w2"), exist_ok=True)
        with open(os.path.join(variant, "w2", "metrics.json"), "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(_calendar_metrics(_variant_a_days(), files=1),
                                    sort_keys=True, separators=(",", ":")) + "\n")
        handle = self.resign_package(variant)
        with self.assertRaises(QueryError) as ctx:
            parse_calendar(handle)
        self.assertEqual(ctx.exception.check, "calendar-metrics")
        self.assertIn(CALENDAR_FILE, str(ctx.exception))

    def test_empty_calendar_file_fails_closed(self):
        handle = self.calendar_variant("pkg-empty-cal", None, metrics=None, calendar_lines=[])
        with self.assertRaises(QueryError) as ctx:
            parse_calendar(handle)
        self.assertEqual(ctx.exception.check, "calendar-scan")
        self.assertIn("empty", str(ctx.exception))


class Q6FailClosedTests(Q6Base):
    """(9) malformed records; (10) blank values; (11) duplicates/ordering;
    (13) invalid params; (14) no partial output; (17/18) byte identity."""

    def _expect_scan_error(self, handle, label):
        with self.assertRaises(QueryError) as ctx:
            query_calendar(handle, self.index)
        self.assertEqual(ctx.exception.check, "calendar-scan")
        self.assertIn(label, str(ctx.exception))

    def test_duplicate_trade_date_fails_closed(self):
        days = _variant_a_days()
        handle = self.calendar_variant("pkg-dup", days, metrics=None, calendar_lines=[
            json.dumps(days[0], sort_keys=True),
            json.dumps(days[0], sort_keys=True),
        ])
        self._expect_scan_error(handle, "not strictly ascending")

    def test_non_ascending_order_fails_closed(self):
        days = _variant_a_days()
        swapped = days[1:] + days[:1]
        handle = self.calendar_variant("pkg-order", swapped, metrics=None, calendar_lines=[
            json.dumps(d, sort_keys=True) for d in swapped
        ])
        self._expect_scan_error(handle, "not strictly ascending")

    def test_non_object_line_fails_closed(self):
        # a valid-JSON-but-not-object line: rejected as a non-contract document
        days = _variant_a_days()
        handle = self.calendar_variant("pkg-nonobj", days, metrics=None, calendar_lines=[
            json.dumps(days[0], sort_keys=True), "[1, 2, 3]",
        ])
        self._expect_scan_error(handle, "non-contract key set")

    def test_unparseable_line_fails_closed(self):
        days = _variant_a_days()
        handle = self.calendar_variant("pkg-garbage", days, metrics=None, calendar_lines=[
            json.dumps(days[0], sort_keys=True), "this is not json at all",
        ])
        self._expect_scan_error(handle, "unparseable calendar day")

    def test_wrong_key_set_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[0])
        del broken["notes"]
        handle = self.calendar_variant("pkg-nokey", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "non-contract key set")

    def test_weekend_date_fails_closed(self):
        # 2024-03-09 is a Saturday; the corpus has zero weekend files (D03)
        weekend = _day("2024-03-08", False, "not-retrieved", notes=[NOT_RETRIEVED_NOTE])
        weekend["trade_date"] = "2024-03-09"
        handle = self.calendar_variant("pkg-weekend", _variant_a_days(), metrics=None, calendar_lines=[
            json.dumps(weekend, sort_keys=True),
        ])
        self._expect_scan_error(handle, "weekend date")

    def test_weekday_inconsistency_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[0])
        broken["weekday"] = "Friday"
        handle = self.calendar_variant("pkg-weekday", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "inconsistent with the date")

    def test_missing_weekday_contradiction_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[0])
        broken["missing_weekday"] = True
        broken["file_present"] = True
        handle = self.calendar_variant("pkg-contradict", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "contradicts file_present")

    def test_foreign_label_status_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[0])
        broken["label_status"] = "public-holiday"
        handle = self.calendar_variant("pkg-status", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "outside the governed states")

    def test_unexplained_with_label_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[7])  # the unexplained day
        broken["official_holiday_label"] = "some invented cause"
        handle = self.calendar_variant("pkg-unexplained-label", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "never filled in")

    def test_not_retrieved_with_circular_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[0])
        broken["label_circular"] = "FIX-CIRC-SHOULD-NOT-BE-HERE"
        handle = self.calendar_variant("pkg-retrieved-circ", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "only for official-holiday")

    def test_not_applicable_on_missing_day_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[0])
        broken["label_status"] = "not-applicable"
        handle = self.calendar_variant("pkg-na-missing", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "file-present days")

    def test_blank_label_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[1])  # the sourced official-holiday day
        broken["official_holiday_label"] = ""
        handle = self.calendar_variant("pkg-blank", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "non-empty string")

    def test_false_trad_dt_flag_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[6])  # the present UDiff day
        broken["trad_dt_eq_biz_dt"] = False
        handle = self.calendar_variant("pkg-tradfalse", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "true (UDiff, corpus-proven) or null")

    def test_present_day_without_members_fails_closed(self):
        days = _variant_a_days()
        broken = dict(days[6])
        broken["member_names"] = []
        handle = self.calendar_variant("pkg-nomembers", days, metrics=None, calendar_lines=[
            json.dumps(broken, sort_keys=True),
        ])
        self._expect_scan_error(handle, "must list its formats_present and member_names")

    def test_invalid_selectors_fail_closed(self):
        handle = self.variant_a()
        for kwargs in (
            {"date_from": "2024-03-01"},  # a single bound is not a range
            {"date_to": "2024-03-01"},
            {"date_from": "2024-03-01", "date_to": "03/01/2024"},  # non-ISO
            {"date_from": "2024-13-01", "date_to": "2024-13-02"},  # not a calendar date
            {"date_from": 20240301, "date_to": "2024-03-02"},  # non-string
        ):
            with self.assertRaises(QueryError) as ctx:
                query_calendar(handle, self.index, **kwargs)
            self.assertEqual(ctx.exception.check, "query-input")

    def test_no_partial_output_on_scan_failure(self):
        days = _variant_a_days()
        handle = self.calendar_variant(
            "pkg-midfail", days, metrics=None,
            calendar_lines=[json.dumps(days[0], sort_keys=True), "garbage line"],
        )
        with self.assertRaises(QueryError):
            query_calendar(handle, self.index)
        with self.assertRaises(QueryError):
            query_calendar(handle, self.index, date_from="2024-02-26", date_to="2024-02-26")
        # stateless: a valid variant still serves fully after the failure
        handle_ok = self.variant_a("pkg-ok-after")
        self.assertEqual(len(query_calendar(handle_ok, self.index)), 10)

    def test_package_byte_identity_after_success_and_failure(self):
        before_base = self.package_digests()
        handle = self.variant_a()
        before_variant = self.package_digests(handle.root)
        query_calendar(handle, self.index)
        query_calendar(handle, self.index, date_from="2024-03-04", date_to="2024-03-06")
        bad = self.calendar_variant(
            "pkg-fail-identity", _variant_a_days(), metrics=None,
            calendar_lines=["not json at all"],
        )
        with self.assertRaises(QueryError):
            query_calendar(bad, self.index)
        self.assertEqual(before_base, self.package_digests())
        self.assertEqual(before_variant, self.package_digests(handle.root))


class Q6CliTests(Q6Base):
    """(15) canonical-JSON CLI; (13) CLI usage errors."""

    def test_full_calendar_cli_is_canonical_json(self):
        handle = self.variant_a()
        state = self.cli_state_for(handle, "state-cli-a")
        code, out = self.run_cli("query", "--package", handle.root, "--state", state, "--calendar")
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["query"], CALENDAR_QUERY_ID)
        self.assertIsNone(envelope["date_from"])
        self.assertIsNone(envelope["date_to"])
        self.assertTrue(envelope["calendar_present"])
        self.assertEqual(envelope["record_count"], 10)
        self.assertEqual(envelope["records"][0]["trade_date"], "2024-02-26")
        # canonical JSON: sorted keys, indent 2, deterministic byte-repeat
        self.assertEqual(
            out,
            json.dumps(envelope, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        )
        code2, out2 = self.run_cli("query", "--package", handle.root, "--state", state, "--calendar")
        self.assertEqual(code2, 0)
        self.assertEqual(out, out2)

    def test_range_cli(self):
        handle = self.variant_a()
        state = self.cli_state_for(handle, "state-cli-a2")
        code, out = self.run_cli(
            "query", "--package", handle.root, "--state", state,
            "--calendar", "--from", "2024-03-04", "--to", "2024-03-06",
        )
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["date_from"], "2024-03-04")
        self.assertEqual(envelope["date_to"], "2024-03-06")
        self.assertEqual(envelope["record_count"], 3)
        self.assertEqual(
            [r["trade_date"] for r in envelope["records"]], ["2024-03-04", "2024-03-05", "2024-03-06"]
        )

    def test_absent_calendar_cli_is_empty_success(self):
        code, out = self.run_cli("query", "--package", self.pkg, "--state", self.state, "--calendar")
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertFalse(envelope["calendar_present"])
        self.assertEqual(envelope["record_count"], 0)
        self.assertEqual(envelope["records"], [])

    def test_half_range_is_a_usage_error(self):
        handle = self.variant_a()
        state = self.cli_state_for(handle, "state-cli-a3")
        for args in (("--calendar", "--from", "2024-03-01"), ("--calendar", "--to", "2024-03-01")):
            code, out = self.run_cli("query", "--package", handle.root, "--state", state, *args)
            self.assertEqual(code, 2)
            envelope = json.loads(out)
            self.assertEqual(envelope["result"], "fail")
            self.assertIn("both --from and --to", envelope["detail"])

    def test_modes_remain_mutually_exclusive(self):
        handle = self.variant_a()
        state = self.cli_state_for(handle, "state-cli-a4")
        # Q6 + Q3 positional: two modes
        code, out = self.run_cli("query", "--package", handle.root, "--state", state, "TCS", "EQ", "--calendar")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["result"], "fail")
        # Q6 + Q4: two modes
        code, out = self.run_cli("query", "--package", handle.root, "--state", state, "--calendar", "--field", "series=EQ")
        self.assertEqual(code, 2)
        # Q6 + Q5: two modes
        code, out = self.run_cli("query", "--package", handle.root, "--state", state, "--calendar", "--identity", "INE002A01018")
        self.assertEqual(code, 2)
        # --from/--to without --calendar remain Q2 (unchanged behavior)
        code, out = self.run_cli(
            "query", "--package", handle.root, "--state", state, "--from", "2016-01-04", "--to", "2016-01-05"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["query"], "Q2-date-range")
        # no mode at all: unchanged behavior
        code, out = self.run_cli("query", "--package", self.pkg, "--state", self.state)
        self.assertEqual(code, 2)


class Q6RegressionTests(Q6Base):
    """(16) determinism; (19) Q1–Q10 regression; index impact."""

    def test_deterministic_repeated_queries(self):
        handle = self.variant_a()
        first = query_calendar(handle, self.index)
        second = query_calendar(handle, self.index)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        first_range = query_calendar(handle, self.index, date_from="2024-02-26", date_to="2024-03-01")
        second_range = query_calendar(handle, self.index, date_from="2024-02-26", date_to="2024-03-01")
        self.assertEqual(json.dumps(first_range, sort_keys=True), json.dumps(second_range, sort_keys=True))

    def test_existing_query_contracts_unchanged(self):
        q1_before = query_dataset_summary(self.index)
        q2_before = query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06")
        q3_before = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        q4_before = query_filters(self.handle, self.index, {"series": "EQ"})
        q5_before = query_associations(self.handle, self.index, security_id="INE002A01018")
        q7_before = query_record_detail(
            self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2
        )
        q8_before = query_data_quality(self.handle, self.index)
        q9_before = query_archive_inventory(self.handle)
        query_calendar(self.handle, self.index)
        query_calendar(self.handle, self.index, date_from="2024-02-26", date_to="2024-03-08")
        self.assertEqual(json.dumps(q1_before, sort_keys=True), json.dumps(query_dataset_summary(self.index), sort_keys=True))
        self.assertEqual(json.dumps(q2_before, sort_keys=True), json.dumps(query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06"), sort_keys=True))
        self.assertEqual(json.dumps(q3_before, sort_keys=True), json.dumps(query_instrument(self.handle, self.index, "RELIANCE", "EQ"), sort_keys=True))
        self.assertEqual(json.dumps(q4_before, sort_keys=True), json.dumps(query_filters(self.handle, self.index, {"series": "EQ"}), sort_keys=True))
        self.assertEqual(json.dumps(q5_before, sort_keys=True), json.dumps(query_associations(self.handle, self.index, security_id="INE002A01018"), sort_keys=True))
        self.assertEqual(
            json.dumps(q7_before, sort_keys=True),
            json.dumps(query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2), sort_keys=True),
        )
        self.assertEqual(json.dumps(q8_before, sort_keys=True), json.dumps(query_data_quality(self.handle, self.index), sort_keys=True))
        self.assertEqual(json.dumps(q9_before, sort_keys=True), json.dumps(query_archive_inventory(self.handle), sort_keys=True))

    def test_index_is_unchanged_by_q6(self):
        # Q6 adds no class-(4) state and no index entry: an independent
        # rebuild is byte-identical to the state written in setUp
        document = build_index(self.handle)
        self.assertEqual(json.dumps(document, sort_keys=True), json.dumps(self.index, sort_keys=True))
        self.assertNotIn("w2/calendar.jsonl", document.get("files", {}))
        self.assertNotIn("w2/metrics.json", document.get("files", {}))


if __name__ == "__main__":
    unittest.main()
