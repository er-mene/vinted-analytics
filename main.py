import sys
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

_backend = str(Path(__file__).parent / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

_path = Path(_backend) / "main.py"
spec = spec_from_file_location("backend_app", _path)
mod = module_from_spec(spec)
sys.modules["backend_app"] = mod
spec.loader.exec_module(mod)
app = mod.app
