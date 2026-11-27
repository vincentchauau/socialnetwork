from api.rally.identity import assign_labels


def person(side: str, x_m: float, y_m: float, score: float = 0.9) -> dict[str, object]:
    return {"side": side, "x_m": x_m, "y_m": y_m, "x": 0.5, "y": 0.5, "score": score}


def test_first_players_are_labelled_by_side() -> None:
    people = [person("far-right", 4, 10), person("near-left", 1, 2), person("near-right", 5, 2)]

    labelled, known = assign_labels({}, people)

    labels = {p["side"]: p["id"] for p in labelled}
    assert labels == {"near-left": 1, "near-right": 2, "far-right": 3}
    assert set(known) == {1, 2, 3}


def test_a_player_keeps_the_label_when_they_move_a_little() -> None:
    _, known = assign_labels({}, [person("near-left", 1, 2), person("far-right", 4, 10)])

    labelled, known = assign_labels(known, [person("far-right", 4.3, 9.6), person("near-left", 1.4, 2.2)])

    labels = {p["side"]: p["id"] for p in labelled}
    assert labels == {"near-left": 1, "far-right": 2}


def test_a_new_person_takes_a_free_label() -> None:
    _, known = assign_labels({}, [person("near-left", 1, 2), person("near-right", 5, 2)])

    labelled, known = assign_labels(known, [person("near-left", 1, 2.1), person("far-left", 1, 11)])

    labels = {p["side"]: p["id"] for p in labelled}
    assert labels["near-left"] == 1
    assert labels["far-left"] == 3
    assert set(known) == {1, 2, 3}


def test_no_more_than_four_players_are_labelled() -> None:
    people = [person("near-left", 1, 2, 0.9), person("near-right", 5, 2, 0.8), person("far-left", 1, 11, 0.7),
              person("far-right", 5, 11, 0.6), person("far-left", 2, 12, 0.3)]

    labelled, _ = assign_labels({}, people)

    assert len(labelled) == 4
    assert sorted(p["id"] for p in labelled) == [1, 2, 3, 4]
    assert all(p["score"] != 0.3 for p in labelled)


def test_a_label_is_not_given_twice_in_one_sample() -> None:
    _, known = assign_labels({}, [person("near-left", 1, 2)])

    labelled, _ = assign_labels(known, [person("near-left", 1, 2), person("near-left", 1.2, 2.2, 0.5)])

    assert sorted(p["id"] for p in labelled) == [1, 2]
