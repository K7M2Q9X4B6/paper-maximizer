# Security fixes handoff for Claude

Owner-requested work, 2026-10-25. Task: [#43](https://github.com/K7M2Q9X4B6/paper-maximizer/issues/43). Branch: `codex/security-fixes`.

This is a temporary handoff document. Read it, check the linked PR and CI results, and take any necessary action. **Delete this file only after the owner tells you that you have read and acted on it.** Keep the issue/PR history.

## Changes

- `tools/build.py`: escape the language attribute, including quotes, before inserting it into HTML. Always consume the first line of a plain paragraph, including a pipe-prefixed line that is not a valid table.
- `tools/checks.py`: execute submitted Python only inside a pinned Python 3.12 Docker image. No host files, network, Docker socket, or credentials enter the container. Use a non-root user, read-only root, writable limited `/tmp`, and CPU/memory/process limits. Discard output to prevent host output-buffer exhaustion. Remove the named container after success, failure, or timeout. Missing Docker or image fails closed; no unsafe fallback.
- Main gained tasks/attempts in PR #46 while this fix was in progress. Preserve that feature and run its `verify(answer)` through the same sandbox. Answers are passed as quoted string data; True/False/error are mapped from container exit status rather than submitted stdout.
- Intake and PR-check workflows prepare the image before checking. The host, outside the untrusted container, produces `checks.json`; submitted code cannot replace it.
- `tools/llm.py`: screen all text using 30,000-character chunks with 1,000-character overlaps. Keep the existing provider, retries, fail-closed behavior, and Unauthorized Advice exception. Any rejected or unavailable chunk blocks publication.
- Focused tests cover rendering, parser progress, tail screening, runner failure/cleanup, live Docker isolation, and rerunning existing archived checks. Documentation explains the new Docker requirement.

## Verification

- Before changes: 43 unit tests passed on the current `main` snapshot.
- Local Windows has no Docker. Non-container tests, archive verification, and static build are run locally. Docker integration tests must pass on the PR's Ubuntu runner before merge; they also rerun all existing archived check blocks.
- The security review used harmless local markers and synthetic artifacts. No exploit submission was made to the production library. No existing work or catalog entry is edited by this fix.
- No paid services, live model probes, new Python packages, or frontend features are introduced. Docker is already provided by the GitHub-hosted Ubuntu runner. The normal free safety service remains part of publication.

## What to check next

1. Read the task's final comment and PR check logs for actual local/CI/deployment results and the merged commit. Do not infer Docker integration success from Windows-only test results.
2. Review the sandbox invocation and confirm there are no host mounts, forwarded secrets, or network. Docker still shares the host kernel; this is not a claim of immunity to container-runtime/kernel vulnerabilities.
3. Keep the Python image digest pinned. When updating it, pull the new digest and rerun all archived checks and sandbox tests before merging.
4. Failure messages now show container exit codes instead of submitted stderr. Local reruns require Docker/Linux containers and `python tools/checks.py --pull`; preserve fail-closed behavior rather than adding automatic host execution.
5. Full-text safety screening can make more free-provider calls for long works. Do not restore silent truncation to reduce calls; failed service calls must keep publication closed.
6. After the owner confirms you have read and acted, delete only this temporary file in a normal commit. Do not delete issue/PR history or published works.
