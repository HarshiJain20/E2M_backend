from datetime import datetime, timedelta, timezone

from app.services.pipeline import RUNNING_JOBS, is_interrupted

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def job(status="running", minutes_ago=5, job_id="j1"):
    started = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {"id": job_id, "status": status, "created_at": started, "started_at": started}


def test_stale_active_job_is_interrupted():
    assert is_interrupted(job(minutes_ago=5), NOW)


def test_recent_job_is_given_time():
    assert not is_interrupted(job(minutes_ago=1), NOW)


def test_finished_job_is_never_interrupted():
    assert not is_interrupted(job(status="succeeded"), NOW)


def test_job_running_in_this_process_is_not_interrupted():
    RUNNING_JOBS.add("j9")
    try:
        assert not is_interrupted(job(job_id="j9", minutes_ago=30), NOW)
    finally:
        RUNNING_JOBS.discard("j9")
