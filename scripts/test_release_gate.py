"""Exercise publication decisions, git ref binding and the CI dependency graph."""

from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from pathlib import Path

import yaml

from release_gate import (GitHubAPI, REQUIRED_JOBS, ReleaseRejected, complete_version_release,
                          prepare_version_release, release_plan, tag_commit, version_binding)


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

    def test_release_write_permissions_and_credentials_are_only_in_gated_publisher(self):
        workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        for name, job in workflow["jobs"].items():
            if name == "publish":
                self.assertEqual(job["permissions"]["contents"], "write")
                self.assertIn("github.event_name == 'push'", job["if"])
                self.assertIn("github.repository == 'xNicolas99/YachtPlus'", job["if"])
                continue
            self.assertNotEqual(job.get("permissions", {}).get("contents"), "write")
            self.assertNotEqual(job.get("permissions", {}).get("packages"), "write")
            self.assertNotIn("GH_TOKEN", str(job))
        steps = workflow["jobs"]["publish"]["steps"]
        prepare = next(i for i, step in enumerate(steps) if "--prepare-release" in step.get("run", ""))
        publish = next(i for i, step in enumerate(steps) if "docker push" in step.get("run", ""))
        complete = next(i for i, step in enumerate(steps) if "--complete-release" in step.get("run", ""))
        protected = next(i for i, step in enumerate(steps) if "--image \"$candidate\"" in step.get("run", ""))
        self.assertLess(protected, prepare)
        self.assertLess(prepare, publish)
        self.assertLess(publish, complete)
        self.assertEqual(steps[publish]["env"]["RELEASE_TAGS"], "${{ steps.release_binding.outputs.tags }}")
        self.assertIn("set -euo pipefail", steps[publish]["run"])


class FakeReleaseAPI:
    """A stateful GitHub ref/release boundary, including lost responses and races."""

    def __init__(self, sha=None, release=None):
        self.sha, self.release = sha, release
        self.calls = []
        self.lose_ref_response = False
        self.lose_release_response = False
        self.fail_release = False
        self.ref_race = None

    def request(self, method, path, payload=None, *, missing_ok=False):
        self.calls.append((method, path, payload))
        if method == "GET" and path == "git/ref/tags/v2.1.0":
            return {"object": {"type": "commit", "sha": self.sha}} if self.sha else None
        if method == "GET" and path == "releases/tags/v2.1.0":
            return self.release
        if method == "POST" and path == "git/refs":
            if self.sha or self.ref_race:
                self.sha = self.ref_race or self.sha
                raise ReleaseRejected("GitHub release request failed (HTTP 422)")
            self.sha = payload["sha"]
            if self.lose_ref_response:
                raise ReleaseRejected("Lost ref response")
            return {"ref": payload["ref"], "object": {"sha": self.sha, "type": "commit"}}
        if method == "POST" and path == "releases":
            if self.fail_release:
                raise ReleaseRejected("GitHub release request failed (HTTP 503)")
            self.release = {**payload, "id": 42}
            if self.lose_release_response:
                raise ReleaseRejected("Lost release response")
            return self.release
        raise AssertionError(f"Unexpected release API call: {method} {path}")


