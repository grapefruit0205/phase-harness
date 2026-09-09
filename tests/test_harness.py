from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from phase_harness.core import (
    Execution,
    HarnessError,
    PhaseRunner,
    atomic_json,
    collect_files,
    import_legacy_phase,
    initial_progress,
    validate_config,
)


def config(two_phases: bool = False, deployment: bool = False) -> dict:
    phases = []
    for index in range(1, 3 if two_phases else 2):
        phase_id = f"P{index:02d}"
        phase = {
            "id": phase_id,
            "name": f"Phase {index}",
            "instruction": f"phases/{phase_id}.md",
            "verification_report": f"reports/{phase_id}.md",
            "dependencies": [] if index == 1 else ["P01"],
            "mandatory_checks": {"implement": ["unit"], "verify": ["acceptance"]},
            "fingerprint_groups": {
                "product": ["src"], "tests": ["tests"],
                "dependencies": ["pyproject.toml"],
                "current_phase": [f"phases/{phase_id}.md"],
                "design": [f"design/{phase_id}.md"], "source": ["fixtures"],
            },
        }
        if deployment:
            phase.update(deployment=True, deployment_config_paths=["aws.account_id", "aws.region"])
        phases.append(phase)
    return {
        "schema_version": 2, "state_dir": ".orchestrator/v2", "timeout_seconds": 60,
        "roles": {
            "implement": {"model": "gpt-5.6-sol", "reasoning_effort": "medium"},
            "verify": {"model": "gpt-6-astra", "reasoning_effort": "high"},
        },
        "phases": phases,
    }


class Project:
    def __init__(self, testcase: unittest.TestCase, *, two_phases: bool = False, deployment: bool = False):
        self.temp = tempfile.TemporaryDirectory()
        testcase.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = config(two_phases, deployment)
        for folder in ("src", "tests", "phases", "design", "fixtures", "reports"):
            (self.root / folder).mkdir()
        (self.root / "src/app.py").write_text("VALUE = 1\n")
        (self.root / "tests/test_app.py").write_text("pass\n")
        (self.root / "fixtures/input.json").write_text("{}\n")
        (self.root / "pyproject.toml").write_text("[project]\nname='sample'\n")
        for phase in self.config["phases"]:
            (self.root / phase["instruction"]).write_text("Do the synthetic work.\n")
            (self.root / f"design/{phase['id']}.md").write_text("Synthetic design.\n")
        atomic_json(self.root / "orchestration.json", self.config)
        atomic_json(self.root / "progress.json", initial_progress(validate_config(self.config)))


class FakeExecutor:
    def __init__(self, root: Path, *, fail_role: str | None = None, mutate_verify: bool = False):
        self.root = root
        self.fail_role = fail_role
        self.mutate_verify = mutate_verify
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], prompt: str, timeout: int, result_path: Path) -> Execution:
        self.calls.append(argv)
        role = "implement" if "gpt-5.6-sol" in argv else "verify"
        phase = prompt.split("Phase: ", 1)[1].splitlines()[0]
        if role == "verify":
            (self.root / f"reports/{phase}.md").write_text("verified\n")
            if self.mutate_verify:
                (self.root / "src/app.py").write_text("BAD = True\n")
        failed = role == self.fail_role
        check = "unit" if role == "implement" else "acceptance"
        result = {
            "status": "blocked" if failed else "passed", "summary": "synthetic result",
            "artifacts": [], "checks": [{"name": check, "status": "failed" if failed else "passed", "evidence": "fake"}],
            "blockers": ["synthetic failure"] if failed else [],
        }
        atomic_json(result_path, result)
        return Execution(1 if failed else 0, "fake stdout\n", "fake stderr\n", result)


