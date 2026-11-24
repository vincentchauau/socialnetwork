import random

import pytest

from api.werewolf.engine import Ability, Faction, Game, GameError, Phase

F, A = Faction, Ability


def make_game(n=9, bots=0, seed=1):
    random.seed(seed)
    entries = [(f"P{i + 1}", i < bots) for i in range(n)]
    return Game(entries)


def setup_roles(game, roles):
    """roles: {pid: (faction, ability)} — ghi đè role trước khi start."""
    for pid, (faction, ability) in roles.items():
        p = game.player(pid)
        p.faction, p.ability = faction, ability


def neutralize(game, keep=(), wolves=2):
    """Mọi người không trong `keep` thành Người thụ động (không có hành động).

    Giữ `wolves` Sói thụ động (id cuối) để game không kết thúc ngay.
    """
    passive_wolves = {p.id for p in game.players[len(game.players) - wolves:]} if wolves else set()
    for p in game.players:
        if p.id in keep:
            continue
        faction = F.WOLF if p.id in passive_wolves else F.VILLAGER
        p.faction, p.ability = faction, A.REVEAL_ON_DEATH


def start_quiet(game, vote=None):
    """Bắt đầu game rồi cho mọi Sói bỏ phiếu trắng ở vote giết ban đêm, trừ các Sói trong `vote` ({pid: mục tiêu})."""
    game.start()
    vote = vote or {}
    for pid in list(game.wolf_options):
        if game.phase == Phase.NIGHT and pid not in game.wolf_actions:
            game.submit(pid, vote.get(pid, 0), "wolf")


def texts(game, pid):
    return [e["text"] for e in game.view_for(pid)["log"]]


def test_requires_min_players():
    with pytest.raises(GameError):
        Game([(f"P{i}", False) for i in range(4)])


@pytest.mark.parametrize("m", range(5, 41))
def test_role_counts_follow_the_hard_limits(m):
    from api.werewolf.engine.roles import role_counts
    c = role_counts(m)
    assert c.wolves == m // 3 and c.holders == m // 3  # Sói = người có chức năng = m/3
    assert c.ghosts == (m // 9 if m >= 12 else 0)  # Ma = m/9, chỉ từ 12 người
    assert c.plain == m - 2 * (m // 3) - c.ghosts  # người thường = phần còn lại
    assert c.wolves + c.holders + c.ghosts + c.plain == m and c.plain > 0


@pytest.mark.parametrize("m", range(5, 41))
def test_faction_counts_are_consistent(m):
    random.seed(m)
    g = Game([(f"P{i}", False) for i in range(m)])
    count = lambda f: sum(p.faction == f for p in g.players)
    assert count(F.WOLF) == m // 3
    assert count(F.GHOST) == (m // 9 if m >= 12 else 0)
    assert count(F.WOLF) + count(F.GHOST) + count(F.VILLAGER) == m
    assert count(F.WOLF) >= 1 and count(F.VILLAGER) >= 1


def test_five_players_have_one_wolf_one_holder_and_three_plain_people():
    from api.werewolf.engine.roles import role_counts
    c = role_counts(5)
    assert (c.wolves, c.holders, c.ghosts, c.plain) == (1, 1, 0, 3)


@pytest.mark.parametrize("m", [5, 9, 12, 20, 40])
def test_generated_roles_match_the_counts_and_groups(m):
    from api.werewolf.engine.roles import ALLOWED_ABILITIES, role_counts, suggest_roles
    c = role_counts(m)
    for seed in range(30):
        random.seed(seed)
        roles = suggest_roles(m)
        wolves = [a for f, a in roles if f == F.WOLF]
        ghosts = [a for f, a in roles if f == F.GHOST]
        villagers = [a for f, a in roles if f == F.VILLAGER]
        assert len(wolves) == c.wolves and len(ghosts) == c.ghosts
        assert all(a in (A.KILL, A.KILL_ON_DEATH) for a in wolves) and A.KILL in wolves  # Sói: chỉ tấn công, có ≥1 chủ động
        assert all(a == A.TRANSFORM for a in ghosts)
        assert sum(a != A.NONE for a in villagers) == c.holders  # người có chức năng = m/3
        assert sum(a == A.NONE for a in villagers) == c.plain  # người thường không có chức năng
        assert all(a in ALLOWED_ABILITIES[F.VILLAGER] for a in villagers)
        holders = [a for a in villagers if a != A.NONE]
        if len(holders) >= 4:  # đủ người thì phe Người có đủ 4 nhóm chức năng
            groups = [{A.KILL, A.KILL_ON_DEATH}, {A.BLOCK_EFFECTS, A.REVERSE_EFFECTS},
                      {A.BLOCK_ABILITY, A.REVERSE_ABILITY}, {A.SEE_FACTION, A.SEE_ABILITY, A.REVEAL_ON_DEATH}]
            assert all(any(a in grp for a in holders) for grp in groups), (m, seed)


def test_plain_people_have_no_night_action_and_still_vote_by_day():
    g = make_game(9)
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.VILLAGER, A.NONE)})
    g.start()
    assert 1 not in g.night_options and 1 not in g.wolf_options
    assert g.view_for(1)["actions"] == []  # chỉ còn vote ban ngày khi sang ngày


