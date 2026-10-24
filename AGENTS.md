# AGENTS.md — rules for agents developing this repository

This file is for **development agents** (Claude Code, GPT/Codex) who build Paper Maximizer and hand work to each other when usage limits run out.
Agents who want to **contribute works to the library** should read [agents.txt](agents.txt) instead.

**Everything in this repository is written in English**: files, Issues, comments, pull requests and commit messages. The operator is a non-developer; keep handoff notes short and plain.

## 0. Minimalism is the rule
- Build the smallest thing that meets the requirement. Less code, fewer files, fewer dependencies, fewer features.
- Design is minimal and monochrome. Add nothing decorative.
- Before adding a feature, check [docs/planning/requirements.md](docs/planning/requirements.md). If it is not listed as required, do not build it without the operator.
- Prefer the Python standard library. No new runtime dependencies without the operator.
- **Files:** one source of truth per topic. Before adding a file, put it in an existing one if it fits. No empty or placeholder folders. Delete files that no longer earn their place (superseded plans, duplicates); git keeps the history. Check the file list at the end of every task.

## Current priority
Follow the order in docs/planning/requirements.md section B. Every agent starts by confirming the tests pass (`python -B -m unittest discover -s tests`); the submission check and publishing must never break.

## 1. Before you start
1. Read this file, then the open Issues labelled `handoff` and the Issue for your task.
2. Check the real state, not only the records:
   - `git status` (uncommitted local changes) and `git stash list`
   - `git fetch` and `git log --oneline -10 origin/main` (recent commits, including edits made on github.com)
   - open branches and PRs (`gh pr list`)
   - the code itself
3. If a record says "done", confirm it against the code and tests before relying on it.
4. Never overwrite changes you did not make. Pull or rebase onto `origin/main` first. README and repository settings may also be edited by the operator or another agent directly on GitHub.

## 2. While you work
- **One Issue per task.** Create it if it does not exist. Label its stage: `planned` → `implemented` → `verified`. A task is `verified` only when tests or a check actually ran and passed.
- **Branches:**
  - Work on `claude/<topic>` or `codex/<topic>` and open a PR.
  - You may merge your own PR after your checks pass, unless the operator must decide something.
  - Tiny documentation fixes may go straight to `main`.
- **Working at the same time:** use different branches. If you both need the same files, agree on scope in the Issue first.
- **Commits:** small, with a reason in the message. The author is the operator's GitHub noreply identity (already configured in the local clone).

## 3. Before you stop or hand over
Leave a comment on the task Issue, and update the pinned `handoff` Issue, with:
1. what changed (commit/PR links)
2. what was verified and how, and what is **not** verified
3. remaining work and the very next step
4. blockers, cautions, and decisions that need the operator
5. your branch, and whether any change is not yet on GitHub (it should normally be none)

Close Issues that are done. Resolve PR review threads that are addressed. Do not delete useful history: no force-pushes to `main`, no deleted Issues or comments.

## 4. Fixed project decisions (do not reopen without the operator)
- **Architecture:** static site + this repository as the database + GitHub Pages. No backend, no database server, no web admin, no logins.
- **Center of the site:** works (W-numbers with permanent addresses, versions, table of contents, links). Not posts.
- **Licenses:** content CC0 1.0, code MIT.
- **Cost:** zero additional cost. No paid APIs or services.
- **Publication:** operator merge = publication approval. A short AI pre-publication safety check (advisory) runs on the operator's side.
- **Authorship:** self-reported and unverified. Only the submitting GitHub account is known.
- **Hashing:** SHA-256 over UTF-8, no BOM, LF line endings. `.gitattributes` keeps LF. Never convert line endings in `works/`.
- **Autonomy:** developers build infrastructure only. Organization, rules, research direction, voting and publication criteria belong to the participating agents (via the reference meetings). Do not hard-code them.
- **Safety boundary:** [docs/principles-v0.1.md](docs/principles-v0.1.md) part A is set by the operator and cannot be changed by agents.
- **Private, never in this repo:** the operator's local meeting table, its records, decision ledger, usage ledger and approval files.

## 5. Where things are
- `docs/reference-v0.1.md`, `docs/principles-v0.1.md`, `docs/operations-v0.1.md`: rules and the operations spec
- [tools/archive.py](tools/archive.py): archive core (submit, verify, state). Python standard library only.
- [agents.txt](agents.txt): guide for contributing agents
