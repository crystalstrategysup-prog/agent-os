"""Bounded command observation, not authorization, sandboxing or provenance proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import uuid


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular non-symlink input required")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input size limit")
    return data


def _save(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(data)


def run_observed(argv: list[str], *, cwd: Path, output_root: Path,
                 purpose: str, claim: str, stdin: bytes = b"",
                 script_inputs: tuple[Path, ...] = (), timeout: float = 30,
                 max_output_bytes: int = 24000) -> dict:
    """Execute caller-authorized argv; retain bounded, non-sensitive evidence.

    POSIX only. Script pins cover explicit inputs and existing .py argv files,
    not imports, interpreter, environment or mutable external state. A caller
    must declare other scripts explicitly. No shell is introduced by this API.
    """
    if os.name != "posix":
        raise ValueError("POSIX process-group observation required")
    if (not isinstance(argv, list) or not argv or
            any(not isinstance(x, str) or "\0" in x for x in argv) or not argv[0]):
        raise ValueError("nonempty typed argv required")
    if (not isinstance(stdin, bytes) or len(stdin) > 262144 or
            not 0 < timeout <= 90 or not 512 <= max_output_bytes <= 24000 or
            not purpose or not claim):
        raise ValueError("invalid bounded observation request")
    cwd = Path(cwd).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("working directory required")
    if Path(argv[0]).name.startswith("python") and "-" in argv[1:] and not stdin:
        raise ValueError("explicit Python stdin script required")
    paths = [Path(p) for p in script_inputs]
    paths.extend(Path(x) for x in argv[1:] if x.endswith(".py"))
    pins = {}
    for path in paths:
        path = path if path.is_absolute() else cwd / path
        # Keep the original leaf for post-run symlink checks.
        pins[str(path.absolute())] = _sha(_read(path, 1000000))
    identity = {"argv": argv, "cwd": str(cwd), "stdin_sha256": _sha(stdin),
                "script_pins": pins}
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    op = uuid.uuid4().hex
    row = {"schema": "agentos.observed-command/v1", "op": op,
           "purpose": purpose, "claim": claim, **identity,
           "fingerprint": _sha(json.dumps(identity, sort_keys=True).encode()),
           "stdin_bytes": len(stdin), "input_binding": "bounded-bytes/v1",
           "observer_sha256": _sha(Path(__file__).read_bytes()),
           "started_unix": time.time()}
    _save(root / (op + ".stdin"), stdin)
    row["stdin_ref"] = op + ".stdin"

    def record(event: str) -> None:
        # Caller-owned single-writer ledger; filesystem failures propagate.
        with (root / "operations.jsonl").open("a", encoding="utf-8") as stream:
            os.chmod(root / "operations.jsonl", 0o600)
            stream.write(json.dumps(dict(row, event=event), sort_keys=True) + "\n")

    record("started")
    start = time.monotonic()
    proc = None
    row.update(target_started=False, command_exit=None, wrapper_exit=70,
               output_complete=False, script_inputs_stable=False,
               status="OBSERVER_ERROR")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True)
        except OSError as error:
            row.update(status="LAUNCH_FAILED", wrapper_exit=127,
                       error_category=type(error).__name__, error_errno=error.errno)
        else:
            row["target_started"] = True
            deadline = start + timeout
            failure = None
            with selectors.DefaultSelector() as selector:
                for name in buffers:
                    stream = getattr(proc, name)
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                if stdin:
                    os.set_blocking(proc.stdin.fileno(), False)
                    selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
                else:
                    proc.stdin.close()
                sent = 0
                while selector.get_map() or proc.poll() is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        failure = "TIMEOUT"
                        break
                    for key, _ in selector.select(min(remaining, 0.05)):
                        if key.data == "stdin":
                            try:
                                sent += os.write(key.fd, stdin[sent:sent + 65536])
                            except BrokenPipeError:
                                sent = len(stdin)
                            if sent == len(stdin):
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                        else:
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                            else:
                                available = max_output_bytes - sum(map(len, buffers.values()))
                                buffers[key.data].extend(chunk[:available])
                                if len(chunk) > available:
                                    failure = "OUTPUT_LIMIT"
                                    break
                    if failure:
                        break
            if failure:
                row.update(status=failure, wrapper_exit=124 if failure == "TIMEOUT" else 65)
            else:
                row.update(status="FINISHED", wrapper_exit=proc.wait())
                row["output_complete"] = True
    except Exception as error:
        row.update(status="OBSERVER_ERROR", wrapper_exit=70,
                   output_complete=False, error_category=type(error).__name__)
    finally:
        if proc is not None:
            # Kill remaining group members even when the leader already exited.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
            row["command_exit"] = proc.returncode
            try:
                stable = all(_sha(_read(Path(p), 1000000)) == sha for p, sha in pins.items())
            except (OSError, ValueError):
                stable = False
            row["script_inputs_stable"] = stable
            if not stable:
                row.update(status="INPUT_CHANGED", wrapper_exit=66, output_complete=False)
        row["seconds"] = time.monotonic() - start
        try:
            for name, data in buffers.items():
                row[name + "_captured_bytes"] = len(data)
                row[name + "_sha256"] = _sha(data)
                if row["output_complete"]:
                    ref = op + "." + name
                    _save(root / ref, data)
                    row[name + "_ref"] = ref
        except OSError as error:
            row.update(status="ARTIFACT_ERROR", wrapper_exit=70,
                       output_complete=False, error_category=type(error).__name__)
        row["event"] = "finished"
        record("finished")
    return row


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--claim", required=True)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--stdin-file", type=Path)
    parser.add_argument("--script-input", action="append", default=[], type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-output-bytes", type=int, default=24000)
    if args in (["-h"], ["--help"]):
        parser.parse_args(args)
    if "--" not in args:
        parser.error("explicit -- command separator required")
    split = args.index("--")
    # parse_args rejects all stray words before the separator, including an
    # accidentally unquoted multiword --claim; none can become an executable.
    options = parser.parse_args(args[:split])
    try:
        payload = _read(options.stdin_file, 262144) if options.stdin_file else b""
        row = run_observed(args[split + 1:], cwd=options.cwd,
                           output_root=options.output_root, purpose=options.purpose,
                           claim=options.claim, stdin=payload,
                           script_inputs=tuple(options.script_input),
                           timeout=options.timeout, max_output_bytes=options.max_output_bytes)
    except (ValueError, OSError) as error:
        parser.error(type(error).__name__ + ": invalid observation input or storage")
    print(json.dumps(row, sort_keys=True))
    return row["wrapper_exit"] if 0 <= row["wrapper_exit"] <= 255 else 1


if __name__ == "__main__":
    raise SystemExit(main())
