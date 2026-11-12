"""Phase 7: Zero- Flow as a PyInstaller build (zeroflow/frozen.py).

In a build, sys.executable is ZeroFlow.exe, not Python: `[sys.executable, "-m", ...]`
starts a second Engine instead of the Reader, the download or the AI test. Each child is
started as `ZeroFlow.exe --child <role>`, and zero_flow.py hands that to the module.
From source nothing changes. Also here: where the AI runtime goes (the program folder
in Program Files cannot be written to), where Whisper finds the CUDA libraries in a
build, and standard streams for a windowed build's children.
"""
import io
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import frozen, paths

EXE = r"C:\Program Files\Zero- Flow\ZeroFlow.exe"
PY = r"F:\app\venv\Scripts\python.exe"


# ---------------------------------------------------------------- child processes
@pytest.mark.parametrize("role, module", [("reader", "reader"), ("fetch", "zeroflow.fetch"),
                                          ("ai-check", "zeroflow.ai_check")])
def test_from_source_a_child_is_python_dash_m(role, module):
    assert frozen.child_command(role, frozen=False, executable=PY) == [PY, "-m", module]


@pytest.mark.parametrize("role", ["reader", "fetch", "ai-check"])
def test_in_a_build_a_child_is_the_exe_with_its_role(role):
    assert frozen.child_command(role, frozen=True, executable=EXE) == [EXE, "--child", role]


def test_arguments_follow_the_role():
    assert frozen.child_command("fetch", '{"repo": "x"}', frozen=True, executable=EXE) == \
        [EXE, "--child", "fetch", '{"repo": "x"}']
    assert frozen.child_command("fetch", "a", frozen=False, executable=PY) == \
        [PY, "-m", "zeroflow.fetch", "a"]


def test_an_unknown_role_is_refused():
    with pytest.raises(KeyError):
        frozen.child_command("engine", frozen=True, executable=EXE)


def test_every_child_module_exists():
    import importlib.util
    for module in frozen.CHILD_MODULES.values():
        assert importlib.util.find_spec(module) is not None, module


def test_no_child_is_started_with_dash_m_any_more():
    """The four places that started children with `sys.executable -m` go through
    child_command, so a build cannot start a second Engine by mistake."""
    root = os.path.dirname(paths.__file__)
    for name in ("supervisor.py", "first_run.py"):
        with open(os.path.join(root, name), encoding="utf-8") as f:
            assert '"-m"' not in f.read(), name


# ---------------------------------------------------------------- zero_flow.py hands over
def test_a_child_flag_runs_that_module_as_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", list(sys.argv))      # run_child sets it
    ran = []
    argv = [EXE, "--child", "fetch", '{"repo": "x"}']
    handled = frozen.run_child(argv, run_module=lambda m, **kw: ran.append((m, kw, list(sys.argv))))
    assert handled is True
    module, kwargs, seen_argv = ran[0]
    assert module == "zeroflow.fetch" and kwargs["run_name"] == "__main__"
    assert seen_argv == [EXE, '{"repo": "x"}']        # the module sees its own arguments


def test_without_the_flag_the_engine_runs():
    ran = []
    assert frozen.run_child([EXE], run_module=lambda m, **kw: ran.append(m)) is False
    assert frozen.run_child([EXE, "--restart"], run_module=lambda m, **kw: ran.append(m)) is False
    assert ran == []


def test_an_unknown_child_role_exits_with_an_error():
    with pytest.raises(SystemExit) as stop:
        frozen.run_child([EXE, "--child", "nonsense"], run_module=lambda m, **kw: None)
    assert stop.value.code == 2


def test_the_entry_point_hands_children_over_before_the_engine():
    """zero_flow.py must check for --child before it imports the supervisor, or the
    child would load Qt and claim the single-instance lock first."""
    root = os.path.dirname(os.path.dirname(paths.__file__))
    with open(os.path.join(root, "zero_flow.py"), encoding="utf-8") as f:
        source = f.read()
    assert source.index("run_child") < source.index("supervisor.run")


# ---------------------------------------------------------------- restart and sign-in
def test_a_restart_from_source_runs_the_entry_point():
    command = frozen.engine_command("--restart", frozen=False, executable=PY, base_dir=r"F:\app")
    assert command == [PY, r"F:\app\zero_flow.py", "--restart"]


