"""The platform account (system) is not found as a person by the chat (moved here from the shared tests)."""

import pytest
from sqlalchemy.orm import sessionmaker

from api.chat.social import models as social_models, service
from sn_shared.db import make_engine
from sn_shared.directory import ensure_table_for_sqlite
from sn_shared.testing import add_person


@pytest.fixture
def factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'directory.db'}")
    ensure_table_for_sqlite(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_the_platform_account_is_not_found_as_a_person(factory):
    social_models.ensure_tables(factory.kw["bind"])

    add_person(factory, -1, "system", kind="system")
    add_person(factory, 1, "alice")
    with factory() as db:
        assert service.person_by_name(db, "system") is None
        assert service.person_by_name(db, "ALICE").user_id == 1