def test_small_room_has_no_ghost_abilities():
    g = make_game(9)
    assert all(p.ability != A.TRANSFORM for p in g.players)


def test_ghosts_have_transform_and_wolves_know_each_other():
    g = make_game(20)
    ghosts = [p for p in g.players if p.faction == F.GHOST]
    assert any(p.ability == A.TRANSFORM for p in ghosts)
    wolf = next(p for p in g.players if p.faction == F.WOLF)
    view = g.view_for(wolf.id)
    seen_wolves = {x["id"] for x in view["players"] if x["faction"] and x["faction"]["code"] == "WOLF"}
    assert seen_wolves == {p.id for p in g.players if p.faction == F.WOLF}


def test_view_hides_other_players_roles():
    g = make_game()
    v = g.view_for(1)
    others = [p for p in v["players"] if p["id"] != 1]
    assert all(p["ability"] is None for p in others)
    assert v["me"]["ability"]["code"] == g.player(1).ability.name


def test_all_bot_games_terminate():
    for seed in range(40):
        random.seed(seed)
        g = Game([(f"B{i}", True) for i in range(15)])
        g.start()
        assert g.phase == Phase.OVER
        assert g.winner is not None or not g.alive()  # chỉ được không có phe thắng khi không còn ai sống (hòa)


def test_protect_blocks_kill():
    g = make_game()
    neutralize(g, keep=(1, 2, 3, 4))
    setup_roles(g, {1: (F.WOLF, A.KILL), 2: (F.VILLAGER, A.BLOCK_EFFECTS),
                    3: (F.VILLAGER, A.REVEAL_ON_DEATH), 4: (F.WOLF, A.REVEAL_ON_DEATH)})
    start_quiet(g)
    g.submit(1, 3)
    g.submit(2, 3)
    assert g.player(3).alive
    assert g.phase == Phase.DAY
    assert any("thất bại" in t for t in texts(g, 1))


def test_reverse_effects_kills_attacker():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.KILL), 2: (F.VILLAGER, A.REVERSE_EFFECTS)})
    start_quiet(g)
    g.submit(1, 3)
    g.submit(2, 3)
    assert not g.player(1).alive and g.player(3).alive


def test_block_ability_cancels_action():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.KILL), 2: (F.VILLAGER, A.BLOCK_ABILITY)})
    start_quiet(g)
    g.submit(1, 3)
    g.submit(2, 1)
    assert g.player(3).alive


def test_wolf_vote_tie_kills_nobody():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.REVEAL_ON_DEATH), 2: (F.WOLF, A.REVEAL_ON_DEATH)})
    start_quiet(g, vote={1: 3, 2: 4})
    assert len(g.alive()) == 9


def test_wolf_vote_majority_kills():
    g = make_game()
    neutralize(g, keep=(1, 2, 3))
    setup_roles(g, {i: (F.WOLF, A.REVEAL_ON_DEATH) for i in (1, 2, 3)})
    start_quiet(g, vote={1: 4, 2: 4, 3: 5})
    assert not g.player(4).alive and g.player(5).alive


