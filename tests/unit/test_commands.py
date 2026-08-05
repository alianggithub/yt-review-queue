"""Unit tests for the command parser."""
import pytest
from yt_review_queue.commands import parse_command


def test_priority_digit():
    r = parse_command("priority 5")
    assert r is not None
    assert r["cmd"] == "priority"
    assert r["priority"] == 5


def test_priority_word_voice():
    r = parse_command("priority five")
    assert r is not None
    assert r["cmd"] == "priority"
    assert r["priority"] == 5


def test_priority_with_note():
    r = parse_command("priority 5 check the benchmark")
    assert r is not None
    assert r["cmd"] == "priority"
    assert r["priority"] == 5
    assert r["note"] == "check the benchmark"


def test_priority_word_with_note():
    r = parse_command("priority three look at the GPU part")
    assert r is not None
    assert r["cmd"] == "priority"
    assert r["priority"] == 3
    assert r["note"] == "look at the GPU part"


def test_priority_zero():
    r = parse_command("priority 0")
    assert r is not None
    assert r["priority"] == 0


def test_queue_no_arg():
    r = parse_command("queue")
    assert r is not None
    assert r["cmd"] == "queue"
    assert r["id"] is None


def test_queue_with_id():
    r = parse_command("queue Q7F2")
    assert r is not None
    assert r["cmd"] == "queue"
    assert r["id"] == "Q7F2"


def test_choose():
    r = parse_command("choose Q7F2 1")
    assert r is not None
    assert r["cmd"] == "choose"
    assert r["id"] == "Q7F2"
    assert r["candidate"] == 1


def test_link():
    r = parse_command("link Q7F2 https://youtu.be/abc?t=120")
    assert r is not None
    assert r["cmd"] == "link"
    assert r["id"] == "Q7F2"
    assert "abc" in r["url"]


def test_wiki():
    r = parse_command("wiki Q7F2")
    assert r is not None
    assert r["cmd"] == "wiki"
    assert r["id"] == "Q7F2"
    assert r["category"] is None


def test_wiki_with_category():
    r = parse_command("wiki Q7F2 as llm-model-trends")
    assert r is not None
    assert r["cmd"] == "wiki"
    assert r["id"] == "Q7F2"
    assert r["category"] == "llm-model-trends"


def test_watched():
    r = parse_command("watched Q7F2")
    assert r is not None
    assert r["cmd"] == "watched"
    assert r["id"] == "Q7F2"


def test_status():
    r = parse_command("status")
    assert r is not None
    assert r["cmd"] == "status"


def test_switch():
    r = parse_command("switch dan")
    assert r is not None
    assert r["cmd"] == "switch"
    assert r["label"] == "dan"


def test_garbage():
    assert parse_command("garbage") is None


def test_empty():
    assert parse_command("") is None


def test_priority_invalid():
    # priority 6 is out of range (0-5), parser returns None
    assert parse_command("priority 6") is None
