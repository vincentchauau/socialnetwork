from pathlib import Path

from sqlalchemy.orm import sessionmaker

from api.rally import account_events
from api.rally.db import Base, make_engine
from api.rally.models import Match, Rally


def test_deleting_a_user_removes_matches_rallies_and_files(tmp_path: Path) -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    video = tmp_path / "game.mp4"
    video.write_bytes(b"x")
    with sessionmaker(engine, expire_on_commit=False)() as db:
        match = Match(user_id=7, name="Final", video_name="game.mp4", video_path=str(video))
        db.add(match)
        db.flush()
        db.add(Rally(match_id=match.id, number=1, start_ms=0, end_ms=100, hits=1, winner="A"))
        db.commit()

        account_events.on_user_deleted(db, 7)
        db.commit()

        assert db.query(Match).count() == 0
        assert db.query(Rally).count() == 0
    assert not video.exists()
    engine.dispose()


def test_deleting_an_unknown_user_is_harmless() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        account_events.on_user_deleted(db, 999)
    engine.dispose()
