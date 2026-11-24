import pytest

from api.ai.provider import SCENES, DummyProvider, get_provider


class TestDummyProvider:
    def test_is_deterministic(self):
        provider = DummyProvider()
        assert provider.video_script("Blue sea") == provider.video_script("Blue sea")
        assert provider.answer("hi") == provider.answer("hi")

    def test_script_has_eight_scenes_and_matching_subtitles(self):
        script = DummyProvider().video_script("Hoàng hôn trên vịnh Hạ Long")
        assert script.topic == script.filename == "hoang_hon_tren_vinh_ha_long"
        assert len(script.stories) == SCENES
        assert all("[CAMERA:" in story and "[AUDIO:" in story for story in script.stories)
        (subtitle,) = script.subtitles
        blocks = subtitle.text.split("\n\n")
        assert len(blocks) == SCENES
        assert blocks[0].startswith("1\n00:00:00,000 --> 00:00:08,000")
        assert blocks[7].startswith("8\n00:00:56,000 --> 00:01:04,000")

    def test_topic_is_capped_and_never_empty(self):
        assert DummyProvider().video_script("one two three four five six seven eight nine ten").topic.count("_") == 7
        assert DummyProvider().video_script("!!!").topic == "untitled"

    def test_answer_says_it_is_a_stand_in(self):
        answer = DummyProvider().answer(" what is oil paint? ")
        assert answer.language == "text"
        assert "giả lập" in answer.content and "what is oil paint?" in answer.content


class TestProviderChoice:
    def test_dummy_is_the_default(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        assert get_provider().name == "dummy"
        monkeypatch.setenv("AI_PROVIDER", " Dummy ")
        assert get_provider().name == "dummy"

    def test_an_unknown_provider_stops_the_start(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "openai")
        with pytest.raises(RuntimeError, match="not supported"):
            get_provider()
