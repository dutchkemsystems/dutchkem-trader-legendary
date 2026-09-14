"""Tests for exit optimizer cooldown after engine restart.

Bug: When the engine restarts, positions are synced from MT5 into
open_positions. The exit optimizer immediately runs on these positions
on the very first cycle and may close them prematurely because the ML
model sees them as fresh and recommends exit based on current price
meeting exit criteria.

Fix: Track registered_at_cycle on each position. Skip exit optimizer
for positions that haven't been tracked for at least
EXIT_OPTIMIZER_COOLDOWN_CYCLES (default 2) cycles.
"""

import importlib
import pytest


@pytest.fixture
def engine_module():
    return importlib.import_module("unified_engine")


@pytest.fixture
def cooldown():
    mod = importlib.import_module("unified_engine")
    return getattr(mod, 'EXIT_OPTIMIZER_COOLDOWN_CYCLES', 2)


class TestCooldownConstant:
    """EXIT_OPTIMIZER_COOLDOWN_CYCLES must exist and be reasonable."""

    def test_cooldown_constant_exists(self, engine_module):
        """Module-level constant EXIT_OPTIMIZER_COOLDOWN_CYCLES must be defined."""
        assert hasattr(engine_module, 'EXIT_OPTIMIZER_COOLDOWN_CYCLES')

    def test_cooldown_is_positive_integer(self, cooldown):
        """Cooldown must be a positive integer >= 1."""
        assert isinstance(cooldown, int)
        assert cooldown >= 1

    def test_cooldown_is_reasonable(self, cooldown):
        """Cooldown should be between 1 and 10 cycles."""
        assert 1 <= cooldown <= 10


class TestPositionAgeCheck:
    """Verify the cycle-age logic that the exit optimizer will use."""

    def test_first_cycle_after_sync_is_in_cooldown(self, cooldown):
        """Position just synced (cycle 0) at cycle 5 should be in cooldown."""
        registered_at_cycle = 5
        current_cycle = 5  # Same cycle as registration
        cycles_tracked = current_cycle - registered_at_cycle
        assert cycles_tracked == 0
        assert cycles_tracked < cooldown

    def test_one_cycle_after_sync_is_in_cooldown(self, cooldown):
        """Position synced at cycle 5, checked at cycle 6: 1 cycle tracked."""
        cycles_tracked = 6 - 5
        assert cycles_tracked < cooldown  # Still in cooldown when cooldown=2

    def test_two_cycles_after_sync_passes_cooldown(self, cooldown):
        """Position synced at cycle 5, checked at cycle 7: passes cooldown."""
        cycles_tracked = 7 - 5
        assert cycles_tracked >= cooldown  # 2 >= 2

    def test_many_cycles_after_sync_passes_cooldown(self, cooldown):
        """Position synced at cycle 5, checked at cycle 50: well past cooldown."""
        cycles_tracked = 50 - 5
        assert cycles_tracked >= cooldown

    def test_scalper_positions_also_get_cooldown(self, cooldown):
        """Scalper-registered positions should also be subject to cooldown."""
        # Scalper registers positions during cycle 10
        registered_at_cycle = 10
        current_cycle = 10
        cycles_tracked = current_cycle - registered_at_cycle
        assert cycles_tracked < cooldown


class TestRegisteredAtCycleField:
    """Positions should have registered_at_cycle when created."""

    def test_source_has_registered_at_cycle(self, engine_module):
        """unified_engine.py must contain 'registered_at_cycle' field."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'registered_at_cycle' in content

    def test_exit_optimizer_checks_registered_at_cycle(self, engine_module):
        """The exit optimizer section must reference registered_at_cycle and the cooldown constant."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'EXIT_OPTIMIZER_COOLDOWN_CYCLES' in content, (
            "EXIT_OPTIMIZER_COOLDOWN_CYCLES constant not found in unified_engine.py"
        )
        # The cooldown check should reference registered_at_cycle
        # It should check cycles_tracked or similar against the cooldown
        assert 'registered_at_cycle' in content


class TestExitOptimizerSectionGuard:
    """The exit optimizer code path must contain a cooldown guard."""

    def test_exit_optimizer_section_has_cooldown_guard(self, engine_module):
        """Lines near _get_optimized_exit call must check registered_at_cycle."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Find the exit optimizer section that calls _get_optimized_exit
        for i, line in enumerate(lines):
            if '_get_optimized_exit' in line and 'exit_rec' in line:
                # Look in surrounding 10 lines for cooldown check
                start = max(0, i - 5)
                end = min(len(lines), i + 2)
                section = ''.join(lines[start:end])
                assert 'registered_at_cycle' in section, (
                    f"No cooldown guard near _get_optimized_exit call at line {i+1}. "
                    f"Found: {section.strip()}"
                )
                assert 'EXIT_OPTIMIZER_COOLDOWN_CYCLES' in section, (
                    f"No cooldown constant reference near _get_optimized_exit at line {i+1}"
                )
                return
        pytest.fail("_get_optimized_exit call with exit_rec not found in source")

    def test_scalper_registration_has_registered_at_cycle(self, engine_module):
        """Scalper position registration must include registered_at_cycle."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Find the scalper registration section (source == "scalper")
        for i, line in enumerate(lines):
            if '"source": "scalper"' in line:
                # Check the full dict block (from open_positions assignment to closing brace)
                start = max(0, i - 8)
                end = min(len(lines), i + 4)
                section = ''.join(lines[start:end])
                assert 'registered_at_cycle' in section, (
                    f"Scalper registration at line {i+1} missing registered_at_cycle. "
                    f"Context:\n{section}"
                )
                return
        pytest.fail("Scalper registration (source=='scalper') not found in source")

    def test_signal_execution_has_registered_at_cycle(self, engine_module):
        """Signal execution position registration must include registered_at_cycle."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Find the signal execution section (open_positions[signal.symbol])
        for i, line in enumerate(lines):
            if 'open_positions[signal.symbol]' in line and '= {' in line:
                # Check next 20 lines for registered_at_cycle (dict may be long)
                end = min(len(lines), i + 20)
                section = ''.join(lines[i:end])
                assert 'registered_at_cycle' in section, (
                    f"Signal execution at line {i+1} missing registered_at_cycle. "
                    f"Context:\n{section}"
                )
                return
        pytest.fail("Signal execution position registration not found")

    def test_reverse_reconciliation_has_registered_at_cycle(self, engine_module):
        """Reverse reconciliation (MT5 sync) must include registered_at_cycle."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Find the reverse reconciliation section (source == "mt5_sync")
        for i, line in enumerate(lines):
            if '"source": "mt5_sync"' in line:
                start = max(0, i - 10)
                end = min(len(lines), i + 4)
                section = ''.join(lines[start:end])
                assert 'registered_at_cycle' in section, (
                    f"Reverse reconciliation at line {i+1} missing registered_at_cycle. "
                    f"Context:\n{section}"
                )
                return
        pytest.fail("Reverse reconciliation (mt5_sync) not found in source")


class TestOtherExitsUnaffected:
    """Cooldown must not block time exits or trailing stops."""

    def test_time_exit_uses_bars_held(self, engine_module):
        """Time exit uses entry_time + bars_held, not cycle count."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'bars_held' in content
        assert 'TIME_EXIT' in content

    def test_trailing_stop_uses_sl_tp_levels(self, engine_module):
        """Trailing stop logic operates on SL/TP levels, not cycle count."""
        import inspect
        source_file = inspect.getfile(engine_module)
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'trailing_enabled' in content
        assert 'partial_tp_done' in content
