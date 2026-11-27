from sqlalchemy.orm import sessionmaker

from api.rally import job
from api.rally.db import Base, make_engine
from api.rally.models import Match


def test_job_with_a_missing_video_marks_the_match_failed() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        match = Match(
            user_id=1, name="Final", video_name="game.mp4", video_path="does-not-exist.mp4",
            people_status="running",
        )
        db.add(match)
        db.commit()
        match_id = match.id

    job.run_analysis(factory, match_id)

    with factory() as db:
        match = db.get(Match, match_id)
        assert match.people_status == "failed"
        assert match.people_track is None
    engine.dispose()


def test_a_job_left_running_by_a_restart_is_marked_failed_at_start_up() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        stuck = Match(user_id=1, name="Stuck", video_name="a.mp4", video_path="a.mp4", people_status="running")
        finished = Match(user_id=1, name="Done", video_name="b.mp4", video_path="b.mp4", people_status="done")
        db.add_all([stuck, finished])
        db.commit()
        stuck_id, finished_id = stuck.id, finished.id

    job.fail_stale_jobs(factory)

    with factory() as db:
        assert db.get(Match, stuck_id).people_status == "failed"
        assert db.get(Match, finished_id).people_status == "done"
    engine.dispose()