def test_transform_makes_ghost_and_notifies_target():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.GHOST, A.TRANSFORM)})
    start_quiet(g)
    g.submit(1, 2)
    assert g.player(2).faction == F.GHOST
    assert any("biến thành Ma" in t for t in texts(g, 2))
    assert not any("biến thành Ma" in t for t in texts(g, 5))


def test_see_faction_wolf_is_private_to_wolves_villager_is_public():
    g = make_game()
    neutralize(g, keep=(1, 2, 3))
    setup_roles(g, {1: (F.WOLF, A.SEE_FACTION), 2: (F.WOLF, A.REVEAL_ON_DEATH),
                    3: (F.VILLAGER, A.SEE_FACTION)})
    start_quiet(g)
    g.submit(1, 5)
    g.submit(3, 6)
    log_villager = texts(g, 7)
    log_wolf = texts(g, 2)
    assert any("P6" in t for t in log_villager)  # soi của Người: công khai
    assert not any("P5" in t for t in log_villager)  # soi của Sói: riêng
    assert any("P5" in t for t in log_wolf)


def test_protect_cooldown_excludes_last_target():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.VILLAGER, A.BLOCK_EFFECTS)})
    start_quiet(g)
    g.submit(1, 2)
    for p in g.alive():
        g.submit(p.id, 0)
    assert g.phase == Phase.NIGHT
    assert 2 not in g.night_options[1]


def test_kill_on_death_waits_for_human_choice():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.KILL), 2: (F.VILLAGER, A.KILL_ON_DEATH)})
    start_quiet(g)
    g.submit(1, 2)
    assert g.phase == Phase.REVENGE and g.pending_revenge == 2
    enemy = g.revenge_options[0]
    with pytest.raises(GameError):
        g.submit(3, enemy)
    g.submit(2, enemy)
    assert not g.player(enemy).alive
    assert g.phase == Phase.DAY


def test_day_vote_hangs_majority_and_tie_spares():
    g = make_game()
    neutralize(g)
    start_quiet(g)
    assert g.phase == Phase.DAY
    for p in g.alive():
        g.submit(p.id, 2 if p.id != 2 else 3)
    assert not g.player(2).alive
    assert g.night == 2 and g.phase == Phase.NIGHT  # đêm 2: Sói luôn có vote nên phải chờ họ


def test_day_tie_hangs_nobody():
    g = make_game()
    neutralize(g)
    start_quiet(g)
    votes = {1: 2, 2: 0, 3: 1, 4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2}  # 4 phiếu P1, 4 phiếu P2
    for pid, target in votes.items():
        g.submit(pid, target)
    assert len(g.alive()) == 9
    assert any("Hòa phiếu" in t for t in texts(g, 1))


def test_invalid_actions_rejected():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    start_quiet(g)
    with pytest.raises(GameError):
        g.submit(1, 1)  # tự nhắm
    with pytest.raises(GameError):
        g.submit(2, 3)  # không có hành động
    g.submit(1, 3)
    assert g.phase == Phase.DAY
    g.submit(1, 4)  # vote hợp lệ
    with pytest.raises(GameError):
        g.submit(1, 4)  # vote lần 2
    with pytest.raises(GameError):
        g.submit(2, 3)  # mục tiêu đã chết
    with pytest.raises(GameError):
        g.submit(2, 2)  # tự vote chính mình


def test_force_skips_missing_players():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    start_quiet(g)
    g.force()
    assert g.phase == Phase.DAY and len(g.alive()) == 9
    g.force()
    assert g.phase == Phase.NIGHT


def test_win_when_wolves_eliminated():
    g = make_game()
    neutralize(g, keep=(1, 2), wolves=0)
    setup_roles(g, {1: (F.VILLAGER, A.KILL), 2: (F.WOLF, A.REVEAL_ON_DEATH)})
    start_quiet(g)
    g.submit(1, 2)
    assert g.phase == Phase.OVER and g.winner == F.VILLAGER


def test_game_over_reveals_everything():
    g = make_game()
    neutralize(g, keep=(1, 2), wolves=0)
    setup_roles(g, {1: (F.VILLAGER, A.KILL), 2: (F.WOLF, A.REVEAL_ON_DEATH)})
    start_quiet(g)
    g.submit(1, 2)
    view = g.view_for(5)
    assert all(p["ability"] is not None for p in view["players"])


