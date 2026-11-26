"""Tính năng 'vui hơn': thẻ sự kiện, thẻ Bình minh/Hoàng hôn, chat, đồng hồ, bot thông minh, chơi lại."""
import random

import pytest

from api.werewolf.engine import Ability, Faction, Game, GameError, Phase, bots, events

F, A = Faction, Ability


def game_of(n=7, bot_count=0, **kw):
    random.seed(3)
    g = Game([(f"P{i + 1}", i < bot_count) for i in range(n)], **kw)
    return g


def roles(g, mapping):
    for pid, (f, a) in mapping.items():
        p = g.player(pid)
        p.faction, p.ability = f, a
    for p in g.players:
        if p.id not in mapping:
            p.faction, p.ability = F.VILLAGER, A.NONE


def quiet_night(g):
    """Mọi Sói bỏ phiếu trắng."""
    for pid in list(g.wolf_options):
        if g.phase == Phase.NIGHT and pid not in g.wolf_actions:
            g.submit(pid, 0, "wolf")


# ---------- thẻ sự kiện ----------
def test_events_are_off_by_default():
    g = game_of()
    g.start()
    assert g.event is None and g.view_for(1)["event"] is None


def test_forced_event_is_announced_and_visible():
    g = game_of(events=True)
    g.forced_event = events.FOG
    g.start()
    assert g.view_for(1)["event"]["code"] == "FOG"
    assert any("Sương mù" in e["text"] for e in g.view_for(1)["log"])


def test_draw_event_respects_chance(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.99)
    assert events.draw_event() is None
    monkeypatch.setattr(random, "random", lambda: 0.0)
    assert events.draw_event() in events.ALL_EVENTS


def test_fog_hides_seer_result():
    g = game_of()
    roles(g, {1: (F.VILLAGER, A.SEE_FACTION), 6: (F.WOLF, A.KILL), 7: (F.WOLF, A.KILL)})
    g.forced_event = events.FOG
    g.start()
    g.submit(1, 6)
    quiet_night(g)
    g.force()
    assert not any("thuộc nhóm" in e["text"] for e in g.view_for(1)["log"])
    assert any("Sương mù che mắt" in e["text"] for e in g.view_for(1)["log"])


def test_peaceful_night_ignores_wolf_votes():
    g = game_of()
    roles(g, {6: (F.WOLF, A.KILL), 7: (F.WOLF, A.KILL)})
    g.forced_event = events.PEACEFUL
    g.start()
    for pid in (6, 7):
        if pid in g.wolf_options:
            g.submit(pid, 1, "wolf")
    g.force()
    assert g.player(1).alive


def test_without_event_wolf_vote_kills():
    g = game_of()
    roles(g, {6: (F.WOLF, A.KILL), 7: (F.WOLF, A.KILL)})
    g.start()
    for pid in (6, 7):
        if pid in g.wolf_options:
            g.submit(pid, 1, "wolf")
    g.force()
    assert not g.player(1).alive


def test_full_moon_cancels_protection():
    g = game_of()
    roles(g, {1: (F.VILLAGER, A.BLOCK_EFFECTS), 6: (F.WOLF, A.KILL), 7: (F.WOLF, A.KILL)})
    g.forced_event = events.FULL_MOON
    g.start()
    g.submit(1, 2)
    g.submit(6, 2)
    quiet_night(g)
    g.force()
    assert not g.player(2).alive


def test_blood_moon_breaks_ties_randomly():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.forced_event = events.BLOOD_MOON
    g.start()
    g.submit(6, 1, "wolf")
    g.submit(7, 2, "wolf")
    g.force()
    assert sum(not g.player(i).alive for i in (1, 2)) == 1


def test_justice_day_resolves_a_tie():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.forced_event = events.JUSTICE
    g.start()
    quiet_night(g)
    assert g.phase == Phase.DAY and g.view_for(1)["event"]["code"] == "JUSTICE"
    g.submit(1, 2)
    g.submit(2, 1)
    g.force()  # những người còn lại bỏ trắng → 1-1 hòa phiếu
    assert sum(not g.player(i).alive for i in (1, 2)) == 1


# ---------- thẻ Bình minh / Hoàng hôn ----------
def test_dawn_recap_lists_night_deaths():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.submit(6, 1, "wolf")
    g.submit(7, 1, "wolf")
    r = g.view_for(2)["recap"]
    assert r["kind"] == "dawn" and [d["id"] for d in r["deaths"]] == [1]


def test_dusk_recap_after_hanging_and_seq_increases():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    quiet_night(g)
    first = g.view_for(1)["recap"]
    assert first["kind"] == "dawn" and first["deaths"] == []
    for pid in (1, 2, 3, 4):
        g.submit(pid, 5)  # 4 phiếu treo người 5, còn lại bỏ trắng
    g.force()
    assert not g.player(5).alive
    recap = g.view_for(1)["recap"]  # treo cổ xong là sang đêm 2: thẻ Hoàng hôn
    assert recap["seq"] > first["seq"] and recap["kind"] == "dusk" and recap["deaths"][0]["id"] == 5