class HarnessTests(unittest.TestCase):
    def test_unknown_through_and_interrupted_state_fail_closed(self):
        project = Project(self)
        fake = FakeExecutor(project.root)
        with PhaseRunner(project.root, fake) as runner:
            with self.assertRaises(HarnessError):
                runner.run("P999")
        progress = json.loads((project.root / "progress.json").read_text())
        progress["phases"]["P01"]["status"] = "implementing"
        atomic_json(project.root / "progress.json", progress)
        with PhaseRunner(project.root, fake) as runner:
            self.assertFalse(runner.run("P01"))
        self.assertEqual(fake.calls, [])
        self.assertEqual(json.loads((project.root / "progress.json").read_text())["phases"]["P01"]["status"], "blocked")

    def test_exact_models_efforts_and_no_gemini(self):
        project, fake = Project(self), None
        fake = FakeExecutor(project.root)
        with PhaseRunner(project.root, fake) as runner:
            self.assertTrue(runner.run("P01"))
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[0][:9], ["codex", "--disable", "plugins", "exec", "-C", str(project.root), "--skip-git-repo-check", "-m", "gpt-5.6-sol"])
        self.assertIn('model_reasoning_effort="medium"', fake.calls[0])
        self.assertIn("gpt-6-astra", fake.calls[1])
        self.assertIn('model_reasoning_effort="high"', fake.calls[1])
        self.assertNotIn("gemini", " ".join(sum(fake.calls, [])))

    def test_once_through_immediately_advances(self):
        project = Project(self, two_phases=True)
        fake = FakeExecutor(project.root)
        with PhaseRunner(project.root, fake) as runner:
            self.assertTrue(runner.run("P02"))
        progress = json.loads((project.root / "progress.json").read_text())
        self.assertEqual([x["status"] for x in progress["phases"].values()], ["completed", "completed"])
        self.assertEqual(len(fake.calls), 4)

    def test_failure_stops_without_loop(self):
        project = Project(self, two_phases=True)
        fake = FakeExecutor(project.root, fail_role="implement")
        with PhaseRunner(project.root, fake) as runner:
            self.assertFalse(runner.run("P02"))
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(json.loads((project.root / "progress.json").read_text())["phases"]["P02"]["status"], "pending")

    def test_changed_verification_input_is_rejected(self):
        project = Project(self)
        fake = FakeExecutor(project.root, mutate_verify=True)
        with PhaseRunner(project.root, fake) as runner:
            self.assertFalse(runner.run("P01"))
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(json.loads((project.root / "progress.json").read_text())["phases"]["P01"]["status"], "blocked")

    def test_cache_exclusion_and_source_addition(self):
        project = Project(self)
        before = collect_files(project.root, ["fixtures"])
        (project.root / "fixtures/__pycache__").mkdir()
        (project.root / "fixtures/__pycache__/junk.pyc").write_bytes(b"junk")
        self.assertEqual(collect_files(project.root, ["fixtures"]), before)
        (project.root / "fixtures/new.json").write_text("{}\n")
        self.assertNotEqual(collect_files(project.root, ["fixtures"]), before)

    def test_lock_and_atomic_progress(self):
        project = Project(self)
        first = PhaseRunner(project.root)
        first.__enter__()
        self.addCleanup(first.__exit__, None, None, None)
        with self.assertRaises(HarnessError):
            PhaseRunner(project.root).__enter__()
        parsed = json.loads((project.root / "progress.json").read_text())
        self.assertEqual(parsed["schema_version"], 2)

    def test_deployment_guard(self):
        project = Project(self, deployment=True)
        fake = FakeExecutor(project.root)
        with PhaseRunner(project.root, fake) as runner:
            with self.assertRaises(HarnessError):
                runner.run("P01")
        atomic_json(project.root / "project.config.json", {"aws": {"account_id": None, "region": None}})
        with PhaseRunner(project.root, fake, allow_deploy=True) as runner:
            with self.assertRaises(HarnessError):
                runner.run("P01")
        self.assertEqual(fake.calls, [])

    def test_legacy_import_ready_verify_and_detects_change(self):
        project = Project(self)
        run = project.root / "legacy"
        run.mkdir()
        files = collect_files(project.root, ["src"])
        snapshot = {"schema_version": 1, "phase": "P01", "files": [
            {"path": path, "kind": "file", "bytes": (project.root / path).stat().st_size, "sha256": digest}
            for path, digest in files.items()
        ]}
        snapshot_path = run / "workspace-after.json"
        snapshot_path.write_text(json.dumps(snapshot))
        result = {"status": "passed", "summary": "legacy", "artifacts": [], "checks": [], "blockers": []}
        atomic_json(run / "result.json", result)
        receipt = {"phase": "P01", "role": "implement", "exit_code": 0, "finished_at": "now", "result": result,
                   "workspace_snapshot_after_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                   "model": "gpt-5.6-sol", "reasoning_effort": "max"}
        atomic_json(run / "receipt.json", receipt)
        import_legacy_phase(project.root, project.root / "orchestration.json", project.root / "progress.json",
                            phase_id="P01", receipt_path=run / "receipt.json", target_status="ready_verify",
                            snapshot_path=snapshot_path, baseline_roots=["src"])
        state = json.loads((project.root / "progress.json").read_text())["phases"]["P01"]
        self.assertEqual(state["status"], "ready_verify")
        self.assertEqual(receipt["reasoning_effort"], "max")

        changed = Project(self)
        (changed.root / "src/added.py").write_text("new\n")
        other = changed.root / "legacy"
        other.mkdir()
        other_snapshot = other / "workspace-after.json"
        other_snapshot.write_text(json.dumps(snapshot))
        receipt["workspace_snapshot_after_sha256"] = hashlib.sha256(other_snapshot.read_bytes()).hexdigest()
        atomic_json(other / "receipt.json", receipt)
        atomic_json(other / "result.json", result)
        with self.assertRaisesRegex(HarnessError, "added=.*src/added.py"):
            import_legacy_phase(changed.root, changed.root / "orchestration.json", changed.root / "progress.json",
                                phase_id="P01", receipt_path=other / "receipt.json", target_status="ready_verify",
                                snapshot_path=other_snapshot, baseline_roots=["src"])

        empty = Project(self)
        empty_run = empty.root / "legacy"
        empty_run.mkdir()
        empty_snapshot = empty_run / "workspace-after.json"
        empty_snapshot.write_text(json.dumps(snapshot))
        receipt["workspace_snapshot_after_sha256"] = hashlib.sha256(empty_snapshot.read_bytes()).hexdigest()
        atomic_json(empty_run / "receipt.json", receipt)
        atomic_json(empty_run / "result.json", result)
        with self.assertRaisesRegex(HarnessError, "baseline root"):
            import_legacy_phase(empty.root, empty.root / "orchestration.json", empty.root / "progress.json",
                                phase_id="P01", receipt_path=empty_run / "receipt.json", target_status="ready_verify",
                                snapshot_path=empty_snapshot)

        blocked = Project(self)
        blocked_run = blocked.root / "legacy"
        blocked_run.mkdir()
        blocked_snapshot = blocked_run / "workspace-after.json"
        blocked_snapshot.write_text(json.dumps(snapshot))
        receipt["workspace_snapshot_after_sha256"] = hashlib.sha256(blocked_snapshot.read_bytes()).hexdigest()
        receipt["error"] = "post-run mutation"
        atomic_json(blocked_run / "receipt.json", receipt)
        atomic_json(blocked_run / "result.json", result)
        with self.assertRaisesRegex(HarnessError, "harness error"):
            import_legacy_phase(blocked.root, blocked.root / "orchestration.json", blocked.root / "progress.json",
                                phase_id="P01", receipt_path=blocked_run / "receipt.json", target_status="ready_verify",
                                snapshot_path=blocked_snapshot, baseline_roots=["src"])


if __name__ == "__main__":
    unittest.main()
