"""Fail closed before GHCR publication; only same-run, trusted pushes qualify.

No workflow_run payloads or downloaded artifacts enter the publication path.
Inputs come from GitHub's push context and the actual checked-out commit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TRUSTED_REPOSITORY = "xNicolas99/YachtPlus"
RELEASE_BRANCH = "refs/heads/master"
REQUIRED_JOBS = frozenset({"backend-tests", "frontend-tests", "security-stack", "ruff"})
SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", re.ASCII)
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class ReleaseRejected(ValueError):
    """Publication did not meet a required condition."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseRejected(message)


def release_plan(
    *,
    event_name: str,
    repository: str,
    ref: str,
    sha: str,
    checked_sha: str,
    event: dict,
    needs: dict,
    cancelled: str,
    package: dict,
    lock: dict,
    on_release_branch: bool,
) -> dict:
    """Validate all evidence before returning the only permitted image tags."""
    require(event_name == "push", "Only push events can publish")
    require(repository == TRUSTED_REPOSITORY, "Untrusted repository")
    require(cancelled == "false", "Cancelled or unknown run status")
    require(set(needs) == REQUIRED_JOBS, "Missing or unexpected validation jobs")
    require(
        all(isinstance(job, dict) and job.get("result") == "success" for job in needs.values()),
        "Every validation job must succeed",
    )
    require(bool(SHA.fullmatch(sha)), "Invalid commit SHA")
    require(checked_sha == sha, "Checkout differs from the validated commit")
    require(isinstance(event.get("repository"), dict), "Missing push repository")
    require(event["repository"].get("full_name") == repository, "Push repository mismatch")
    require(event["repository"].get("fork") is False, "Fork or unknown repository provenance")
    require(event.get("ref") == ref, "Push ref mismatch")
    require(event.get("after") == sha, "Push commit mismatch")
    require(event.get("deleted") is False, "Deleted or unknown push ref")
    require("workflow_run" not in event and "pull_request" not in event, "Untrusted event payload")

    version = package.get("version")
    require(isinstance(version, str) and bool(SEMVER.fullmatch(version)), "Invalid canonical SemVer")
    require(lock.get("version") == version, "Lockfile version mismatch")
    require(lock.get("packages", {}).get("", {}).get("version") == version, "Lockfile root mismatch")

    is_branch = ref == RELEASE_BRANCH
    require(is_branch or ref == f"refs/tags/v{version}", "Ref must be master or the canonical version tag")
    require(on_release_branch, "Commit is not reachable from the release branch")
    tags = [version, f"sha-{sha}"]
    if is_branch:
        tags.append("latest")
    return {"image": "ghcr.io/xnicolas99/yachtplus", "version": version, "tags": "\n".join(tags)}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def verify_remote(ref: str, sha: str) -> None:
    """Reject queued stale branch runs and tags that were moved or removed."""
    # An annotated tag has a tag-object SHA and a peeled commit SHA. Prefer
    # the latter so annotated and lightweight releases bind to the same HEAD.
    refs = dict(
        line.split("\t", 1)[::-1]
        for line in git("ls-remote", "origin", ref, ref + "^{}").splitlines()
    )
    require(refs.get(ref + "^{}", refs.get(ref)) == sha, "Remote publication ref moved or vanished")


