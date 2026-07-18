from src.pipeline.need_profile import NeedProfile
from src.pipeline.session_store import (
    DEFAULT_TTL_SECONDS,
    InMemorySessionStore,
    SessionStore,
)


def make_profile() -> NeedProfile:
    return NeedProfile(category="máy_lạnh", slots={"ngan_sach_max": 20000000})


class FakeClock:
    """Injectable monotonic-style clock for deterministic TTL tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_in_memory_store_satisfies_protocol() -> None:
    assert isinstance(InMemorySessionStore(), SessionStore)


def test_default_ttl_is_thirty_minutes() -> None:
    assert DEFAULT_TTL_SECONDS == 1800


def test_set_then_get_roundtrip() -> None:
    store = InMemorySessionStore()
    store.set("s1", make_profile())
    got = store.get("s1")
    assert got is not None
    assert got.category == "máy_lạnh"
    assert got.slots["ngan_sach_max"] == 20000000


def test_get_missing_returns_none() -> None:
    store = InMemorySessionStore()
    assert store.get("does-not-exist") is None


def test_set_overwrites_existing() -> None:
    store = InMemorySessionStore()
    store.set("s1", make_profile())
    updated = NeedProfile(category="tủ_lạnh")
    store.set("s1", updated)
    got = store.get("s1")
    assert got is not None
    assert got.category == "tủ_lạnh"


def test_delete_removes_entry() -> None:
    store = InMemorySessionStore()
    store.set("s1", make_profile())
    store.delete("s1")
    assert store.get("s1") is None


def test_delete_missing_is_noop() -> None:
    store = InMemorySessionStore()
    store.delete("never-existed")  # must not raise


def test_entry_within_ttl_is_returned() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(ttl_seconds=30, clock=clock)
    store.set("s1", make_profile())
    clock.advance(29)
    assert store.get("s1") is not None


def test_entry_past_ttl_expires() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(ttl_seconds=30, clock=clock)
    store.set("s1", make_profile())
    clock.advance(31)
    assert store.get("s1") is None


def test_expired_entry_is_evicted_on_access() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(ttl_seconds=30, clock=clock)
    store.set("s1", make_profile())
    clock.advance(31)
    assert store.get("s1") is None
    # entry is gone even if the clock rewinds; lazy access evicted it
    clock.now = 1000.0
    assert store.get("s1") is None


def test_set_refreshes_ttl_window() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(ttl_seconds=10, clock=clock)
    store.set("s1", make_profile())
    clock.advance(8)
    store.set("s1", make_profile())  # refresh timestamp
    clock.advance(7)  # 15s since first set, but only 7s since refresh
    assert store.get("s1") is not None