def test_full_log_shows_every_action_and_vote():
    random.seed(3)
    g = Game([(f"P{i + 1}", False) for i in range(9)])
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    g.player(5).alive = False  # người đã chết xem được nhật ký đầy đủ
    start_quiet(g)
    g.submit(1, 3)
    log = texts(g, 5)  # người chết thấy hành động của P1
    assert any("P1" in t and "→ P3" in t for t in log)
    for p in g.alive():
        g.submit(p.id, 0)
    assert any("vote → bỏ trắng" in t for t in texts(g, 5))


def test_living_players_never_see_other_peoples_night_actions():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    start_quiet(g)
    g.submit(1, 3)
    assert not any("→ P3" in t for t in texts(g, 5))


def test_day_events_are_labelled_as_day():
    g = make_game()
    neutralize(g)
    start_quiet(g)
    for p in g.alive():
        g.submit(p.id, 2 if p.id != 2 else 3)
    hang = next(e for e in g.view_for(1)["log"] if "bị treo cổ" in e["text"] and "chết" in e["text"])
    assert hang["round"].startswith("Ngày")


def test_wolf_vote_tie_is_logged_for_wolves_only():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.REVEAL_ON_DEATH), 2: (F.WOLF, A.REVEAL_ON_DEATH)})
    start_quiet(g, vote={1: 3, 2: 4})
    assert any("hòa phiếu" in t for t in texts(g, 1))
    assert not any("Sói vote" in t for t in texts(g, 5))


def test_full_log_names_the_actor_in_private_notes():
    random.seed(4)
    g = Game([(f"P{i + 1}", False) for i in range(9)])
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.BLOCK_ABILITY), 2: (F.VILLAGER, A.KILL)})
    g.player(5).alive = False
    start_quiet(g)
    g.submit(1, 2)
    g.submit(2, 3)
    outsider = texts(g, 5)
    assert any("P1 khóa chức năng P2" in t for t in outsider)
    assert not any(t.startswith("🚫 Chức năng của bạn") for t in outsider)
    assert any("Bạn khóa chức năng P2" in t for t in texts(g, 1))


def test_full_log_is_only_for_the_dead_and_finished_games():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    g.player(5).alive = False
    start_quiet(g)
    g.submit(1, 3)
    assert g.can_see_everything(5) and not g.can_see_everything(6)
    assert any("(Sói" in t for t in texts(g, 5))
    assert not any("(Sói" in t or "→ P3" in t for t in texts(g, 6))


def test_votes_are_public_and_actor_sees_own_action():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    start_quiet(g)
    g.submit(1, 3)
    assert any("Bạn dùng" in t and "P3" in t for t in texts(g, 1))
    assert not any("Bạn dùng" in t for t in texts(g, 5))  # không lộ hành động đêm của người khác
    for p in g.alive():
        g.submit(p.id, 0 if p.id != 5 else 6)
    assert any("P5 vote → P6" in t for t in texts(g, 7))  # phiếu vote công khai


def test_perspective_shows_only_what_that_player_knows():
    random.seed(2)
    g = Game([(f"P{i + 1}", False) for i in range(9)])
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.BLOCK_ABILITY), 2: (F.VILLAGER, A.KILL)})
    g.player(5).alive = False
    start_quiet(g)
    g.submit(1, 2)
    g.submit(2, 3)
    god = [e["text"] for e in g.view_for(5)["log"]]
    own = [e["text"] for e in g.view_for(1, perspective=True)["log"]]
    other = [e["text"] for e in g.view_for(5, perspective=True)["log"]]
    assert any("P1 (Sói" in t for t in god)  # góc nhìn toàn bộ
    assert any("Bạn dùng" in t for t in own) and any("Bạn khóa" in t for t in own)
    assert not any("khóa" in t or "Bạn dùng" in t for t in other)
    mine = g.view_for(1, perspective=True)["players"]
    assert next(p for p in mine if p["id"] == 4)["ability"] is None  # chưa biết chức năng người khác