class GitHubAPI:
    """Only the already-gated publisher receives this job-scoped token."""

    def __init__(self, token: str):
        require(bool(token), "Missing release credential")
        self.token = token

    def request(self, method: str, path: str, payload=None, *, missing_ok=False):
        request = Request(
            f"https://api.github.com/repos/{TRUSTED_REPOSITORY}/{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                     "User-Agent": "YachtPlus-release-gate"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
                require(isinstance(result, dict), "Unexpected GitHub release response")
                return result
        except HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            # Never print auth headers, error bodies or credential material.
            raise ReleaseRejected(f"GitHub release request failed (HTTP {error.code})") from None
        except (URLError, TimeoutError):
            raise ReleaseRejected("GitHub release request was interrupted; recheck the version ref and release before retrying") from None


def tag_commit(api, tag: str):
    reference = api.request("GET", f"git/ref/tags/{tag}", missing_ok=True)
    if reference is None:
        return None
    obj = reference.get("object", {})
    for _ in range(8):
        require(isinstance(obj, dict) and isinstance(obj.get("sha"), str)
                and bool(SHA.fullmatch(obj["sha"])), "Malformed version-tag object")
        if obj.get("type") == "commit":
            return obj["sha"]
        require(obj.get("type") == "tag", "Version tag must resolve to a commit")
        obj = api.request("GET", f"git/tags/{obj['sha']}").get("object", {})
    raise ReleaseRejected("Version tag contains too many indirections")


def version_at_commit(sha: str) -> str:
    require(bool(SHA.fullmatch(sha)), "Invalid release commit")
    return json.loads(git("show", f"{sha}:frontend/package.json")).get("version")


def version_binding(plan, sha, tag_sha, release, *, historical_version=None, ancestor=False):
    """Version refs never move, including subsequent master commits and reruns."""
    tag = f"v{plan['version']}"
    if release is not None:
        require(release.get("tag_name") == tag, "Release/tag mismatch")
        require(tag_sha is not None, "Release exists without its version tag")
    if tag_sha is not None and tag_sha != sha:
        require(ancestor and historical_version == plan["version"],
                "Version tag belongs to an unrelated commit or another canonical version")
        require(release is not None,
                "An earlier commit reserved this version but its release is incomplete. "
                "Recover publication at that original commit or bump the canonical version; the tag will not move.")
        return {"release_tag": tag, "create_release": False, "publish_version": False,
                "tags": "\n".join(value for value in plan["tags"].splitlines() if value != plan["version"])}
    # Existing user-authored releases (including drafts) are never edited or
    # replaced. Their presence also prevents republishing the SemVer image.
    return {"release_tag": tag, "create_release": release is None, "publish_version": release is None,
            "tags": plan["tags"] if release is None else "\n".join(
                value for value in plan["tags"].splitlines() if value != plan["version"])}


def prepare_version_release(api, plan, sha, *, create_tag=True):
    tag = f"v{plan['version']}"
    tag_sha = tag_commit(api, tag)
    release = api.request("GET", f"releases/tags/{tag}", missing_ok=True)
    if tag_sha is None:
        require(release is None, "Release exists without its version tag")
        require(create_tag, "Version tag vanished before release completion")
        # create-ref is a compare-and-set against ABSENCE: never force-push
        # or edit a release ref, including when two publishers race.
        try:
            api.request("POST", "git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
        except ReleaseRejected:
            if tag_commit(api, tag) != sha:
                raise
        tag_sha = tag_commit(api, tag)
        require(tag_sha == sha, "Version tag reservation did not bind to the checked commit")
    historical = version_at_commit(tag_sha) if tag_sha != sha else None
    ancestor = tag_sha != sha and subprocess.run(
        ["git", "merge-base", "--is-ancestor", tag_sha, sha], check=False,
    ).returncode == 0
    return version_binding(plan, sha, tag_sha, release, historical_version=historical, ancestor=ancestor)


def complete_version_release(api, plan, sha, digest, *, run_id):
    require(isinstance(digest, str) and bool(DIGEST.fullmatch(digest)), "Missing or invalid published image digest")
    binding = prepare_version_release(api, plan, sha, create_tag=False)
    if not binding["create_release"]:
        return binding
    tag = binding["release_tag"]
    require(tag_commit(api, tag) == sha, "Release version tag moved before publication")
    # The ref is already reserved at the exact SHA. GitHub must not infer a
    # mutable branch target or implicitly create a tag from the current master.
    payload = {
        "tag_name": tag, "target_commitish": sha, "name": f"YachtPlus {plan['version']}",
        "draft": False, "prerelease": False, "generate_release_notes": True,
        "body": (f"<!-- yachtplus-release sha={sha} digest={digest} -->\n"
                 f"Validated commit: `{sha}`\n\n"
                 f"Container image: `{plan['image']}:{plan['version']}`\n\n"
                 f"Pinned image: `{plan['image']}@{digest}`\n\n"
                 f"[Build and protection checks](https://github.com/{TRUSTED_REPOSITORY}/actions/runs/{run_id})"),
    }
    try:
        release = api.request("POST", "releases", payload)
    except ReleaseRejected:
        # An interrupted response or concurrent rerun may already have
        # published this exact release. Accept only our exact commit/digest.
        release = api.request("GET", f"releases/tags/{tag}", missing_ok=True)
        if release is None:
            raise
    require(release.get("tag_name") == tag and release.get("draft") is False
            and release.get("prerelease") is False, "GitHub release state does not match the validated release")
    require(f"<!-- yachtplus-release sha={sha} digest={digest} -->" in (release.get("body") or ""),
            "Existing release provenance does not match the published candidate")
    require(tag_commit(api, tag) == sha, "Release version tag moved during publication")
    return binding


def write_outputs(plan, binding=None):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"version={plan['version']}\nimage={plan['image']}\n")
        tags = binding["tags"] if binding else plan["tags"]
        output.write(f"tags<<RELEASE_TAGS\n{tags}\nRELEASE_TAGS\n")
        if binding:
            output.write(f"release_tag={binding['release_tag']}\n")
            output.write(f"create_release={str(binding['create_release']).lower()}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--verify-remote", action="store_true")
    modes.add_argument("--prepare-release", action="store_true")
    modes.add_argument("--complete-release", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(git("rev-parse", "--show-toplevel"))
        checked_sha = git("rev-parse", "HEAD")
        require(git("status", "--porcelain", "--untracked-files=all") == "", "Checkout was modified")
        # Checkout fetch-depth: 0 makes release-branch ancestry available. A
        # missing branch or git failure rejects publication rather than guessing.
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", checked_sha, "origin/master"],
            check=False,
        ).returncode == 0
        plan = release_plan(
            event_name=os.environ["GITHUB_EVENT_NAME"],
            repository=os.environ["GITHUB_REPOSITORY"],
            ref=os.environ["GITHUB_REF"],
            sha=os.environ["GITHUB_SHA"],
            checked_sha=checked_sha,
            event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")),
            needs=json.loads(os.environ["CI_NEEDS_JSON"]),
            cancelled=os.environ["CI_CANCELLED"],
            package=json.loads((root / "frontend/package.json").read_text(encoding="utf-8")),
            lock=json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8")),
            on_release_branch=ancestor,
        )
        if args.verify_remote or args.prepare_release:
            verify_remote(os.environ["GITHUB_REF"], checked_sha)
        if args.prepare_release or args.complete_release:
            api = GitHubAPI(os.environ["GH_TOKEN"])
            if args.prepare_release:
                write_outputs(plan, prepare_version_release(api, plan, checked_sha))
            else:
                complete_version_release(api, plan, checked_sha, os.environ["RELEASE_DIGEST"],
                                         run_id=os.environ["GITHUB_RUN_ID"])
        elif not args.verify_remote:
            write_outputs(plan)
        print(f"Validated {checked_sha} as {plan['image']}:{plan['version']}")
        return 0
    except (ReleaseRejected, KeyError, TypeError, AttributeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Publication rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