def test_a_restart_in_a_build_runs_the_exe():
    assert frozen.engine_command("--restart", frozen=True, executable=EXE) == [EXE, "--restart"]


def test_start_with_windows_in_a_build_runs_the_exe(tmp_path):
    from zeroflow.settings_window import startup_command
    assert startup_command(r"C:\app", EXE, frozen=True) == f'"{EXE}"'


def test_start_with_windows_from_source_is_unchanged(tmp_path):
    from zeroflow.settings_window import startup_command
    (tmp_path / "pythonw.exe").write_text("")
    command = startup_command(r"C:\app", str(tmp_path / "python.exe"), frozen=False)
    assert "pythonw.exe" in command and command.endswith('zero_flow.py"')


# ---------------------------------------------------------------- where the AI runtime goes
def test_in_a_build_the_runtime_goes_to_local_app_data():
    where = paths.runtime_dir(frozen=True, environ={"LOCALAPPDATA": r"C:\Users\z\AppData\Local"})
    assert where == r"C:\Users\z\AppData\Local\ZeroFlow\runtime"


def test_from_source_the_runtime_stays_in_the_program_folder():
    assert paths.runtime_dir(frozen=False, environ={}) == os.path.join(paths.BASE_DIR, "runtime")


def test_the_llama_runtime_uses_runtime_dir(monkeypatch, tmp_path):
    """Loaded as in a build: from source both paths are the same, which would hide it."""
    import importlib
    from zeroflow.llm import llama_runtime
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        importlib.reload(llama_runtime)
        assert llama_runtime.RUNTIME_DIR == str(tmp_path / "ZeroFlow" / "runtime" / "llama")
    finally:
        monkeypatch.undo()
        importlib.reload(llama_runtime)


# ---------------------------------------------------------------- CUDA in a build
def _dirs(tmp_path, *names):
    for name in names:
        (tmp_path / name).mkdir(parents=True)


def test_from_source_the_pip_cuda_packages_are_found(tmp_path):
    _dirs(tmp_path, "nvidia/cublas/bin", "nvidia/cudnn/bin")
    found = frozen.cuda_dll_dirs([str(tmp_path)], frozen=False, bundle_dir=None)
    assert found == [str(tmp_path / "nvidia" / "cublas" / "bin"),
                     str(tmp_path / "nvidia" / "cudnn" / "bin")]


def test_in_a_build_whisper_uses_the_cuda_libraries_torch_ships(tmp_path):
    """Measured 2026-11-12 (tools/measure_cuda_from_torch.py): CTranslate2 runs on torch's
    cuBLAS/cuDNN, so the GPU edition need not carry the nvidia packages (1.9 GB) too."""
    _dirs(tmp_path, "torch/lib")
    found = frozen.cuda_dll_dirs([], frozen=True, bundle_dir=str(tmp_path))
    assert found == [str(tmp_path / "torch" / "lib")]


def test_a_cpu_build_has_no_cuda_folders(tmp_path):
    assert frozen.cuda_dll_dirs([str(tmp_path)], frozen=True, bundle_dir=str(tmp_path)) == []


def test_whisper_loading_uses_cuda_dll_dirs():
    import inspect
    from zeroflow import stt
    assert "cuda_dll_dirs" in inspect.getsource(stt.load_whisper_model)


# ---------------------------------------------------------------- a windowed build's streams
def test_missing_streams_are_reopened_from_the_handles_windows_gave():
    """A windowed build sets sys.stdout to None even when the parent passed a pipe; the AI
    test reads its answer from that pipe."""
    fake = types.SimpleNamespace(stdin=None, stdout=None, stderr=io.StringIO())
    kept = fake.stderr
    frozen.reopen_std_streams(fake, opener=lambda fd, mode, **kw: f"stream {fd} {mode}")
    assert fake.stdin == "stream 0 r" and fake.stdout == "stream 1 w"
    assert fake.stderr is kept                      # a working stream is left alone


def test_a_stream_with_no_handle_becomes_a_sink():
    def no_handle(fd, mode, **kw):
        raise OSError("bad file descriptor")
    fake = types.SimpleNamespace(stdin=None, stdout=None, stderr=None)
    frozen.reopen_std_streams(fake, opener=no_handle)
    print("nothing", file=fake.stdout)                # must not raise
    fake.stderr.write("nothing")
