from sqlalchemy.orm import sessionmaker

from api.rally import job
from api.rally.db import Base, make_engine
from api.rally.models import Match


def test_job_without_a_court_marks_the_match_failed() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        match = Match(user_id=1, name="Final", video_name="game.mp4", video_path="missing.mp4", people_status="running")
        db.add(match)
        db.commit()
        match_id = match.id

    job.run_analysis(factory, match_id)

    with factory() as db:
        assert db.get(Match, match_id).people_status == "failed"
    engine.dispose()


def test_job_with_a_missing_video_marks_the_match_failed() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        match = Match(
            user_id=1, name="Final", video_name="game.mp4", video_path="does-not-exist.mp4",
            court_corners="[[0.2,0.8],[0.8,0.8],[0.8,0.2],[0.2,0.2]]", people_status="running",
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