def test_preset_roles_are_used_in_order():
    roles = [(F.WOLF, A.KILL), (F.WOLF, A.KILL_ON_DEATH), (F.VILLAGER, A.SEE_FACTION),
             (F.VILLAGER, A.BLOCK_EFFECTS), (F.GHOST, A.TRANSFORM)]
    g = Game([(f"P{i + 1}", False) for i in range(5)], roles=roles)
    assert [(p.faction, p.ability) for p in g.players] == roles


@pytest.mark.parametrize("roles,message", [
    ([(F.GHOST, A.KILL)] + [(F.WOLF, A.KILL)] * 2 + [(F.VILLAGER, A.KILL)] * 2, "không dành cho phe Ma"),
    ([(F.GHOST, A.KILL_ON_DEATH)] + [(F.WOLF, A.KILL)] * 2 + [(F.VILLAGER, A.KILL)] * 2, "không dành cho phe Ma"),
    ([(F.GHOST, A.BLOCK_ABILITY)] + [(F.WOLF, A.KILL)] * 2 + [(F.VILLAGER, A.KILL)] * 2, "không dành cho phe Ma"),
    ([(F.WOLF, A.TRANSFORM)] + [(F.WOLF, A.KILL)] + [(F.VILLAGER, A.KILL)] * 3, "không dành cho phe Sói"),
    ([(F.GHOST, A.SEE_FACTION)] + [(F.WOLF, A.KILL)] * 2 + [(F.VILLAGER, A.KILL)] * 2, "không dành cho phe Ma"),
    ([(F.GHOST, A.BLOCK_EFFECTS)] + [(F.WOLF, A.KILL)] * 2 + [(F.VILLAGER, A.KILL)] * 2, "không dành cho phe Ma"),
    ([(F.WOLF, A.BLOCK_EFFECTS)] + [(F.WOLF, A.KILL)] + [(F.VILLAGER, A.KILL)] * 3, "không dành cho phe Sói"),
    ([(F.WOLF, A.SEE_FACTION)] + [(F.WOLF, A.KILL)] + [(F.VILLAGER, A.KILL)] * 3, "không dành cho phe Sói"),
    ([(F.WOLF, A.REVEAL_ON_DEATH)] + [(F.WOLF, A.KILL)] + [(F.VILLAGER, A.KILL)] * 3, "không dành cho phe Sói"),
    ([(F.VILLAGER, A.TRANSFORM)] + [(F.WOLF, A.KILL)] * 2 + [(F.VILLAGER, A.KILL)] * 2, "không dành cho phe Người"),
    ([(F.VILLAGER, A.KILL)] * 5, "ít nhất 1 Sói"),
    ([(F.WOLF, A.KILL)] * 5, "ít nhất 1 Sói và 1 Người"),
])
def test_invalid_preset_roles_are_rejected(roles, message):
    with pytest.raises(GameError, match=message):
        Game([(f"P{i + 1}", False) for i in range(5)], roles=roles)


def test_suggest_roles_follows_balanced_counts():
    from api.werewolf.engine.roles import faction_counts, suggest_roles
    for m in (5, 9, 12, 20, 40):
        roles = suggest_roles(m)
        assert len(roles) == m
        for faction, count in faction_counts(m):
            assert sum(f == faction for f, _ in roles) == count


def test_wolf_vote_is_a_default_not_an_ability():
    assert not hasattr(A, "WOLF_VOTE")
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.VILLAGER, A.SEE_FACTION)})
    g.start()
    wolves = {p.id for p in g.players if p.faction == F.WOLF}
    assert set(g.wolf_options) == wolves  # mọi Sói có vote đêm, không ai khác có
    assert 1 not in g.wolf_options and 1 in g.night_options


def test_wolf_has_two_night_actions_ability_and_vote():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.SEE_FACTION)})
    g.start()
    kinds = [a["kind"] for a in g.view_for(1)["actions"]]
    assert kinds == ["night", "wolf"]
    assert g.view_for(1)["actions"][1]["canAbstain"] is True
    assert [a["kind"] for a in g.view_for(2)["actions"]] in ([], ["wolf"])  # không có hành động Người


def test_wolf_with_passive_ability_still_votes():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL_ON_DEATH)})
    g.start()
    assert [a["kind"] for a in g.view_for(1)["actions"]] == ["wolf"]


