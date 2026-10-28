"""Load the maintained engine under a private namespace, without tools rebinding."""
import importlib
from pathlib import Path
import sys
import types


def load_engine(name):
    if name not in {"route_probe", "route_probe_graph", "route_probe_replay"}:
        raise ValueError("engine_name_not_supported")
    package = "_function_extractor_engine"
    if package not in sys.modules:
        module = types.ModuleType(package)
        module.__path__ = [str(Path(__file__).resolve().parents[3] / "backend" / "tools")]
        # runner→function_extractor→tools→repository: parents[3] is root.
        sys.modules[package] = module
    return importlib.import_module(package + "." + name)
