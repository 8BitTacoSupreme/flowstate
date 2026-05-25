"""Tests for handler registry profile/disabled gating (HOOK-01, HOOK-02)."""

from __future__ import annotations

import pytest

from flowstate.events.handler import handler
from flowstate.events.registry import (
    _PROFILE_ORDER,
    HandlerRegistry,
    _current_profile,
    _disabled_names,
)


class TestCurrentProfile:
    def test_unset_defaults_to_standard(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_HANDLERS", raising=False)
        assert _current_profile() == _PROFILE_ORDER["standard"]

    def test_minimal_returns_zero(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "minimal")
        assert _current_profile() == 0

    def test_strict_returns_two(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "strict")
        assert _current_profile() == 2

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "MINIMAL")
        assert _current_profile() == 0

    def test_unrecognized_falls_back_to_standard(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "paranoid")
        assert _current_profile() == _PROFILE_ORDER["standard"]


class TestDisabledNames:
    def test_unset_returns_empty(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        assert _disabled_names() == set()

    def test_single_name(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "audit_handler")
        assert _disabled_names() == {"audit_handler"}

    def test_comma_separated(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "a,b,c")
        assert _disabled_names() == {"a", "b", "c"}

    def test_whitespace_tolerated(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", " a , b , c ")
        assert _disabled_names() == {"a", "b", "c"}

    def test_empty_strings_ignored(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "a,,,")
        assert _disabled_names() == {"a"}


class TestHandlerProfileKwarg:
    def test_default_profile_is_standard(self):
        @handler("test.event")
        def h(event):
            pass

        assert h.profile == "standard"

    def test_explicit_profile_minimal(self):
        @handler("test.event", profile="minimal")
        def h(event):
            pass

        assert h.profile == "minimal"

    def test_explicit_profile_strict(self):
        @handler("test.event", profile="strict")
        def h(event):
            pass

        assert h.profile == "strict"

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="Invalid profile"):

            @handler("test.event", profile="paranoid")  # type: ignore[arg-type]
            def h(event):
                pass


class TestRegistryProfileGating:
    def test_minimal_env_registers_only_minimal_handlers(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "minimal")
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        reg = HandlerRegistry()

        @handler("e", profile="minimal")
        def h_min(event):
            pass

        @handler("e", profile="standard")
        def h_std(event):
            pass

        @handler("e", profile="strict")
        def h_strict(event):
            pass

        assert reg.register_handler(h_min) is True
        assert reg.register_handler(h_std) is False
        assert reg.register_handler(h_strict) is False
        assert len(reg.get_handlers("e")) == 1

    def test_standard_env_registers_minimal_and_standard(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "standard")
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        reg = HandlerRegistry()

        @handler("e", profile="minimal")
        def h_min(event):
            pass

        @handler("e", profile="standard")
        def h_std(event):
            pass

        @handler("e", profile="strict")
        def h_strict(event):
            pass

        assert reg.register_handler(h_min) is True
        assert reg.register_handler(h_std) is True
        assert reg.register_handler(h_strict) is False
        assert len(reg.get_handlers("e")) == 2

    def test_strict_env_registers_all(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "strict")
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        reg = HandlerRegistry()

        @handler("e", profile="strict")
        def h_strict(event):
            pass

        @handler("e", profile="minimal")
        def h_min(event):
            pass

        @handler("e", profile="standard")
        def h_std(event):
            pass

        assert reg.register_handler(h_strict) is True
        assert reg.register_handler(h_min) is True
        assert reg.register_handler(h_std) is True
        assert len(reg.get_handlers("e")) == 3

    def test_unset_env_behaves_like_standard(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_HANDLERS", raising=False)
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        reg = HandlerRegistry()

        @handler("e", profile="strict")
        def h_strict(event):
            pass

        assert reg.register_handler(h_strict) is False

    def test_handler_without_event_types_raises(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        reg = HandlerRegistry()
        with pytest.raises(ValueError, match="no event_types"):
            reg.register_handler(lambda e: None)


class TestRegistryDisabledNames:
    def test_disabled_name_skipped_regardless_of_profile(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "strict")
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "h_min")
        reg = HandlerRegistry()

        @handler("e", profile="minimal")
        def h_min(event):
            pass

        assert reg.register_handler(h_min) is False
        assert len(reg.get_handlers("e")) == 0

    def test_disabled_takes_precedence_over_profile_allow(self, monkeypatch):
        """A handler that WOULD register by profile is still skipped if disabled."""
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "strict")
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "blocked_handler")
        reg = HandlerRegistry()

        @handler("e", profile="standard")
        def blocked_handler(event):
            pass

        assert reg.register_handler(blocked_handler) is False

    def test_non_disabled_handler_still_registers(self, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "other")
        monkeypatch.setenv("FLOWSTATE_HANDLERS", "standard")
        reg = HandlerRegistry()

        @handler("e")
        def my_handler(event):
            pass

        assert reg.register_handler(my_handler) is True
