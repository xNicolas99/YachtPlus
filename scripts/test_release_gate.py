"""Exercise publication decisions, git ref binding and the CI dependency graph."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from release_gate import REQUIRED_JOBS, ReleaseRejected, release_plan


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def evidence() -> dict:
    return {
        "event_name": "push",
        "repository": "xNicolas99/YachtPlus",
        "ref": "refs/heads/master",
        "sha": SHA,
        "checked_sha": SHA,
        "event": {
            "repository": {"full_name": "xNicolas99/YachtPlus", "fork": False},
            "ref": "refs/heads/master",
            "after": SHA,
            "deleted": False,
        },
        "needs": {job: {"result": "success"} for job in REQUIRED_JOBS},
        "cancelled": "false",
        "package": {"version": "2.1.0"},
        "lock": {"version": "2.1.0", "packages": {"": {"version": "2.1.0"}}},
        "on_release_branch": True,
    }


class PublicationPolicyTests(unittest.TestCase):
    def test_master_returns_canonical_version_and_full_checked_sha(self):
        plan = release_plan(**evidence())
        self.assertEqual(plan["image"], "ghcr.io/xnicolas99/yachtplus")
        self.assertEqual(plan["version"], "2.1.0")
        self.assertEqual(plan["tags"].splitlines(), ["2.1.0", f"sha-{SHA}", "latest"])

    def test_version_tag_does_not_move_latest(self):
        args = evidence()
        args["ref"] = args["event"]["ref"] = "refs/tags/v2.1.0"
        self.assertEqual(release_plan(**args)["tags"].splitlines(), ["2.1.0", f"sha-{SHA}"])

    def test_failed_skipped_cancelled_or_unknown_validation_never_publishes(self):
        for job in REQUIRED_JOBS:
            for status in ["failure", "skipped", "cancelled", "timed_out", "neutral", "", None]:
                with self.subTest(job=job, status=status):
                    args = evidence()
                    args["needs"][job]["result"] = status
                    with self.assertRaises(ReleaseRejected):
                        release_plan(**args)

    def test_missing_or_forged_validation_evidence_is_rejected(self):
        for needs in [{}, {"ci": {"result": "success"}}, {**evidence()["needs"], "unknown": {"result": "success"}}]:
            with self.subTest(needs=needs):
                args = evidence()
                args["needs"] = needs
                with self.assertRaises(ReleaseRejected):
                    release_plan(**args)

    def test_cancellation_and_unknown_run_state_is_rejected(self):
        for state in ["true", "", "False", None]:
            with self.subTest(state=state):
                args = evidence()
                args["cancelled"] = state
                with self.assertRaises(ReleaseRejected):
                    release_plan(**args)

    def test_pr_dispatch_and_workflow_run_cannot_publish(self):
        for event_name in ["pull_request", "pull_request_target", "workflow_run", "workflow_dispatch"]:
            with self.subTest(event_name=event_name):
                args = evidence()
                args["event_name"] = event_name
                with self.assertRaises(ReleaseRejected):
                    release_plan(**args)

    def test_fork_or_mismatched_repository_is_rejected(self):
        for change in [
            {"repository": "attacker/YachtPlus"},
            {"event": {**evidence()["event"], "repository": {"full_name": "attacker/YachtPlus", "fork": False}}},
            {"event": {**evidence()["event"], "repository": {"full_name": "xNicolas99/YachtPlus", "fork": True}}},
            {"event": {**evidence()["event"], "repository": {"full_name": "xNicolas99/YachtPlus"}}},
        ]:
            with self.subTest(change=change):
                with self.assertRaises(ReleaseRejected):
                    release_plan(**{**evidence(), **change})

    def test_mismatched_checked_commit_push_commit_and_ref_are_rejected(self):
        for change in [
            {"checked_sha": "b" * 40},
            {"sha": "not-a-sha"},
            {"event": {**evidence()["event"], "after": "b" * 40}},
            {"event": {**evidence()["event"], "ref": "refs/heads/feature"}},
            {"event": {**evidence()["event"], "deleted": True}},
            {"event": {**evidence()["event"], "workflow_run": {"conclusion": "success"}}},
            {"event": {**evidence()["event"], "pull_request": {}}},
        ]:
            with self.subTest(change=change):
                with self.assertRaises(ReleaseRejected):
                    release_plan(**{**evidence(), **change})

    def test_branch_and_semver_tag_mismatch_never_publish(self):
        for ref in ["refs/heads/devel", "refs/heads/v2.1.0", "refs/tags/v2.0.0", "refs/tags/2.1.0", "refs/tags/v2.1.0-rc.1"]:
            with self.subTest(ref=ref):
                args = evidence()
                args["ref"] = args["event"]["ref"] = ref
                with self.assertRaises(ReleaseRejected):
                    release_plan(**args)

    def test_tag_commit_outside_release_branch_is_rejected(self):
        args = evidence()
        args["ref"] = args["event"]["ref"] = "refs/tags/v2.1.0"
        args["on_release_branch"] = False
        with self.assertRaises(ReleaseRejected):
            release_plan(**args)

    def test_noncanonical_semver_cannot_inject_tags_or_outputs(self):
        for version in ["latest", "2.1", "02.1.0", "2.1.0-rc.1", "2.1.0+build", "2.1.0\nlatest", "２.1.0", None]:
            with self.subTest(version=version):
                args = evidence()
                args["package"]["version"] = version
                with self.assertRaises(ReleaseRejected):
                    release_plan(**args)

    def test_lockfile_and_root_versions_must_match_canonical_version(self):
        for lock in [{}, {"version": "2.0.0"}, {"version": "2.1.0", "packages": {"": {"version": "2.0.0"}}}]:
            with self.subTest(lock=lock):
                args = evidence()
                args["lock"] = lock
                with self.assertRaises(ReleaseRejected):
                    release_plan(**args)


class PublicationCommandTests(unittest.TestCase):
    """Use real git checkouts/remotes and the real CLI; never mock git success."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.origin = self.base / "origin"
        self.origin.mkdir()
        self.run_git(self.origin, "init", "-b", "master")
        self.run_git(self.origin, "config", "user.name", "Release Test")
        self.run_git(self.origin, "config", "user.email", "release-test@example.invalid")
        frontend = self.origin / "frontend"
        frontend.mkdir()
        args = evidence()
        (frontend / "package.json").write_text(json.dumps(args["package"]), encoding="utf-8")
        (frontend / "package-lock.json").write_text(json.dumps(args["lock"]), encoding="utf-8")
        self.run_git(self.origin, "add", ".")
        self.run_git(self.origin, "commit", "-m", "Release")
        self.sha = self.run_git(self.origin, "rev-parse", "HEAD")
        self.run_git(self.origin, "tag", "v2.1.0")
        self.checkout = self.base / "checkout"
        self.run_git(self.base, "clone", "--no-hardlinks", str(self.origin), str(self.checkout))
        self.output = self.base / "output"
        self.event = self.base / "event.json"
        self.env = os.environ.copy()
        self.env.update({
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REPOSITORY": "xNicolas99/YachtPlus",
            "GITHUB_REF": "refs/heads/master",
            "GITHUB_SHA": self.sha,
            "GITHUB_EVENT_PATH": str(self.event),
            "GITHUB_OUTPUT": str(self.output),
            "CI_NEEDS_JSON": json.dumps(args["needs"]),
            "CI_CANCELLED": "false",
        })
        self.payload = args["event"]
        self.payload["after"] = self.sha

    @staticmethod
    def run_git(cwd, *args):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()

    def cli(self, *args):
        self.event.write_text(json.dumps(self.payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/release_gate.py"), *args],
            cwd=self.checkout, env=self.env, text=True, capture_output=True, check=False,
        )

    def assert_rejected_without_outputs(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Publication rejected:", result.stderr)
        self.assertFalse(self.output.exists(), "Rejected inputs must not emit image tags")

    def test_actual_checkout_emits_version_and_bound_commit(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.output.read_text(encoding="utf-8")
        self.assertIn("version=2.1.0\n", output)
        self.assertIn(f"sha-{self.sha}\n", output)

    def test_actual_checkout_mismatch_emits_no_outputs(self):
        self.env["GITHUB_SHA"] = "b" * 40
        self.payload["after"] = "b" * 40
        self.assert_rejected_without_outputs(self.cli())

    def test_malformed_json_and_missing_inputs_fail_closed(self):
        self.env["CI_NEEDS_JSON"] = "not-json"
        self.assert_rejected_without_outputs(self.cli())
        del self.env["CI_NEEDS_JSON"]
        self.assert_rejected_without_outputs(self.cli())

    def test_malformed_lockfile_fails_without_outputs(self):
        (self.checkout / "frontend/package-lock.json").write_text('{"version":"2.1.0","packages":[]}', encoding="utf-8")
        self.assert_rejected_without_outputs(self.cli())

    def test_remote_current_commit_passes(self):
        result = self.cli("--verify-remote")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.output.exists())

    def test_stale_remote_branch_rejects_previously_validated_checkout(self):
        (self.origin / "new.txt").write_text("new commit", encoding="utf-8")
        self.run_git(self.origin, "add", ".")
        self.run_git(self.origin, "commit", "-m", "Newer release")
        self.assert_rejected_without_outputs(self.cli("--verify-remote"))

    def test_lightweight_and_annotated_tags_bind_to_commit(self):
        self.env["GITHUB_REF"] = self.payload["ref"] = "refs/tags/v2.1.0"
        for annotated in [False, True]:
            with self.subTest(annotated=annotated):
                if annotated:
                    self.run_git(self.origin, "tag", "-f", "-a", "v2.1.0", "-m", "Annotated tag")
                result = self.cli("--verify-remote")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_version_after_checkout_rejects_publication(self):
        (self.checkout / "frontend/package.json").write_text('{"version":"2.2.0"}', encoding="utf-8")
        self.assert_rejected_without_outputs(self.cli())

    def test_untracked_docker_context_file_rejects_publication(self):
        (self.checkout / "injected.txt").write_text("not from the checked commit", encoding="utf-8")
        self.assert_rejected_without_outputs(self.cli())

    def test_missing_release_branch_ancestry_rejects_publication(self):
        self.run_git(self.checkout, "branch", "-dr", "origin/master")
        self.assert_rejected_without_outputs(self.cli())

    def test_moved_remote_tag_rejects_publication(self):
        self.env["GITHUB_REF"] = self.payload["ref"] = "refs/tags/v2.1.0"
        (self.origin / "new.txt").write_text("moved target", encoding="utf-8")
        self.run_git(self.origin, "add", ".")
        self.run_git(self.origin, "commit", "-m", "Newer commit")
        self.run_git(self.origin, "tag", "-f", "v2.1.0")
        self.assert_rejected_without_outputs(self.cli("--verify-remote"))

    def test_deleted_remote_tag_rejects_publication(self):
        self.env["GITHUB_REF"] = self.payload["ref"] = "refs/tags/v2.1.0"
        self.run_git(self.origin, "tag", "-d", "v2.1.0")
        self.assert_rejected_without_outputs(self.cli("--verify-remote"))


class WorkflowIntegrationTests(unittest.TestCase):
    def test_only_ci_can_write_packages_and_depends_on_every_validation_job(self):
        publishers = []
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            self.assertNotIn("workflow_run", workflow.get("on", {}))
            self.assertNotIn("pull_request_target", workflow.get("on", {}))
            self.assertNotEqual(workflow.get("permissions", {}).get("packages"), "write")
            for job_name, job in workflow["jobs"].items():
                if job.get("permissions", {}).get("packages") == "write":
                    publishers.append((path.name, job_name))
                    self.assertEqual(set(job["needs"]), REQUIRED_JOBS)
                    self.assertNotIn("continue-on-error", job)
                    for required_job in REQUIRED_JOBS:
                        self.assertNotIn("if", workflow["jobs"][required_job])
                        self.assertNotIn("continue-on-error", workflow["jobs"][required_job])
                    steps = job["steps"]
                    checkout = steps[0]["with"]
                    self.assertEqual(checkout["ref"], "${{ github.sha }}")
                    self.assertEqual(checkout["persist-credentials"], "false")
                    self.assertEqual(checkout["fetch-depth"], "0")
                    gate_index = next(i for i, step in enumerate(steps) if step.get("id") == "release")
                    login_index = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("docker/login-action@"))
                    self.assertLess(gate_index, login_index)
                    for step in steps[gate_index:]:
                        self.assertNotIn("continue-on-error", step)
                        self.assertNotIn("if", step)
        self.assertEqual(publishers, [("ci.yml", "publish")])


if __name__ == "__main__":
    unittest.main()
