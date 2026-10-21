# Codex builder and Claude Code reviewer — staged pilot

Status: prepared, disabled, no paid model calls performed. Owner: Sahar.

## Implemented

A ready, same-repository pull request authored and updated by the repository owner can trigger the workflow after enablement. Control code comes from the trusted base commit. Forks, drafts, other authors, and bot updates do not run. Claude reviews supplied text with tools disabled; Codex proposes structured replacements in an isolated directory. The controller applies only permitted existing changed files. At most three reviews and two repair proposals run. Evidence and a repair patch are retained as an artifact tied to the original head revision. Only the separate post-verification publisher can push a repair commit. No PR comment, merge, deployment or human approval occurs.

## Application verification and repair publication

After a successful bounded review loop, a separate job applies the repair artifact and runs configured application checks without AI credentials. Only then can a fresh publisher job with repository write access commit the tested patch to the same PR branch. It uses a normal fast-forward push, never force-pushes, merges, or deploys. A successful check is recorded on the resulting exact commit because GitHub-token pushes do not retrigger ordinary PR workflows. Findings, failed application checks or concurrent branch updates prevent publication. You retain final revision-specific acceptance.

HuVera runs its landing-page audit, lint, content tests, browser tests and build, plus backend lint/type/PostgreSQL tests if that backend is present. The remote HuVera repository currently lacks the local uncommitted backend; it cannot test unpublished code. SelfEat apps run TypeScript, Expo web export and their existing Playwright suite against a checked-out backend; the backend runs its existing pytest suite. Backend revision is taken from its default branch, so cross-repository coordinated changes still need a separate integration plan. Existing test gaps are not filled by AI approval.

The initial task implementation remains in the interactive Codex project; automation starts at the PR handoff. Protected files, dependency manifests, deleted files, symlinks and unsupported files fail closed for manual handling. Large changes are rejected rather than silently truncated.

## Activation requirements

1. Review and merge this setup PR with the workflow disabled.
2. Choose exact API model identifiers in repository variables `AI_DELIVERY_CODEX_MODEL` and `AI_DELIVERY_CLAUDE_MODEL`. Desktop model labels are not assumed to be API names.
3. Add `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` through GitHub encrypted repository secrets. Do not paste keys into chat. Existing desktop sign-ins are not copied.
4. Obtain Sahar's explicit provider spending authorization and set provider-side limits. Claude is capped at USD 1 per review invocation (up to three); Codex has a subprocess timeout but no monetary cap in this controller. This is not a total USD 3 workflow cap.
5. Set `AI_DELIVERY_ENABLED=true` only after those requirements. Start with a synthetic private test PR. No live AI success has been verified.
6. Verify the full review → repair → application checks → same-branch commit sequence on a synthetic private PR before using it for real work. Enable stale-review dismissal in repository branch protection and keep merge/release approval human-owned. Protected branches may deny the publisher; that is a visible failure, never bypassed.

## Verification and intake

Nine synthetic unit tests pass: traversal/protected paths, malformed review, unrelated edits, symlinks/atomic validation, allowed repairs, two-repair bound, missing credentials, failing application checks withholding success evidence, and successful verification binding to the source revision. No customer data or secrets used. Provider CLIs pinned to Codex 0.163.0 and Claude Code 2.1.306, retrieved from their official npm package metadata on 21 October 2026. GitHub actions pinned to commit hashes. No new skill or plugin installed. Provider costs and account access remain unverified; paid execution stays disabled.

## Opposition assessment

OPPOSITION TEAM — Alternative: use an ordinary human-triggered second review with no CI credentials. It has lower automation risk and no unattended spend, but requires repeated handoffs. Main risks of the proposed workflow are source prompt injection, insufficient diff context, model false negatives, and cost. This version limits tools and paths, rejects malformed output, caps rounds and context, retains human acceptance, and stays disabled pending credentials and budget. Disconfirming test: a synthetic PR with traversal or workflow-edit repair proposals must fail closed. KEEP REVERSIBLE.

Official references: https://code.claude.com/docs/en/headless and https://learn.chatgpt.com/docs/non-interactive-mode .

Local static verification: Pyright reports zero errors for the controller; actionlint 1.7.12 validates both workflow files. Existing application code and workflows are unchanged. Live provider tests and repaired-application tests have not run. The automation wiring is prepared, but end-to-end activation remains blocked on credentials and explicit spending authorization.