def test_recap_reveals_identity_of_reveal_on_death():
    g = game_of()
    roles(g, {1: (F.VILLAGER, A.REVEAL_ON_DEATH), 6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.submit(6, 1, "wolf")
    g.submit(7, 1, "wolf")
    assert g.view_for(2)["recap"]["deaths"][0]["revealed"]["faction"]["code"] == "VILLAGER"


# ---------- chat ----------
def test_chat_channels_follow_the_phase():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    assert g.view_for(6)["chatChannel"] == "wolf" and g.view_for(1)["chatChannel"] is None
    with pytest.raises(GameError):
        g.post_chat(1, "xin chào", now=10)
    g.post_chat(6, "đêm nay giết ai?", now=10)
    assert [m["text"] for m in g.view_for(7)["chat"]] == ["đêm nay giết ai?"]
    assert g.view_for(1)["chat"] == []  # người thường không đọc được kênh Sói


def test_day_chat_is_public_and_throttled():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    quiet_night(g)
    g.post_chat(1, "chào cả nhà", now=100)
    with pytest.raises(GameError):
        g.post_chat(1, "lại nữa", now=100.1)
    g.post_chat(1, "ok", now=102)
    assert [m["text"] for m in g.view_for(5)["chat"]] == ["chào cả nhà", "ok"]


def test_dead_chat_is_private_to_the_dead():
    g = game_of(dead_talk=False)
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.submit(6, 1, "wolf")
    g.submit(7, 1, "wolf")
    g.force()
    assert g.view_for(1)["chatChannel"] == "dead"
    g.post_chat(1, "tôi chết rồi", now=1)
    assert any(m["channel"] == "dead" for m in g.view_for(1)["chat"])
    assert not any(m["channel"] == "dead" for m in g.view_for(2)["chat"])


def test_chat_validation():
    g = game_of()
    g.start()
    for bad in ("", "   ", "x" * 200):
        with pytest.raises(GameError):
            g.post_chat(6, bad, now=1)
    with pytest.raises(GameError):
        g.post_chat(6, "hi", target=99, now=2)


def test_chat_seq_survives_trimming():
    from api.werewolf.engine.chat import KEEP, Chat
    c = Chat()
    for i in range(KEEP + 20):
        c.add(1, "public", "x", "Ngày 1", throttle=False)
    seqs = [m.seq for m in c.messages]
    assert len(seqs) == KEEP and len(set(seqs)) == KEEP and seqs == sorted(seqs)


# ---------- đồng hồ ----------
def test_timer_validation():
    for bad in (1, 9999):
        with pytest.raises(GameError):
            game_of(timer=bad)


def test_no_timer_means_no_limit():
    g = game_of()
    g.start()
    assert g.seconds_left() is None and g.view_for(1)["timer"] is None and not g.tick()


def test_timer_counts_down_and_forces_phase():
    g = game_of(timer=30)
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    assert g.seconds_left(now=100) == 30
    assert g.seconds_left(now=110) == 20
    assert not g.tick(now=120)
    assert g.tick(now=131) and g.phase == Phase.DAY  # đêm hết giờ → sang ngày
    assert g.seconds_left(now=200) == 60  # ban ngày gấp đôi, bắt đầu đếm lại
    assert g.tick(now=261) and g.night == 2


# ---------- bot thông minh ----------
def test_bots_chat_in_the_morning(monkeypatch):
    monkeypatch.setattr(bots, "CHATTER_CHANCE", 1.0)
    g = game_of(bot_count=7)
    g.start()
    for _ in range(3):
        if g.phase == Phase.NIGHT:
            g.force()
        if g.game_over:
            break
    assert g.chat.messages or g.game_over


def test_wolf_bots_share_a_single_day_target():
    g = game_of(n=9, bot_count=9)
    roles(g, {1: (F.WOLF, A.NONE), 2: (F.WOLF, A.NONE), 3: (F.WOLF, A.NONE)})
    g.start()
    targets = {bots.wolf_day_target(g).id for _ in range(20)}
    assert len(targets) == 1


def test_suspicion_rises_for_players_who_voted_the_bot():
    g = game_of()
    g.start()
    g.vote_history.append({2: 1, 3: 4})
    scores = bots.suspicion(g, g.player(1))
    assert scores[2] > scores.get(3, 0)


def test_bandwagon_follows_the_leader(monkeypatch):
    monkeypatch.setattr(bots, "BANDWAGON_CHANCE", 1.0)
    g = game_of()
    roles(g, {1: (F.VILLAGER, A.NONE)})
    g.start()
    others = [p for p in g.players if p.id != 1]
    assert bots.day_vote(g, g.player(1), others, {2: 5, 3: 5, 4: 5}).id == 5


def test_bot_only_games_still_finish():
    for seed in range(15):
        random.seed(seed)
        g = Game([(f"B{i}", True) for i in range(9)], events=True, timer=30)
        g.start()
        for _ in range(60):
            if g.game_over:
                break
            g.force()
        assert g.game_over, seed


def test_dead_talk_switch_puts_the_dead_in_public_chat():
    g = game_of()  # mặc định bật
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.submit(6, 1, "wolf")
    g.submit(7, 1, "wolf")
    assert g.view_for(1)["chatChannel"] == "public"
    g.post_chat(1, "tôi nghi P6", target=6, now=1)
    msg = g.view_for(2)["chat"][-1]
    assert msg["dead"] is True and msg["channel"] == "public"


# ---------- nền tảng: riêng tư, bot thay người rời, đồng hồ giả, chat sạch ----------
def test_living_players_never_see_wolf_chat_or_the_full_log():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.post_chat(6, "tối nay giết P1", now=1)
    for pid in range(1, 6):
        view = g.view_for(pid)
        assert view["chat"] == [] and not any("(Sói" in e["text"] for e in view["log"])
    assert [m["text"] for m in g.view_for(7)["chat"]] == ["tối nay giết P1"]


def test_the_dead_see_the_full_log_but_the_wolf_channel_stays_with_wolves():
    g = game_of()
    roles(g, {6: (F.WOLF, A.KILL), 7: (F.WOLF, A.NONE)})
    g.start()
    g.post_chat(6, "bí mật", now=1)
    g.player(1).alive = False
    assert g.can_see_everything(1) and not g.can_see_everything(2)
    assert not g.view_for(1)["chat"]  # original semantics: the dead read the dead channel, not the wolves'
    g.game_over = True
    assert [m["text"] for m in g.view_for(2)["chat"]] == ["bí mật"]  # everything once the game is over


def test_message_visible_rules():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    msg = g.post_chat(6, "hi", now=1)
    assert g.message_visible(g.player(7), msg) and not g.message_visible(g.player(1), msg)
    assert g.message_visible(g.player(1), msg, everything=True)


def test_take_over_makes_a_leaver_a_bot_and_never_blocks_the_phase():
    g = game_of(n=9)
    roles(g, {1: (F.VILLAGER, A.SEE_FACTION), 8: (F.WOLF, A.NONE), 9: (F.WOLF, A.NONE)})
    g.start()
    assert 1 in g.missing()
    g.take_over(1)
    assert g.player(1).is_bot and 1 not in g.missing()
    g.take_over(1)  # already a bot: nothing happens
    for _ in range(40):
        if g.game_over:
            break
        g.force()
    assert g.game_over


def test_take_over_during_revenge_releases_the_wait():
    g = game_of(n=9)
    roles(g, {1: (F.VILLAGER, A.KILL_ON_DEATH), 8: (F.WOLF, A.NONE), 9: (F.WOLF, A.NONE)})
    g.start()
    g.submit(8, 1, "wolf")
    g.submit(9, 1, "wolf")
    assert g.phase == Phase.REVENGE and g.pending_revenge == 1
    g.take_over(1)
    assert g.phase != Phase.REVENGE


def test_take_over_before_start_or_after_the_end_only_flags_the_seat():
    g = game_of(n=9)
    g.take_over(2)
    assert g.player(2).is_bot and g.phase == Phase.SETUP


def test_timer_uses_the_injected_clock():
    now = [10.0]
    g = game_of(timer=30, clock=lambda: now[0])
    g.start()
    assert g.seconds_left() == 30
    now[0] += 12
    assert g.seconds_left() == 18 and not g.tick()
    now[0] += 20
    assert g.tick()


def test_chat_uses_the_injected_clock_for_spacing():
    now = [5.0]
    g = game_of(clock=lambda: now[0])
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.post_chat(6, "một")
    with pytest.raises(GameError, match="nhanh"):
        g.post_chat(6, "hai")
    now[0] += 1
    g.post_chat(6, "ba")


@pytest.mark.parametrize("raw,clean", [
    ("a\x00b\x07c", "abc"),
    ("  nhiều   khoảng\ttrắng\n ", "nhiều khoảng trắng"),
    ("an‮evil", "anevil"),
    ("zero​width﻿", "zerowidth"),
    ("<script>alert(1)</script>", "<script>alert(1)</script>"),  # never escaped: clients render text
    ("👨‍👩 gia đình ❤️", "👨‍👩 gia đình ❤️"),  # emoji joiners are kept
])
def test_chat_text_is_cleaned(raw, clean):
    from api.werewolf.engine.chat import clean as clean_text
    assert clean_text(raw) == clean


def test_chat_rejects_text_that_is_only_control_characters():
    from api.werewolf.engine.chat import ChatError
    from api.werewolf.engine.chat import clean as clean_text
    with pytest.raises(ChatError):
        clean_text("\x00\x01​")


def test_death_records_the_night_it_happened():
    g = game_of()
    roles(g, {6: (F.WOLF, A.NONE), 7: (F.WOLF, A.NONE)})
    g.start()
    g.submit(6, 1, "wolf")
    g.submit(7, 1, "wolf")
    assert g.player(1).died_on == 1 and g.player(2).died_on is None
