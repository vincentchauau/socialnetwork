"""The messaging helpers without a broker: nothing is required, and a missing broker is `Unavailable`, not a crash."""

import asyncio

import pytest
from sn_shared import messaging


def test_a_queue_spec_names_its_dead_letter_exchange_and_queue():
    spec = messaging.QueueSpec("jobs.notify")
    assert (spec.dead_exchange, spec.dead_queue) == ("jobs.notify.dlx", "jobs.notify.dlq")


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("RABBITMQ_HOST", "mq.internal")
    monkeypatch.setenv("RABBITMQ_PORT", "5673")
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "bus:9092")
    settings = messaging.rabbitmq_settings()
    assert settings["host"] == "mq.internal" and settings["port"] == 5673
    assert messaging.kafka_bootstrap() == "bus:9092"


def test_publishing_with_no_rabbitmq_is_unavailable(monkeypatch):
    monkeypatch.setenv("RABBITMQ_HOST", "127.0.0.1")
    monkeypatch.setenv("RABBITMQ_PORT", "1")
    queue = messaging.WorkQueue(messaging.QueueSpec("none"))
    with pytest.raises(messaging.Unavailable) as caught:
        asyncio.run(queue.publish(b"{}"))
    assert caught.value.what == "rabbitmq"
    assert asyncio.run(queue.ping()) is False


def test_publishing_with_no_kafka_is_unavailable(monkeypatch):
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "127.0.0.1:1")
    log = messaging.EventLog("none")
    with pytest.raises(messaging.Unavailable) as caught:
        asyncio.run(log.publish("k", b"v"))
    assert caught.value.what == "kafka"