def test_wolf_vote_kills_and_wrong_kind_is_rejected():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.REVEAL_ON_DEATH)})
    g.start()
    with pytest.raises(GameError):
        g.submit(1, 3)  # Sói thụ động không có "chức năng" để dùng
    for pid in list(g.wolf_options):
        g.submit(pid, 3 if pid == 1 else 0, "wolf")
    assert not g.player(3).alive
    with pytest.raises(GameError):
        g.submit(1, 3, "wolf")  # sang phase khác


def test_wolf_cannot_vote_twice_or_with_bad_kind():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.SEE_FACTION)})
    g.start()
    g.submit(1, 3, "wolf")
    with pytest.raises(GameError):
        g.submit(1, 4, "wolf")
    with pytest.raises(GameError):
        g.submit(1, 4, "nope")


def test_reverse_ability_turns_wolf_vote_on_the_voter():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.REVEAL_ON_DEATH), 2: (F.VILLAGER, A.REVERSE_ABILITY)})
    g.start()
    for pid in list(g.wolf_options):
        g.submit(pid, 3 if pid == 1 else 0, "wolf")
    g.submit(2, 1)
    assert not g.player(1).alive and g.player(3).alive  # phiếu của Sói 1 quay về chính họ


def test_block_ability_cancels_wolf_vote():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.REVEAL_ON_DEATH), 2: (F.VILLAGER, A.BLOCK_ABILITY)})
    g.start()
    for pid in list(g.wolf_options):
        g.submit(pid, 3 if pid == 1 else 0, "wolf")
    g.submit(2, 1)
    assert g.player(3).alive and len(g.alive()) == 9


def test_protect_blocks_wolf_vote():
    g = make_game()
    neutralize(g, keep=(1, 2))
    setup_roles(g, {1: (F.WOLF, A.REVEAL_ON_DEATH), 2: (F.VILLAGER, A.BLOCK_EFFECTS)})
    g.start()
    for pid in list(g.wolf_options):
        g.submit(pid, 3 if pid == 1 else 0, "wolf")
    g.submit(2, 3)
    assert g.player(3).alive


def test_random_abilities_stay_inside_each_factions_pool():
    from api.werewolf.engine.roles import ALLOWED_ABILITIES, suggest_roles
    for m in (5, 9, 12, 20, 40):
        for seed in range(25):
            random.seed(seed)
            for faction, ability in suggest_roles(m):
                assert ability in ALLOWED_ABILITIES[faction], (m, faction, ability)


def test_wolf_vote_options_exclude_fellow_wolves_and_self():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.SEE_FACTION)})
    g.start()
    wolves = {p.id for p in g.players if p.faction == F.WOLF}
    for pid, options in g.wolf_options.items():
        assert not wolves & set(options), f"Sói {pid} thấy đồng bọn trong danh sách vote"
        assert options  # vẫn còn người để vote


def test_ghosts_only_transform_and_wolves_only_attack():
    from api.werewolf.engine.roles import suggest_roles
    for m in (12, 20, 40):
        for seed in range(25):
            random.seed(seed)
            for faction, ability in suggest_roles(m):
                if faction == F.GHOST:
                    assert ability == A.TRANSFORM
                elif faction == F.WOLF:
                    assert ability in (A.KILL, A.KILL_ON_DEATH)


def test_villagers_keep_all_four_groups():
    from api.werewolf.engine.roles import ALLOWED_ABILITIES
    assert set(ALLOWED_ABILITIES[F.VILLAGER]) == set(A) - {A.TRANSFORM}


def test_draw_when_nobody_is_alive():
    g = make_game()
    for p in g.players:
        p.alive = False
    assert g.check_win() is True
    assert g.game_over and g.winner is None


def test_games_end_promptly_as_a_draw_when_everyone_dies():
    """Hồi quy: trước đây game chạy tới giới hạn số đêm rồi chọn phe thắng tùy tiện dù không còn ai sống."""
    extinct = 0
    for seed in range(120):
        random.seed(seed)
        g = Game([(f"B{i}", True) for i in range(5)])
        g.start()
        assert g.phase == Phase.OVER
        if not g.alive():
            extinct += 1
            assert g.winner is None, f"seed {seed}: không còn ai sống nhưng có phe thắng"
            assert g.night < g.max_nights, f"seed {seed}: chạy tới giới hạn đêm"
            assert any("HÒA" in e.text for e in g.events)
    assert extinct > 0  # kịch bản này đủ phổ biến để bài test có ý nghĩa


