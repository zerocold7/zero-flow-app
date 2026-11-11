"""Dictation on / Reader on (zeroflow/halves.py): each half can be switched off, which
frees its memory; with both off the Engine is Paused. The halves are fakes here; the
real ones (Whisper and the AI, the Reader child process) are checked at the 5b gate."""
import pytest

from zeroflow.halves import Halves


class FakeHalf:
    def __init__(self, fails=False):
        self.running = False
        self.calls = []
        self.fails = fails

    def start(self):
        self.calls.append("start")
        if self.fails:
            raise RuntimeError("no graphics memory")
        self.running = True

    def stop(self):
        """Stopping means freeing the memory: the real one unloads the models."""
        self.calls.append("stop")
        self.running = False


@pytest.fixture
def parts():
    dictation, reader, saved = FakeHalf(), FakeHalf(), {}
    dictation.running = reader.running = True       # both on at start
    halves = Halves(dictation, reader, save=saved.__setitem__)
    return halves, dictation, reader, saved


def test_both_on_is_active(parts):
    halves, *_ = parts
    assert halves.dictation_on and halves.reader_on
    assert halves.state == "active"


def test_turning_dictation_off_frees_only_dictation(parts):
    halves, dictation, reader, _ = parts
    halves.set_dictation(False)
    assert dictation.calls == ["stop"] and not dictation.running
    assert reader.calls == [] and reader.running
    assert halves.state == "active"


def test_turning_reader_off_frees_only_the_reader(parts):
    halves, dictation, reader, _ = parts
    halves.set_reader(False)
    assert reader.calls == ["stop"] and dictation.calls == []
    assert halves.state == "active"


def test_both_off_is_paused_and_says_so(qtbot, parts):
    halves, dictation, reader, _ = parts
    with qtbot.waitSignal(halves.state_changed, timeout=500) as seen:
        halves.set_dictation(False)
        halves.set_reader(False)
    assert seen.args == ["paused"]
    assert halves.state == "paused"
    assert not dictation.running and not reader.running      # nothing held


def test_turning_one_back_on_leaves_paused(parts):
    halves, dictation, *_ = parts
    halves.set_dictation(False)
    halves.set_reader(False)
    halves.set_dictation(True)
    assert dictation.calls == ["stop", "start"] and dictation.running
    assert halves.state == "active"


def test_switching_to_the_state_it_is_already_in_does_nothing(parts):
    halves, dictation, *_ = parts
    halves.set_dictation(True)
    halves.set_dictation(False)
    halves.set_dictation(False)
    assert dictation.calls == ["stop"]


def test_the_choice_is_saved_so_the_next_start_keeps_it(parts):
    halves, *_, saved = parts
    halves.set_reader(False)
    halves.set_dictation(False)
    assert saved == {"READER_ON": False, "DICTATION_ON": False}


def test_a_half_that_cannot_start_stays_off_and_reports_it(qtbot):
    dictation, reader = FakeHalf(fails=True), FakeHalf()
    reader.running = True
    saved = {}
    halves = Halves(dictation, reader, save=saved.__setitem__)
    assert not halves.dictation_on
    with qtbot.waitSignal(halves.problem, timeout=500) as seen:
        halves.set_dictation(True)
    assert "graphics memory" in seen.args[0]
    assert not halves.dictation_on
    assert "DICTATION_ON" not in saved           # the file still says what is true
    assert halves.state == "active"              # the Reader still runs
