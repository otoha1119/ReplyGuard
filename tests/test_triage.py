"""トリアージ採点のテスト（決定的・純関数）."""

from datetime import datetime, timedelta, timezone

from app.domain.triage import compute_triage_score, compute_urgency_score
from app.models import AnalysisResult

from tests.conftest import make_email

NOW = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _analysis(importance: int) -> AnalysisResult:
    return AnalysisResult(importance=importance)


def test_non_negative_float():
    email = make_email(received_at=NOW)
    score = compute_triage_score(email, None, NOW)
    assert isinstance(score, float)
    assert score >= 0.0


def test_unread_outweighs_read_same_conditions():
    unread = make_email(is_unread=True, received_at=NOW)
    read = make_email(is_unread=False, received_at=NOW)
    a = _analysis(3)
    assert compute_triage_score(unread, a, NOW) > compute_triage_score(read, a, NOW)


def test_importance_scales_score():
    email = make_email(received_at=NOW)
    low = compute_triage_score(email, _analysis(1), NOW)
    high = compute_triage_score(email, _analysis(5), NOW)
    assert high > low


def test_default_importance_when_no_analysis():
    email = make_email(received_at=NOW)
    # analysis 無し ⇒ importance=2 と等価.
    assert compute_triage_score(email, None, NOW) == compute_triage_score(
        email, _analysis(2), NOW
    )


def test_age_factor_monotonic_increasing():
    a = _analysis(3)
    fresh = make_email(received_at=NOW)
    old = make_email(received_at=NOW - timedelta(days=7))
    older = make_email(received_at=NOW - timedelta(days=30))
    s_fresh = compute_triage_score(fresh, a, NOW)
    s_old = compute_triage_score(old, a, NOW)
    s_older = compute_triage_score(older, a, NOW)
    assert s_fresh < s_old < s_older or s_old < s_older  # 7日<30日(頭打ち14日)
    assert s_fresh < s_old
    assert s_old <= s_older


def test_age_factor_capped_at_14_days():
    a = _analysis(3)
    at_cap = make_email(received_at=NOW - timedelta(days=14))
    beyond = make_email(received_at=NOW - timedelta(days=100))
    assert compute_triage_score(at_cap, a, NOW) == compute_triage_score(beyond, a, NOW)


def test_fresh_age_factor_is_one():
    a = _analysis(4)
    email = make_email(is_unread=True, received_at=NOW)
    # unread(1.0) * importance(4) * age(1.0) = 4.0
    assert compute_triage_score(email, a, NOW) == 4.0


def test_missing_received_at_treated_as_fresh():
    a = _analysis(4)
    email = make_email(is_unread=True, received_at=None)
    assert compute_triage_score(email, a, NOW) == 4.0


def test_deterministic_repeatable():
    email = make_email(received_at=NOW - timedelta(days=3))
    a = _analysis(2)
    assert compute_triage_score(email, a, NOW) == compute_triage_score(email, a, NOW)


# --- compute_urgency_score ---

def _analysis_with_deadline(deadline: datetime | None) -> AnalysisResult:
    return AnalysisResult(importance=3, deadline=deadline)


def test_urgency_no_analysis_returns_zero():
    assert compute_urgency_score(None, NOW) == 0.0


def test_urgency_no_deadline_returns_zero():
    assert compute_urgency_score(_analysis_with_deadline(None), NOW) == 0.0


def test_urgency_overdue_returns_max():
    past = NOW - timedelta(days=1)
    assert compute_urgency_score(_analysis_with_deadline(past), NOW) == 5.0


def test_urgency_beyond_window_returns_floor():
    far_future = NOW + timedelta(days=31)
    assert compute_urgency_score(_analysis_with_deadline(far_future), NOW) == 0.5


def test_urgency_at_window_boundary_returns_floor():
    at_window = NOW + timedelta(days=30)
    assert compute_urgency_score(_analysis_with_deadline(at_window), NOW) == 0.5


def test_urgency_today_deadline_near_max():
    today = NOW + timedelta(hours=1)
    score = compute_urgency_score(_analysis_with_deadline(today), NOW)
    assert 4.4 < score <= 4.5


def test_urgency_decreases_as_deadline_recedes():
    s1 = compute_urgency_score(_analysis_with_deadline(NOW + timedelta(days=1)), NOW)
    s2 = compute_urgency_score(_analysis_with_deadline(NOW + timedelta(days=7)), NOW)
    s3 = compute_urgency_score(_analysis_with_deadline(NOW + timedelta(days=14)), NOW)
    assert s1 > s2 > s3


def test_urgency_overdue_beats_imminent():
    overdue = NOW - timedelta(days=1)
    imminent = NOW + timedelta(hours=1)
    assert compute_urgency_score(_analysis_with_deadline(overdue), NOW) > \
           compute_urgency_score(_analysis_with_deadline(imminent), NOW)