def test_wolf_cannot_vote_the_target_it_already_killed_directly():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    g.start()
    g.submit(1, 3)  # Giết trực tiếp P3
    vote = next(a for a in g.view_for(1)["actions"] if a["kind"] == "wolf")
    assert 3 not in vote["options"] and 4 in vote["options"]  # P3 không còn trong danh sách vote
    with pytest.raises(GameError, match="người khác"):
        g.submit(1, 3, "wolf")
    g.submit(1, 4, "wolf")  # vote người khác thì hợp lệ


def test_wolf_cannot_kill_directly_the_target_it_already_voted_for():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL)})
    g.start()
    g.submit(1, 3, "wolf")
    kill = next(a for a in g.view_for(1)["actions"] if a["kind"] == "night")
    assert 3 not in kill["options"]
    with pytest.raises(GameError, match="người khác"):
        g.submit(1, 3)
    g.submit(1, 4)


def test_exclusion_only_applies_to_wolves_with_direct_kill():
    g = make_game()
    neutralize(g, keep=(1,))
    setup_roles(g, {1: (F.WOLF, A.KILL_ON_DEATH)})
    g.start()
    g.submit(1, 3, "wolf")  # Sói không có Giết trực tiếp: vote tự do
    assert g.wolf_actions[1] == 3


def test_bot_wolves_never_vote_for_their_own_direct_kill_target():
    for seed in range(60):
        random.seed(seed)
        roles = [(F.WOLF, A.KILL)] * 3 + [(F.VILLAGER, A.NONE)] * 6
        g = Game([("Host", False)] + [(f"B{i}", True) for i in range(8)], roles=roles)
        g.start()
        for pid, vote in g.wolf_actions.items():
            if g.player(pid).is_bot and vote:
                assert vote != g.actions[pid], f"seed {seed}: Sói {pid} vote trùng mục tiêu Giết trực tiếp"


def test_wolf_with_direct_kill_gets_no_redundant_vote_when_one_target_is_left():
    g = make_game()
    neutralize(g, keep=(1, 2), wolves=0)
    setup_roles(g, {1: (F.WOLF, A.KILL), 2: (F.VILLAGER, A.NONE)})
    for p in g.players[2:]:
        p.alive = False  # chỉ còn Sói 1 và người 2
    g.start()
    assert 1 not in g.wolf_options  # chỉ còn một mục tiêu: Giết trực tiếp là đủ, không có vote giết thừa
    assert [x["kind"] for x in g.view_for(1)["actions"]] == ["night"]
    g.submit(1, 2)
    assert not g.player(2).alive


def test_wolf_without_direct_kill_still_votes_when_one_target_is_left():
    g = make_game()
    neutralize(g, keep=(1, 2), wolves=0)
    setup_roles(g, {1: (F.WOLF, A.KILL_ON_DEATH), 2: (F.VILLAGER, A.NONE)})
    for p in g.players[2:]:
        p.alive = False
    g.start()
    assert g.wolf_options[1] == [2]  # không có Giết trực tiếp thì vote giết vẫn là cách duy nhất để tấn công


def test_vote_first_never_leaves_the_direct_kill_without_a_target():
    """Hồi quy: vote trước rồi loại mục tiêu khỏi Giết trực tiếp từng có thể để danh sách rỗng (ngõ cụt)."""
    for alive_villagers in (1, 2, 3):
        g = make_game()
        neutralize(g, keep=(1,), wolves=0)
        setup_roles(g, {1: (F.WOLF, A.KILL)})
        for p in g.players[1 + alive_villagers:]:
            p.alive = False
        g.start()
        if 1 in g.wolf_options:  # còn từ 2 mục tiêu: vote một người rồi vẫn phải còn người để Giết trực tiếp
            target = g.wolf_options[1][0]
            g.submit(1, target, "wolf")
            kill = next(a for a in g.view_for(1)["actions"] if a["kind"] == "night")
            assert kill["options"], f"{alive_villagers} người: danh sách Giết trực tiếp rỗng"
            assert target not in kill["options"]
