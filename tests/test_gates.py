"""Tests for scripy/gates.py — StdinGateProvider fast paths (no stdin required)."""

from scripy.gates import StdinGateProvider

HELLO = '#!/usr/bin/env python3\nprint("hello")'


class TestRunGateFastPaths:
    def test_yes_flag_proceeds(self):
        gp = StdinGateProvider()
        proceed, always_run, code = gp.run_gate(HELLO, yes=True, always_run=False)
        assert proceed is True

    def test_yes_flag_returns_code_unchanged(self):
        gp = StdinGateProvider()
        proceed, always_run, code = gp.run_gate(HELLO, yes=True, always_run=False)
        assert code == HELLO

    def test_yes_flag_does_not_set_always_run(self):
        gp = StdinGateProvider()
        proceed, always_run, code = gp.run_gate(HELLO, yes=True, always_run=False)
        assert always_run is False

    def test_always_run_proceeds(self):
        gp = StdinGateProvider()
        proceed, always_run, code = gp.run_gate(HELLO, yes=False, always_run=True)
        assert proceed is True

    def test_always_run_preserves_flag(self):
        gp = StdinGateProvider()
        proceed, always_run, code = gp.run_gate(HELLO, yes=False, always_run=True)
        assert always_run is True

    def test_yes_true_always_run_true_both_proceed(self):
        gp = StdinGateProvider()
        proceed, always_run, code = gp.run_gate(HELLO, yes=True, always_run=True)
        assert proceed is True


class TestWriteGateFastPaths:
    def test_yes_flag_returns_true(self):
        gp = StdinGateProvider()
        assert gp.write_gate("out.py", yes=True) is True
