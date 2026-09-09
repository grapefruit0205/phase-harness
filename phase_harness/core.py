"""Core runner and migration support for phase-harness.

The runner deliberately has two roles: implementation and independent
verification.  It stores exact command, prompt, streams, result and input
fingerprints under the configured private state directory.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable


IMPLEMENT_MODEL = "gpt-5.6-sol"
IMPLEMENT_EFFORT = "medium"
VERIFY_MODEL = "gpt-6-astra"
VERIFY_EFFORT = "high"
STATUSES = {"pending", "implementing", "ready_verify", "verifying", "completed", "blocked"}
DEFAULT_IGNORED_DIRS = {
    ".git", ".hg", ".orchestrator", ".pytest_cache", ".venv", "__pycache__",
    "node_modules", "dist", "build", "coverage", ".next", ".mypy_cache",
}
DEFAULT_IGNORED_NAMES = {".DS_Store", ".coverage"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


class HarnessError(RuntimeError):
    """A safe, user-actionable harness failure."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HarnessError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessError(f"invalid JSON in {path}: {exc}") from exc


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


def _relative(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise HarnessError(f"{label} must be a safe project-relative path: {value!r}")
    return path.as_posix()


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or config.get("schema_version") != 2:
        raise HarnessError("orchestration config must use schema_version 2")
    if set(config.get("roles", {})) != {"implement", "verify"}:
        raise HarnessError("roles must contain exactly implement and verify")
    expected = {
        "implement": (IMPLEMENT_MODEL, IMPLEMENT_EFFORT),
        "verify": (VERIFY_MODEL, VERIFY_EFFORT),
    }
    for role, (model, effort) in expected.items():
        value = config["roles"][role]
        if value != {"model": model, "reasoning_effort": effort}:
            raise HarnessError(f"{role} must use {model} with {effort} effort")
    state_dir = _relative(config.get("state_dir", ".orchestrator/v2"), "state_dir")
    if state_dir == ".orchestrator" or not state_dir.startswith(".orchestrator/"):
        raise HarnessError("state_dir must be below .orchestrator/")
    phases = config.get("phases")
    if not isinstance(phases, list) or not phases:
        raise HarnessError("phases must be a non-empty array")
    ids: set[str] = set()
    for phase in phases:
        if not isinstance(phase, dict) or not isinstance(phase.get("id"), str):
            raise HarnessError("every phase needs a string id")
        phase_id = phase["id"]
        if phase_id in ids:
            raise HarnessError(f"duplicate phase id: {phase_id}")
        ids.add(phase_id)
        _relative(phase.get("instruction", ""), f"{phase_id}.instruction")
        _relative(phase.get("verification_report", ""), f"{phase_id}.verification_report")
        groups = phase.get("fingerprint_groups")
        if not isinstance(groups, dict) or not groups:
            raise HarnessError(f"{phase_id} needs fingerprint_groups")
        for name, paths in groups.items():
            if not isinstance(name, str) or not isinstance(paths, list) or not paths:
                raise HarnessError(f"{phase_id} fingerprint groups must be non-empty lists")
            for item in paths:
                _relative(item, f"{phase_id}.{name}")
        checks = phase.get("mandatory_checks", {})
        if set(checks) != {"implement", "verify"}:
            raise HarnessError(f"{phase_id} mandatory_checks needs implement and verify")
        for role, names in checks.items():
            if not isinstance(names, list) or not names or any(not isinstance(x, str) for x in names):
                raise HarnessError(f"{phase_id}.{role} mandatory checks must be strings")
        dependencies = phase.get("dependencies", [])
        if not isinstance(dependencies, list) or any(x not in ids for x in dependencies):
            raise HarnessError(f"{phase_id} dependencies must name earlier phases")
    timeout = config.get("timeout_seconds", 3600)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 60 <= timeout <= 14400:
        raise HarnessError("timeout_seconds must be between 60 and 14400")
    return config


def initial_progress(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "updated_at": None,
        "phases": {
            phase["id"]: {
                "status": "pending", "attempts": {"implement": 0, "verify": 0},
                "runs": [], "implementation_input": None, "completed_input": None,
                "blocker": None,
            }
            for phase in config["phases"]
        },
    }


def validate_progress(progress: Any, config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(progress, dict) or progress.get("schema_version") != 2:
        raise HarnessError("progress must use schema_version 2")
    expected = [p["id"] for p in config["phases"]]
    if list(progress.get("phases", {})) != expected:
        raise HarnessError("progress phase order must match orchestration config")
    for phase_id, state in progress["phases"].items():
        if not isinstance(state, dict) or state.get("status") not in STATUSES:
            raise HarnessError(f"invalid status for {phase_id}")
        attempts = state.get("attempts")
        if not isinstance(attempts, dict) or set(attempts) != {"implement", "verify"}:
            raise HarnessError(f"invalid attempts for {phase_id}")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in attempts.values()):
            raise HarnessError(f"invalid attempt count for {phase_id}")
        if not isinstance(state.get("runs"), list):
            raise HarnessError(f"invalid runs for {phase_id}")
    return progress


def _ignored(path: PurePosixPath, extra_dirs: set[str], extra_names: set[str]) -> bool:
    if any(part in DEFAULT_IGNORED_DIRS | extra_dirs for part in path.parts):
        return True
    name = path.name
    if name in DEFAULT_IGNORED_NAMES | extra_names or name.startswith(".env"):
        return True
    return path.suffix.lower() in SECRET_SUFFIXES


def collect_files(
    root: Path, selected: Iterable[str], *, ignored_dirs: Iterable[str] = (),
    ignored_names: Iterable[str] = (), missing_ok: bool = False,
) -> dict[str, str]:
    """Return sorted project-relative SHA-256 entries; reject selected symlinks."""
    found: dict[str, str] = {}
    extra_dirs, extra_names = set(ignored_dirs), set(ignored_names)
    for raw in sorted(set(selected)):
        rel = _relative(raw, "fingerprint path")
        path = root / rel
        try:
            path.lstat()
        except FileNotFoundError:
            if missing_ok:
                continue
            raise HarnessError(f"selected fingerprint path is missing: {rel}")
        if path.is_symlink():
            raise HarnessError(f"selected fingerprint path is a symlink: {rel}")
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for candidate in candidates:
            relative = PurePosixPath(candidate.relative_to(root).as_posix())
            if _ignored(relative, extra_dirs, extra_names):
                continue
            if candidate.is_symlink():
                raise HarnessError(f"selected fingerprint entry is a symlink: {relative}")
            if candidate.is_file():
                found[relative.as_posix()] = _file_sha(candidate)
    return dict(sorted(found.items()))


def fingerprint_groups(root: Path, phase: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    policy = config.get("fingerprint_policy", {})
    groups: dict[str, Any] = {}
    for name, selected in sorted(phase["fingerprint_groups"].items()):
        files = collect_files(
            root, selected, ignored_dirs=policy.get("ignored_directories", []),
            ignored_names=policy.get("ignored_files", []),
        )
        payload = "".join(f"{path}\0{digest}\n" for path, digest in files.items()).encode()
        groups[name] = {"sha256": _sha(payload), "files": files}
    combined = "".join(f"{name}\0{value['sha256']}\n" for name, value in groups.items()).encode()
    return {"sha256": _sha(combined), "groups": groups}


def _tree_snapshot(root: Path, config: dict[str, Any]) -> dict[str, str]:
    policy = config.get("fingerprint_policy", {})
    selected = [item.name for item in root.iterdir() if item.name != ".orchestrator"]
    return collect_files(
        root, selected, ignored_dirs=policy.get("ignored_directories", []),
        ignored_names=policy.get("ignored_files", []), missing_ok=True,
    )


def _result_ok(result: Any, mandatory: list[str]) -> tuple[bool, str | None]:
    if not isinstance(result, dict):
        return False, "role did not return a JSON object"
    if result.get("status") != "passed":
        return False, str(result.get("summary") or "role did not pass")
    if result.get("blockers") != []:
        return False, "passed result must have an empty blockers array"
    checks = result.get("checks")
    if not isinstance(checks, list):
        return False, "result checks must be an array"
    failed = sorted(
        str(c.get("name")) for c in checks
        if isinstance(c, dict) and c.get("status") in {"failed", "not_run"}
    )
    if failed:
        return False, "reported checks did not pass: " + ", ".join(failed)
    passed = {c.get("name") for c in checks if isinstance(c, dict) and c.get("status") == "passed"}
    missing = sorted(set(mandatory) - passed)
    if missing:
        return False, "mandatory checks not passed: " + ", ".join(missing)
    return True, None


@dataclass
class Execution:
    exit_code: int | None
    stdout: str
    stderr: str
    result: Any
    error: str | None = None
    timed_out: bool = False


Executor = Callable[[list[str], str, int, Path], Execution]


def subprocess_executor(argv: list[str], prompt: str, timeout: int, result_path: Path) -> Execution:
    process = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return Execution(process.returncode, stdout, stderr, None, "execution timed out", True)
    try:
        result = _load(result_path)
    except HarnessError as exc:
        return Execution(process.returncode, stdout, stderr, None, str(exc))
    return Execution(process.returncode, stdout, stderr, result)


class PhaseRunner:
    def __init__(
        self, root: Path, executor: Executor = subprocess_executor, *, allow_deploy: bool = False
    ) -> None:
        self.root = root.resolve()
        self.config_path = self.root / "orchestration.json"
        self.progress_path = self.root / "progress.json"
        self.config = validate_config(_load(self.config_path))
        self.progress = validate_progress(_load(self.progress_path), self.config)
        self.state_dir = self.root / self.config.get("state_dir", ".orchestrator/v2")
        self.executor = executor
        self.allow_deploy = allow_deploy
        self._lock_stream: Any = None

    def __enter__(self) -> "PhaseRunner":
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock_stream = (self.state_dir / "runner.lock").open("a+")
        try:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lock_stream.close()
            raise HarnessError("another phase-harness process holds the project lock") from exc
        return self

    def __exit__(self, *_args: Any) -> None:
        if self._lock_stream:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_UN)
            self._lock_stream.close()

    def _save(self) -> None:
        self.progress["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        atomic_json(self.progress_path, self.progress)

    def plan(self, through: str | None = None) -> list[dict[str, str]]:
        if through is not None:
            self._phase(through)
        plan: list[dict[str, str]] = []
        for phase in self.config["phases"]:
            state = self.progress["phases"][phase["id"]]
            if state["status"] == "completed":
                if phase["id"] == through:
                    break
                continue
            role = "verify" if state["status"] == "ready_verify" else "implement"
            plan.append({"phase": phase["id"], "status": state["status"], "next_role": role})
            if phase["id"] == through:
                break
        return plan

    def _phase(self, phase_id: str) -> dict[str, Any]:
        for phase in self.config["phases"]:
            if phase["id"] == phase_id:
                return phase
        raise HarnessError(f"unknown phase: {phase_id}")

    def _dependencies_done(self, phase: dict[str, Any]) -> None:
        missing = [d for d in phase.get("dependencies", []) if self.progress["phases"][d]["status"] != "completed"]
        if missing:
            raise HarnessError(f"{phase['id']} dependencies are incomplete: {', '.join(missing)}")

    def _deployment_allowed(self, phase: dict[str, Any]) -> None:
        if not phase.get("deployment", False):
            return
        if not self.allow_deploy:
            raise HarnessError(f"{phase['id']} is a deployment phase; pass --allow-deploy explicitly")
        configured = phase.get("deployment_config_paths", [])
        if not configured:
            raise HarnessError(f"{phase['id']} has no deployment_config_paths guard")
        project = _load(self.root / "project.config.json")
        for dotted in configured:
            value: Any = project
            for key in dotted.split("."):
                value = value.get(key) if isinstance(value, dict) else None
            if value in {None, ""}:
                raise HarnessError(f"deployment setting is not configured: {dotted}")

    def _prompt(self, role: str, phase: dict[str, Any], inputs: dict[str, Any], repair: bool) -> str:
        instruction = (self.root / phase["instruction"]).read_text(encoding="utf-8")
        report = phase["verification_report"]
        checks = ", ".join(phase["mandatory_checks"][role])
        history = self.progress["phases"][phase["id"]].get("blocker")
        action = "Correct only the recorded failure." if repair else "Perform the assigned role once."
        boundary = (
            f"You may edit project implementation files, but do not run this harness recursively."
            if role == "implement" else
            f"Do not modify product, source, design, tests, or dependencies. You may write only {report}."
        )
        return (
            f"Role: {role}\nPhase: {phase['id']}\n{action}\n{boundary}\n"
            f"Mandatory checks: {checks}\nInput fingerprint: {inputs['sha256']}\n"
            f"Prior blocker: {history or 'none'}\n\nPhase instructions:\n{instruction}\n\n"
            "Return the required JSON result. A pass requires every mandatory check to have run "
            "and passed, and no actual product blocker. Nonmandatory style observations are advisory.\n"
        )

    def _argv(self, role: str, result_path: Path) -> list[str]:
        model, effort = (
            (IMPLEMENT_MODEL, IMPLEMENT_EFFORT) if role == "implement" else (VERIFY_MODEL, VERIFY_EFFORT)
        )
        return [
            "codex", "--disable", "plugins", "exec", "-C", str(self.root),
            "--skip-git-repo-check", "-m", model, "-c",
            f'model_reasoning_effort="{effort}"', "--output-schema",
            str(Path(__file__).with_name("agent-result.schema.json")),
            "--output-last-message", str(result_path), "-",
        ]

    def _run_role(self, phase: dict[str, Any], role: str, *, repair: bool = False) -> bool:
        phase_id = phase["id"]
        state = self.progress["phases"][phase_id]
        inputs = fingerprint_groups(self.root, phase, self.config)
        if role == "verify" and state.get("implementation_input") != inputs["sha256"]:
            state["status"] = "blocked"
            state["blocker"] = "verification inputs changed after implementation"
            self._save()
            return False
        state["status"] = "implementing" if role == "implement" else "verifying"
        state["attempts"][role] += 1
        self._save()
        run_id = f"{phase_id}-{role}-{state['attempts'][role]}-{uuid.uuid4().hex[:8]}"
        run_dir = self.state_dir / phase_id / run_id
        run_dir.mkdir(parents=True)
        result_path = run_dir / "result.json"
        prompt = self._prompt(role, phase, inputs, repair)
        argv = self._argv(role, result_path)
        (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        atomic_json(run_dir / "inputs.json", inputs)
        report_path = self.root / phase["verification_report"]
        if role == "verify" and report_path.is_file():
            (run_dir / "verification-report-before.md").write_bytes(report_path.read_bytes())
        before = _tree_snapshot(self.root, self.config) if role == "verify" else None
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            execution = self.executor(argv, prompt, self.config.get("timeout_seconds", 3600), result_path)
        except (OSError, HarnessError) as exc:
            execution = Execution(None, "", "", None, str(exc))
        (run_dir / "stdout.txt").write_text(execution.stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(execution.stderr, encoding="utf-8")
        post_error = None
        try:
            after_inputs = fingerprint_groups(self.root, phase, self.config)
        except HarnessError as exc:
            after_inputs = inputs
            post_error = str(exc)
        mutation_error = None
        if role == "verify":
            after = _tree_snapshot(self.root, self.config)
            allowed = phase["verification_report"]
            changed = sorted(path for path in set(before or {}) | set(after) if (before or {}).get(path) != after.get(path))
            illegal = [path for path in changed if path != allowed]
            if illegal:
                mutation_error = "verifier changed forbidden paths: " + ", ".join(illegal)
            if after_inputs["sha256"] != inputs["sha256"]:
                mutation_error = mutation_error or "verifier changed fingerprinted inputs"
        ok, result_error = _result_ok(execution.result, phase["mandatory_checks"][role])
        error = execution.error or (f"process exited with {execution.exit_code}" if execution.exit_code != 0 else None) or post_error or mutation_error or result_error
        ok = bool(ok and execution.exit_code == 0 and not error)
        receipt = {
            "schema_version": 2, "phase": phase_id, "role": role,
            "attempt": state["attempts"][role], "model": argv[argv.index("-m") + 1],
            "reasoning_effort": IMPLEMENT_EFFORT if role == "implement" else VERIFY_EFFORT,
            "command": argv, "started_at": started,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "exit_code": execution.exit_code, "timed_out": execution.timed_out,
            "prompt_sha256": _sha(prompt.encode()), "stdout_sha256": _sha(execution.stdout.encode()),
            "stderr_sha256": _sha(execution.stderr.encode()), "input_sha256": inputs["sha256"],
            "result": execution.result, "status": "passed" if ok else "blocked", "error": error,
            "config_sha256": _file_sha(self.config_path),
            "harness_fingerprint": "phase-harness:2.0.0",
            "instruction_sha256": _file_sha(self.root / phase["instruction"]),
        }
        atomic_json(run_dir / "receipt.json", receipt)
        state["runs"].append(str((run_dir / "receipt.json").relative_to(self.root)))
        if ok and role == "implement":
            state["status"] = "ready_verify"
            state["implementation_input"] = after_inputs["sha256"]
            state["blocker"] = None
        elif ok:
            state["status"] = "completed"
            state["completed_input"] = inputs["sha256"]
            state["blocker"] = None
        else:
            state["status"] = "blocked"
            state["blocker"] = error
        self._save()
        return ok

    def run(self, through: str | None = None) -> bool:
        """Run each selected phase once-through; stop on the first failure."""
        if through is not None:
            self._phase(through)
        for phase in self.config["phases"]:
            phase_id = phase["id"]
            state = self.progress["phases"][phase_id]
            if state["status"] == "completed":
                if phase_id == through:
                    return True
                continue
            if state["status"] == "blocked":
                return False
            if state["status"] in {"implementing", "verifying"}:
                interrupted_role = "implement" if state["status"] == "implementing" else "verify"
                state["status"] = "blocked"
                state["blocker"] = f"interrupted {interrupted_role} role requires explicit recovery"
                self._save()
                return False
            self._dependencies_done(phase)
            self._deployment_allowed(phase)
            if state["status"] == "pending" and not self._run_role(phase, "implement"):
                return False
            if self.progress["phases"][phase_id]["status"] == "ready_verify" and not self._run_role(phase, "verify"):
                return False
            if phase_id == through:
                return True
        return True

    def repair(self, phase_id: str) -> bool:
        phase = self._phase(phase_id)
        state = self.progress["phases"][phase_id]
        if state["status"] != "blocked":
            raise HarnessError("--repair requires a blocked phase")
        self._dependencies_done(phase)
        self._deployment_allowed(phase)
        return self._run_role(phase, "implement", repair=True)

    def retry_verify(self, phase_id: str) -> bool:
        phase = self._phase(phase_id)
        state = self.progress["phases"][phase_id]
        if state["status"] not in {"blocked", "ready_verify"} or not state.get("implementation_input"):
            raise HarnessError("verify retry requires an implemented phase")
        self._dependencies_done(phase)
        self._deployment_allowed(phase)
        state["status"] = "ready_verify"
        return self._run_role(phase, "verify", repair=True)


def _validate_legacy_receipt(receipt_path: Path, phase_id: str, role: str) -> dict[str, Any]:
    receipt = _load(receipt_path)
    if not isinstance(receipt, dict) or receipt.get("phase") != phase_id or receipt.get("role") != role:
        raise HarnessError("legacy receipt phase/role mismatch")
    if receipt.get("exit_code") != 0 or receipt.get("finished_at") is None:
        raise HarnessError("legacy receipt does not record a completed exit-0 run")
    if receipt.get("error") is not None or receipt.get("status") == "blocked":
        raise HarnessError("legacy receipt records a harness error or blocked status")
    result = receipt.get("result")
    if not isinstance(result, dict) or result.get("status") != "passed" or result.get("blockers") != []:
        raise HarnessError("legacy receipt result is not passed and blocker-free")
    result_path = receipt_path.with_name("result.json")
    if result_path.is_file() and _load(result_path) != result:
        raise HarnessError("legacy result.json differs from receipt result")
    return receipt


def import_legacy_phase(
    root: Path, config_path: Path, progress_path: Path, *, phase_id: str,
    receipt_path: Path, target_status: str, snapshot_path: Path | None = None,
    baseline_roots: Iterable[str] = (), authorized_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Validated one-phase import used before the new runner is activated.

    ``ready_verify`` imports require a passed implement receipt and an exact
    snapshot comparison. ``completed`` imports require a passed verify receipt.
    """
    root = root.resolve()
    config = validate_config(_load(config_path))
    progress = validate_progress(_load(progress_path), config)
    if target_status not in {"ready_verify", "completed"}:
        raise HarnessError("legacy target must be ready_verify or completed")
    role = "implement" if target_status == "ready_verify" else "verify"
    receipt = _validate_legacy_receipt(receipt_path, phase_id, role)
    if target_status == "ready_verify":
        if snapshot_path is None:
            raise HarnessError("ready_verify import requires a workspace snapshot")
        snapshot_bytes = snapshot_path.read_bytes()
        recorded = receipt.get("workspace_snapshot_after_sha256")
        if recorded != _sha(snapshot_bytes):
            raise HarnessError("legacy snapshot hash does not match receipt")
        snapshot = json.loads(snapshot_bytes)
        entries = snapshot.get("files") if isinstance(snapshot, dict) else None
        if not isinstance(entries, list):
            raise HarnessError("legacy snapshot files are invalid")
        baseline_roots = list(baseline_roots)
        if not baseline_roots:
            raise HarnessError("ready_verify import requires at least one baseline root")
        authorized = set(authorized_paths)
        expected = {
            item["path"]: item["sha256"] for item in entries
            if isinstance(item, dict) and item.get("kind") == "file" and item.get("path") not in authorized
        }
        selected_expected = {
            path: digest for path, digest in expected.items()
            if any(path == base or path.startswith(base.rstrip("/") + "/") for base in baseline_roots)
        }
        if not selected_expected:
            raise HarnessError("legacy snapshot contains no files in the selected baseline")
        current = collect_files(root, baseline_roots)
        current = {path: digest for path, digest in current.items() if path not in authorized}
        if current != selected_expected:
            added = sorted(current.keys() - selected_expected.keys())
            deleted = sorted(selected_expected.keys() - current.keys())
            changed = sorted(path for path in current.keys() & selected_expected.keys() if current[path] != selected_expected[path])
            raise HarnessError(
                "legacy product snapshot mismatch; "
                f"added={added}, deleted={deleted}, changed={changed}"
            )
    phase = next((p for p in config["phases"] if p["id"] == phase_id), None)
    if phase is None:
        raise HarnessError(f"unknown phase: {phase_id}")
    inputs = fingerprint_groups(root, phase, config)
    state = progress["phases"][phase_id]
    if state["status"] != "pending":
        raise HarnessError(f"{phase_id} is not pending")
    state["status"] = target_status
    state["attempts"][role] = 1
    state["runs"].append(str(receipt_path.resolve()))
    state["blocker"] = None
    if target_status == "ready_verify":
        state["implementation_input"] = inputs["sha256"]
    else:
        state["completed_input"] = inputs["sha256"]
    progress["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    atomic_json(progress_path, progress)
    return progress