class AutomaticReleaseTests(unittest.TestCase):
    def setUp(self):
        self.plan = release_plan(**evidence())
        self.digest = "sha256:" + "c" * 64

    def test_new_version_reserves_tag_at_exact_validated_sha_before_release(self):
        api = FakeReleaseAPI()
        binding = prepare_version_release(api, self.plan, SHA)
        self.assertEqual(api.sha, SHA)
        self.assertTrue(binding["create_release"])
        self.assertEqual(binding["tags"].splitlines(), ["2.1.0", f"sha-{SHA}", "latest"])
        self.assertIsNone(api.release)
        self.assertIn(("POST", "git/refs", {"ref": "refs/tags/v2.1.0", "sha": SHA}), api.calls)

    def test_existing_current_commit_tag_resumes_without_moving_ref(self):
        api = FakeReleaseAPI(sha=SHA)
        self.assertTrue(prepare_version_release(api, self.plan, SHA)["create_release"])
        self.assertFalse(any(method == "POST" for method, _, _ in api.calls))

    def test_complete_release_records_verified_commit_version_and_published_digest(self):
        api = FakeReleaseAPI(sha=SHA)
        complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        self.assertEqual(api.release["target_commitish"], SHA)
        self.assertEqual(api.release["tag_name"], "v2.1.0")
        self.assertIn(f"ghcr.io/xnicolas99/yachtplus@{self.digest}", api.release["body"])
        self.assertIn("actions/runs/1234", api.release["body"])
        self.assertFalse(api.release["draft"])
        self.assertFalse(api.release["prerelease"])

    def test_successful_release_is_idempotent_and_version_image_is_not_republished(self):
        api = FakeReleaseAPI(sha=SHA)
        complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        original = dict(api.release)
        binding = prepare_version_release(api, self.plan, SHA)
        self.assertFalse(binding["create_release"])
        self.assertEqual(binding["tags"].splitlines(), [f"sha-{SHA}", "latest"])
        # Rebuilding the same SHA may produce a different digest. It must
        # neither replace the SemVer image nor edit the completed release.
        complete_version_release(api, self.plan, SHA, "sha256:" + "d" * 64, run_id="5678")
        self.assertEqual(api.release, original)
        self.assertEqual(sum(method == "POST" and path == "releases" for method, path, _ in api.calls), 1)

    def test_unchanged_version_on_later_master_commit_only_updates_sha_and_latest(self):
        api = FakeReleaseAPI(sha="b" * 40, release={"tag_name": "v2.1.0", "body": "Existing release"})
        with patch("release_gate.version_at_commit", return_value="2.1.0"), patch("release_gate.subprocess.run") as run:
            run.return_value.returncode = 0
            binding = prepare_version_release(api, self.plan, SHA)
            complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        self.assertFalse(binding["create_release"])
        self.assertEqual(binding["tags"].splitlines(), [f"sha-{SHA}", "latest"])
        self.assertEqual(api.sha, "b" * 40)
        self.assertFalse(any(method == "POST" for method, _, _ in api.calls))

    def test_unrelated_or_wrong_version_tag_fails_closed(self):
        for version, ancestor in [("2.0.0", True), ("2.1.0", False)]:
            with self.subTest(version=version, ancestor=ancestor):
                with self.assertRaises(ReleaseRejected):
                    version_binding(self.plan, SHA, "b" * 40, None,
                                    historical_version=version, ancestor=ancestor)

    def test_unfinished_older_version_reservation_requires_explicit_recovery(self):
        api = FakeReleaseAPI(sha="b" * 40)
        with patch("release_gate.version_at_commit", return_value="2.1.0"), patch("release_gate.subprocess.run") as run:
            run.return_value.returncode = 0
            with self.assertRaisesRegex(ReleaseRejected, "release is incomplete.*original commit"):
                prepare_version_release(api, self.plan, SHA)
        self.assertEqual(api.sha, "b" * 40)
        self.assertFalse(any(method == "POST" for method, _, _ in api.calls))

    def test_user_authored_existing_release_is_untouched_and_does_not_fail_a_build(self):
        for draft in (False, True):
            api = FakeReleaseAPI(sha=SHA, release={"tag_name": "v2.1.0", "draft": draft, "body": "User notes"})
            binding = prepare_version_release(api, self.plan, SHA)
            complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
            self.assertFalse(binding["create_release"])
            self.assertNotIn("2.1.0", binding["tags"].splitlines())
            self.assertEqual(api.release["body"], "User notes")
            self.assertFalse(any(method == "POST" for method, _, _ in api.calls))

    def test_atomic_ref_creation_accepts_only_an_exact_same_sha_race(self):
        api = FakeReleaseAPI()
        api.ref_race = SHA
        self.assertTrue(prepare_version_release(api, self.plan, SHA)["create_release"])
        api = FakeReleaseAPI()
        api.ref_race = "b" * 40
        with self.assertRaises(ReleaseRejected):
            prepare_version_release(api, self.plan, SHA)
        self.assertIsNone(api.release)

    def test_interrupted_ref_or_release_response_can_be_retried_without_duplicates(self):
        api = FakeReleaseAPI()
        api.lose_ref_response = api.lose_release_response = True
        prepare_version_release(api, self.plan, SHA)
        complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        self.assertEqual(api.sha, SHA)
        self.assertEqual(api.release["tag_name"], "v2.1.0")

    def test_failed_image_push_never_creates_release_and_failed_release_can_resume(self):
        api = FakeReleaseAPI()
        prepare_version_release(api, self.plan, SHA)
        self.assertIsNone(api.release)
        api.fail_release = True
        with self.assertRaises(ReleaseRejected):
            complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        self.assertEqual(api.sha, SHA)
        self.assertIsNone(api.release)
        api.fail_release = False
        complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        self.assertEqual(api.release["tag_name"], "v2.1.0")

    def test_invalid_digest_missing_tag_or_conflicting_release_never_creates_release(self):
        for digest in ["", "sha256:short", "sha256:" + "A" * 64, "sha256:" + "a" * 64 + "\n"]:
            with self.subTest(digest=digest):
                api = FakeReleaseAPI(sha=SHA)
                with self.assertRaises(ReleaseRejected):
                    complete_version_release(api, self.plan, SHA, digest, run_id="1234")
                self.assertIsNone(api.release)
        with self.assertRaises(ReleaseRejected):
            complete_version_release(FakeReleaseAPI(), self.plan, SHA, self.digest, run_id="1234")
        for release in [{"tag_name": "v9.9.9"}]:
            with self.assertRaises(ReleaseRejected):
                complete_version_release(FakeReleaseAPI(sha=SHA, release=release), self.plan, SHA, self.digest, run_id="1234")

    def test_real_urlerror_after_tag_reservation_is_recovered_by_reading_the_exact_ref(self):
        def reply(data):
            return io.BytesIO(json.dumps(data).encode())
        absent = HTTPError("https://api.github.com/", 404, "Not found", None, None)
        reference = {"object": {"type": "commit", "sha": SHA}}
        with patch("release_gate.urlopen", side_effect=[absent, absent, URLError("connection lost"), reply(reference), reply(reference)]):
            binding = prepare_version_release(GitHubAPI("secret-test-token"), self.plan, SHA)
        self.assertTrue(binding["create_release"])

    def test_real_urlerror_after_release_creation_recovers_only_matching_provenance(self):
        def reply(data):
            return io.BytesIO(json.dumps(data).encode())
        absent = HTTPError("https://api.github.com/", 404, "Not found", None, None)
        reference = {"object": {"type": "commit", "sha": SHA}}
        release = {"tag_name": "v2.1.0", "draft": False, "prerelease": False,
                   "body": f"<!-- yachtplus-release sha={SHA} digest={self.digest} -->"}
        with patch("release_gate.urlopen", side_effect=[reply(reference), absent, reply(reference), URLError("connection lost"), reply(release), reply(reference)]):
            complete_version_release(GitHubAPI("secret-test-token"), self.plan, SHA, self.digest, run_id="1234")

    def test_completion_uses_reserved_tag_even_if_master_advanced_after_image_push(self):
        api = FakeReleaseAPI(sha=SHA)
        with patch("release_gate.verify_remote", side_effect=AssertionError("Must not rebind to master")):
            complete_version_release(api, self.plan, SHA, self.digest, run_id="1234")
        self.assertEqual(api.release["target_commitish"], SHA)

    def test_annotated_tag_resolves_to_exact_commit_and_bad_objects_are_rejected(self):
        class AnnotatedAPI:
            def request(self, method, path, payload=None, **kwargs):
                return {"object": {"sha": "b" * 40, "type": "tag"}} if path.startswith("git/ref/") else {"object": {"sha": SHA, "type": "commit"}}
        self.assertEqual(tag_commit(AnnotatedAPI(), "v2.1.0"), SHA)
        for obj in [{}, {"sha": SHA, "type": "tree"}, {"sha": "invalid", "type": "commit"}]:
            class BadAPI:
                def request(self, *args, **kwargs):
                    return {"object": obj}
            with self.assertRaises(ReleaseRejected):
                tag_commit(BadAPI(), "v2.1.0")


if __name__ == "__main__":
    unittest.main()
