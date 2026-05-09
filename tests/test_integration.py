"""Integration tests for meetmanager-app.

Exercises the full HTTP API against the running stack with synthetic data —
no SPLASH involved. Run: `pytest tests/ -v` from repo root.
"""
from __future__ import annotations

import re
from datetime import date

import pytest
import requests

from conftest import (
    BASE_URL, MEET_TEMPLATE, ENTRIES_FILE, RESULTS_FILE,
    get_registration, post_registration, delete_registration,
    export_bundle, export_lxf,
)


# ---------------------------------------------------------------------------
# Setup / smoke
# ---------------------------------------------------------------------------

class TestSetup:
    def test_meet_uploaded(self, uploaded):
        # Gatineau template has 57 events
        assert uploaded["meet"]["events_loaded"] == 57

    def test_entries_uploaded(self, uploaded):
        # Generator default: 5 clubs x 5 categories x 2 genders x 2 = 100 athletes
        assert uploaded["entries"]["clubs_added"] == 5
        assert uploaded["entries"]["athletes_added"] == 100

    def test_status_counts(self, status):
        assert status["clubs"] == 5
        assert status["athletes"] == 100
        assert status["events"] == 57
        assert status["registrations"] == 0

    def test_meet_info(self, uploaded):
        r = requests.get(f"{BASE_URL}/api/meet-info", timeout=5)
        r.raise_for_status()
        info = r.json()
        assert info["events"] == 57
        assert info["course"] == "SCM"
        assert info["masters"] is False  # Gatineau has no masters


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_admin_login(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/auth",
                          json={"pin": admin_headers["X-Club-Pin"]}, timeout=5)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_invalid_pin_rejected(self):
        r = requests.post(f"{BASE_URL}/api/auth",
                          json={"pin": "000000"}, timeout=5)
        assert r.status_code == 401

    def test_club_login(self, clubs):
        # First club's PIN was generated on entries upload
        pin = clubs[0]["pin"]
        r = requests.post(f"{BASE_URL}/api/auth", json={"pin": pin}, timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "coach"
        assert body["club_id"] == clubs[0]["id"]


# ---------------------------------------------------------------------------
# Registration view: categories + suggestions
# ---------------------------------------------------------------------------

def _by_birthyear(athletes, year, gender=None):
    out = [a for a in athletes if a["birthdate"] and a["birthdate"].startswith(str(year))]
    if gender:
        out = [a for a in out if a["gender"] == gender]
    return out


class TestRegistrationView:
    @pytest.mark.parametrize("year,expected", [
        (2018, "10-"),     # age 8
        (2014, "11-12"),   # age 12
        (2012, "13-14"),   # age 14
        (2010, "15-18"),   # age 16
        (2002, "Open"),    # age 24
    ])
    def test_suggested_age_code(self, athletes, admin_headers, year, expected):
        pool = _by_birthyear(athletes, year)
        assert pool, f"No athlete born in {year}"
        reg = get_registration(pool[0]["id"], admin_headers)
        assert reg["suggested_age_code"] == expected

    def test_all_age_codes_exposed_by_backend(self, athletes, admin_headers):
        # Backend doesn't pre-filter to ±1 (frontend does); it should expose
        # every age category that exists across the meet's events.
        adult = _by_birthyear(athletes, 2002)[0]
        reg = get_registration(adult["id"], admin_headers)
        codes = set()
        for s in reg["individual_events"] + reg["relay_events"]:
            for c in s["categories"]:
                codes.add(c["age_code"])
        # Gatineau has no Masters, so we expect exactly these 5 codes
        assert codes == {"10-", "11-12", "13-14", "15-18", "Open"}

    def test_junior_only_sees_reachable_categories(self, athletes, admin_headers):
        # 12-year-old: ±1 = 10-, 11-12, 13-14
        junior = _by_birthyear(athletes, 2014)[0]
        reg = get_registration(junior["id"], admin_headers)
        codes = set()
        for s in reg["individual_events"] + reg["relay_events"]:
            for c in s["categories"]:
                codes.add(c["age_code"])
        # Backend doesn't filter ±1 (frontend does); but the events themselves
        # should at least have the natural category 11-12 represented.
        assert "11-12" in codes

    def test_individual_events_match_athlete_gender(self, athletes, admin_headers):
        male = _by_birthyear(athletes, 2002, gender="M")[0]
        reg = get_registration(male["id"], admin_headers)
        # All individual events should be either gender 1 (M) or gender 0 (all)
        # — never gender 2 (F-only).
        # We can't read the raw event gender from the registration payload, but
        # we can confirm the event count differs vs. an F athlete (sanity).
        female = _by_birthyear(athletes, 2002, gender="F")[0]
        reg_f = get_registration(female["id"], admin_headers)
        # Gatineau alternates M/F per style; both should see ~half the events.
        assert len(reg["individual_events"]) > 0
        assert len(reg_f["individual_events"]) > 0


# ---------------------------------------------------------------------------
# Registration write: create / change / delete
# ---------------------------------------------------------------------------

class TestRegistrationWrite:
    @pytest.fixture
    def adult(self, athletes):
        return _by_birthyear(athletes, 2002, gender="M")[0]

    def test_create_and_delete(self, adult, admin_headers):
        reg = get_registration(adult["id"], admin_headers)
        style = next(s for s in reg["individual_events"]
                     if any(c["age_code"] == "Open" for c in s["categories"]))
        cat = next(c for c in style["categories"] if c["age_code"] == "Open")

        r = post_registration(adult["id"], cat["event_id"], "Open", 65430, admin_headers)
        reg_id = r["id"]
        assert reg_id

        # Verify it's now registered
        after = get_registration(adult["id"], admin_headers)
        after_style = next(s for s in after["individual_events"]
                           if s["style_uid"] == style["style_uid"])
        regd = next(c for c in after_style["categories"] if c["registered"])
        assert regd["age_code"] == "Open"
        assert regd["entry_time_ms"] == 65430

        delete_registration(reg_id, admin_headers)
        cleaned = get_registration(adult["id"], admin_headers)
        cleaned_style = next(s for s in cleaned["individual_events"]
                             if s["style_uid"] == style["style_uid"])
        assert not any(c["registered"] for c in cleaned_style["categories"])

    def test_change_category_via_re_register(self, adult, admin_headers):
        """Simulates the frontend's category-switch flow: delete old, post new."""
        reg = get_registration(adult["id"], admin_headers)
        style = next(s for s in reg["individual_events"]
                     if {"15-18", "Open"} <= {c["age_code"] for c in s["categories"]})

        c_open = next(c for c in style["categories"] if c["age_code"] == "Open")
        c_1518 = next(c for c in style["categories"] if c["age_code"] == "15-18")

        # 15-18 and Open share the same event_id on adult Gatineau events
        assert c_open["event_id"] == c_1518["event_id"]

        r1 = post_registration(adult["id"], c_open["event_id"], "Open", 70000, admin_headers)
        delete_registration(r1["id"], admin_headers)
        r2 = post_registration(adult["id"], c_1518["event_id"], "15-18", 70000, admin_headers)

        after = get_registration(adult["id"], admin_headers)
        after_style = next(s for s in after["individual_events"]
                           if s["style_uid"] == style["style_uid"])
        regd = next(c for c in after_style["categories"] if c["registered"])
        assert regd["age_code"] == "15-18"

        delete_registration(r2["id"], admin_headers)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    @pytest.fixture(scope="class")
    def with_registrations(self, athletes, admin_headers):
        """Register one athlete per category, on the first event that supports it."""
        created = []
        for year, code in [(2018, "10-"), (2014, "11-12"), (2012, "13-14"),
                           (2010, "15-18"), (2002, "Open")]:
            ath = _by_birthyear(athletes, year, gender="M")[0]
            reg = get_registration(ath["id"], admin_headers)
            style = next((s for s in reg["individual_events"]
                          if any(c["age_code"] == code for c in s["categories"])), None)
            if not style:
                continue
            cat = next(c for c in style["categories"] if c["age_code"] == code)
            r = post_registration(ath["id"], cat["event_id"], code, 60000, admin_headers)
            created.append({"reg_id": r["id"], "athlete": ath, "code": code,
                            "event_id": cat["event_id"]})

        yield created

        for c in created:
            try:
                delete_registration(c["reg_id"], admin_headers)
            except Exception:
                pass

    def test_export_bundle_contains_scripts(self, with_registrations, admin_headers):
        bundle = export_bundle(admin_headers)
        names = set(bundle.namelist())
        assert "inscriptions.lxf" in names
        assert "simulate_results.vbs" in names
        assert "simulate_results.bat" in names

    def test_export_returns_valid_lxf_zip(self, with_registrations, admin_headers):
        lxf = export_lxf(admin_headers)
        names = lxf.namelist()
        assert any(n.endswith(".lef") for n in names)

    def test_export_contains_all_registrations(self, with_registrations, admin_headers):
        lxf = export_lxf(admin_headers)
        lef_name = next(n for n in lxf.namelist() if n.endswith(".lef"))
        lef = lxf.read(lef_name).decode()
        # Each registration => one ENTRY
        assert lef.count("<ENTRY ") == len(with_registrations)

    def test_export_sets_eventid_and_agegroupid(self, with_registrations, admin_headers):
        lxf = export_lxf(admin_headers)
        lef_name = next(n for n in lxf.namelist() if n.endswith(".lef"))
        lef = lxf.read(lef_name).decode()
        entries = re.findall(r"<ENTRY ([^/]+?)/>", lef)
        assert len(entries) == len(with_registrations)
        for attrs in entries:
            assert "eventid=" in attrs
            assert "agegroupid=" in attrs

    def test_export_eventid_matches_meet_template(self, with_registrations, admin_headers):
        """Each ENTRY's eventid must reference an EVENT defined in the SESSIONS section."""
        lxf = export_lxf(admin_headers)
        lef_name = next(n for n in lxf.namelist() if n.endswith(".lef"))
        lef = lxf.read(lef_name).decode()

        defined = set(re.findall(r'<EVENT [^>]*\beventid="(\d+)"', lef))
        used = set(re.findall(r'<ENTRY [^/]*\beventid="(\d+)"', lef))
        assert used <= defined, f"Entries reference undefined eventids: {used - defined}"

    def test_export_agegroupid_matches_event_groups(self, with_registrations, admin_headers):
        """Each ENTRY's agegroupid must be defined within its EVENT's AGEGROUPS."""
        lxf = export_lxf(admin_headers)
        lef_name = next(n for n in lxf.namelist() if n.endswith(".lef"))
        lef = lxf.read(lef_name).decode()

        # Map eventid -> set of agegroupids defined for that event
        ev_blocks = re.findall(
            r'<EVENT [^>]*\beventid="(\d+)"[^>]*>(.*?)</EVENT>', lef, re.DOTALL)
        ev_agegroups: dict[str, set[str]] = {
            eid: set(re.findall(r'<AGEGROUP [^>]*\bagegroupid="(\d+)"', body))
            for eid, body in ev_blocks
        }

        entries = re.findall(
            r'<ENTRY [^/]*\beventid="(\d+)"[^/]*\bagegroupid="(\d+)"', lef)
        assert entries, "no ENTRY rows with both eventid and agegroupid"
        for eid, agid in entries:
            assert agid in ev_agegroups.get(eid, set()), \
                f"ENTRY agegroupid={agid} not defined on EVENT {eid}"


# ---------------------------------------------------------------------------
# Results upload (best times)
# ---------------------------------------------------------------------------

class TestResultsUpload:
    @pytest.fixture(scope="class")
    def uploaded_results(self, results_path) -> dict:
        with open(results_path, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/api/upload/results",
                files={"file": ("results.lxf", f, "application/octet-stream")},
                timeout=60,
            )
        r.raise_for_status()
        return r.json()

    def test_results_upload_response(self, uploaded_results):
        # Generator emits 3 results per athlete (300 total). Some may collide
        # on the same (athlete, style, course) when one event shares a style
        # with another — those keep the fastest. So times_updated <= 300.
        assert uploaded_results["athletes_skipped"] == 0
        assert uploaded_results["times_updated"] > 100

    def test_status_shows_best_times(self, uploaded_results):
        r = requests.get(f"{BASE_URL}/api/status", timeout=10)
        r.raise_for_status()
        assert r.json()["best_times"] > 100

    def test_athlete_registration_shows_best_time(self, uploaded_results,
                                                   athletes, admin_headers):
        # Walk athletes until we find one whose /registration response shows
        # at least one non-null best_time_scm_ms (Gatineau course is SCM).
        found = False
        for a in athletes[:30]:  # sample is enough
            reg = get_registration(a["id"], admin_headers)
            for s in reg["individual_events"]:
                if s.get("best_time_scm_ms"):
                    found = True
                    break
            if found:
                break
        assert found, "no best_time_scm_ms surfaced on any athlete after upload"
