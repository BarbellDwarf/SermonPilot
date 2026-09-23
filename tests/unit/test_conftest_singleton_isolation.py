"""Guard the per-test singleton isolation in tests/conftest.py.

The first test leaves the database handle bound under both import paths and
parks a queue object in the global job-queue slot. The second test only
passes when the isolation fixture stopped and cleared both between the two,
so this file fails immediately if the fixture is removed.
"""

from __future__ import annotations

_stopped: list[bool] = []


class _FakeQueue:
    def stop(self) -> None:
        _stopped.append(True)


def test_a_test_may_leave_process_globals_bound():
    import database as bare_database

    import ui.database as database
    import ui.job_queue as job_queue

    database.get_db()
    bare_database.get_db()
    job_queue._job_queue = _FakeQueue()

    assert database._db is not None
    assert bare_database._db is not None
    assert job_queue._job_queue is not None


def test_b_next_test_starts_with_clean_singletons():
    import database as bare_database

    import ui.database as database
    import ui.job_queue as job_queue

    assert database._db is None
    assert bare_database._db is None
    assert job_queue._job_queue is None
    assert _stopped == [True]
