"""REVIEW-2 DB-free guard. Blocks every socket connect, then runs either the
ha1_unit pytest suite or a named DB-free script. Attempt 1 omitted the cwd on
sys.path (a `py script.py` launch, unlike `py -m pytest`) and failed at
collection with ModuleNotFoundError: features -- a wrapper error, kept as
pytest-ha1_unit.attempt1-wrapper-syspath.out.txt."""
import os, runpy, socket, sys
sys.path.insert(0, os.getcwd())
def _refuse(*a, **k):
    raise RuntimeError("REVIEW-2 guard: socket connect attempted during DB-free run")
socket.socket.connect = _refuse
socket.socket.connect_ex = _refuse
socket.create_connection = _refuse
mode = sys.argv[1]
if mode == "pytest":
    import pytest
    code = pytest.main(["-p", "no:cacheprovider", "--confcutdir=tests/ha1_unit", "tests/ha1_unit", "-q"])
else:
    code = 0
    sys.argv = [mode]
    runpy.run_path(mode, run_name="__main__")
print("guard: app_imported=%s pymysql_imported=%s" % ("app" in sys.modules, "pymysql" in sys.modules))
sys.exit(code)
