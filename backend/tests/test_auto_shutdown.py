"""Auto-shutdown state machine (single-process / no-Docker mode)."""

from app.main import AutoShutdownState


def make_state(idle_timeout: float = 90.0) -> AutoShutdownState:
    state = AutoShutdownState(idle_timeout)
    state.last_seen = 1000.0  # deterministic clock
    return state


def test_not_due_before_any_browser_ever_connected():
    state = make_state()
    # No tab has ever opened: only the hard idle fallback may trigger.
    assert state.due(now=1000.0 + 30) is False
    assert state.due(now=1000.0 + 91) is True


def test_open_tab_prevents_shutdown():
    state = make_state()
    state.tab_opened()
    opened_at = state.last_seen
    assert state.due(now=opened_at + 60) is False  # heartbeats keep idle low anyway


def test_closing_last_tab_triggers_after_both_graces():
    state = make_state()
    state.tab_opened()
    state.tab_closed()
    closed_at = state.last_seen
    # Within the refresh grace: not due.
    assert state.due(now=closed_at + 5) is False
    # After tab-close grace AND request idle: due.
    assert state.due(now=closed_at + 21) is True


def test_reopened_tab_cancels_pending_shutdown():
    state = make_state()
    state.tab_opened()
    state.tab_closed()
    closed_at = state.last_seen
    assert state.due(now=closed_at + 5) is False  # grace running
    state.tab_opened()  # refresh completed / tab reopened
    assert state.due(now=closed_at + 60) is False


def test_requests_defer_tab_close_shutdown():
    state = make_state()
    state.tab_opened()
    state.tab_closed()
    closed_at = state.last_seen
    state.last_seen = closed_at + 18  # a straggling request arrives
    assert state.due(now=closed_at + 21) is False  # idle requirement not met


def test_tab_counter_never_goes_negative():
    state = make_state()
    state.tab_closed()
    state.tab_closed()
    assert state.open_tabs == 0


async def test_session_endpoints_are_noops_when_disabled(client):
    assert (await client.post("/api/v1/session/open")).status_code == 204
    assert (await client.post("/api/v1/session/close")).status_code == 204
