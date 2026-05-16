import pytest

from travel_agent.agent.memory import InMemoryMemory


def test_sliding_window_drops_oldest():
    m = InMemoryMemory(max_messages=3)
    for i in range(5):
        m.add_message({"role": "user", "content": str(i)})
    assert [x["content"] for x in m.get_messages()] == ["2", "3", "4"]


def test_get_messages_returns_a_copy():
    m = InMemoryMemory(max_messages=10)
    m.add_message({"role": "user", "content": "a"})
    snapshot = m.get_messages()
    snapshot.append({"role": "user", "content": "tampered"})
    assert [x["content"] for x in m.get_messages()] == ["a"]


def test_clear_resets():
    m = InMemoryMemory(max_messages=10)
    m.add_message({"role": "user", "content": "a"})
    m.clear()
    assert m.get_messages() == []


def test_missing_role_rejected():
    m = InMemoryMemory(max_messages=10)
    with pytest.raises(ValueError):
        m.add_message({"content": "no role"})


def test_invalid_max_messages():
    with pytest.raises(ValueError):
        InMemoryMemory(max_messages=0)
