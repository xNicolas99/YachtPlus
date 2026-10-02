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


TRUSTED_REPOSITORY = "xNicolas99/YachtPlus"
RELEASE_BRANCH = "refs/heads/master"
REQUIRED_JOBS = frozenset({"backend-tests", "frontend-tests", "security-stack", "ruff"})
SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", re.ASCII)
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-remote", action="store_true")
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
        if args.verify_remote:
            verify_remote(os.environ["GITHUB_REF"], checked_sha)
        else:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write(f"version={plan['version']}\nimage={plan['image']}\n")
                output.write(f"tags<<RELEASE_TAGS\n{plan['tags']}\nRELEASE_TAGS\n")
        print(f"Validated {checked_sha} as {plan['image']}:{plan['version']}")
        return 0
    except (ReleaseRejected, KeyError, TypeError, AttributeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Publication rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
