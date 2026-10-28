"""Resolve only this skill's packaged or standalone engine; no host discovery."""
from pathlib import Path
import os
import sys


def prepare(script):
    script = Path(script).resolve()
    root = script.parents[4]
    embedded = root / 'resources' / 'fe_tools'
    if not ((root / 'fe_module.py').is_file()
            and (embedded / 'tools/function_extractor/cli.py').is_file()):
        return root, root
    # A copied/symlinked installed skill may be invoked by the system Python.
    # Reuse its own existing release interpreter without installing anything.
    for parent in root.parents:
        if (parent / 'pyvenv.cfg').is_file():
            python = parent / 'bin' / 'python'
            if not python.is_file():
                raise SystemExit('packaged_interpreter_missing')
            if Path(sys.prefix).resolve() != parent.resolve():
                flags = ['-I'] if sys.flags.isolated else []
                if sys.dont_write_bytecode:
                    flags.append('-B')
                os.execv(str(python), [str(python), *flags, str(script), *sys.argv[1:]])
            break
    if sys.version_info < (3, 11):
        raise SystemExit('Python_3_11_or_newer_required')
    sys.path.insert(0, str(root.parent))
    from agent_os.module_registry import verify
    if verify()['status'] != 'PASS':
        raise SystemExit('PACKAGED_MODULE_PIN_MISMATCH')
    return embedded, Path.cwd().resolve()
