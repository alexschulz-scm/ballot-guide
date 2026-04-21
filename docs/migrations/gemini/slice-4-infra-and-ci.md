# Slice 4 — Infra & CI

## Goal

GitHub Actions and Azure Container Apps deployment use `GEMINI_API_KEY` instead of `ANTHROPIC_API_KEY`. Test-phase CI env vars use `MOCK_LLM`.

## Context

This is the only slice with deploy-time risk. Merging the code before the secret exists in GitHub Actions and Azure will cause the next prod deploy to boot-fail (AC-17 requires `GEMINI_API_KEY`).

**The plan/implement cycle for this slice must pause for user confirmation that manual steps are done before merging.**

## Changes

### `.github/workflows/deploy.yml`

In the test job env block (around lines 28-29):
- `MOCK_CLAUDE: "true"` → `MOCK_LLM: "true"`
- `ANTHROPIC_API_KEY: test-key` → `GEMINI_API_KEY: test-key`

In the deploy job (around line 84):
- `anthropicApiKey=${{ secrets.ANTHROPIC_API_KEY }}` → `geminiApiKey=${{ secrets.GEMINI_API_KEY }}`

### `infra/main.bicep`

- Rename param `anthropicApiKey` → `geminiApiKey` (keep `@secure()` decorator)
- Update the propagation to the `api` module (line ~50): pass `geminiApiKey: geminiApiKey`

### `infra/modules/api.bicep`

- Rename param `anthropicApiKey` → `geminiApiKey` (keep `@secure()`)
- Rename the registered secret (line ~41): `{ name: 'anthropic-api-key', value: anthropicApiKey }` → `{ name: 'gemini-api-key', value: geminiApiKey }`
- Rename the env var mapping (line ~64): `{ name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }` → `{ name: 'GEMINI_API_KEY', secretRef: 'gemini-api-key' }`
- Flip the mock flag in prod env (line ~61): `MOCK_CLAUDE: 'false'` → `MOCK_LLM: 'false'`

## Acceptance criteria

- [ ] `bicep build infra/main.bicep` succeeds with no warnings
- [ ] `rg -i 'anthropic|mock_claude' .github infra` returns zero hits
- [ ] CI test job passes with `GEMINI_API_KEY=test-key` and `MOCK_LLM=true`
- [ ] A staging deploy (or a dry-run `az deployment group what-if`) shows the new secret and env-var mapping in place
- [ ] Prod deploy boots successfully (see manual verification below)

## Manual steps — do BEFORE merging this slice

This is a checklist. All items must be confirmed done before the slice is merged to the migration branch's eventual target.

- [ ] **GitHub Actions secret**: add `GEMINI_API_KEY` to the repo's Actions secrets (Settings → Secrets and variables → Actions). Use a production-grade key from Google AI Studio or Google Cloud.
- [ ] **Azure secret**: add `GEMINI_API_KEY` to wherever the Bicep reads production secrets from (Key Vault or Container Apps secret store — confirm with whoever owns the subscription).
- [ ] **Verify** the new secret is readable from the pipeline's service principal / identity.
- [ ] **Do NOT remove** the old `ANTHROPIC_API_KEY` secret yet — keep as rollback safety net until the first successful prod deploy on Gemini.

## Manual steps — do AFTER first successful Gemini prod deploy

- [ ] Confirm the container boots with `GEMINI_API_KEY` only (check logs for the AC-17 startup check passing).
- [ ] Smoke-test one real ballot request in prod.
- [ ] Delete the old `ANTHROPIC_API_KEY` GitHub Actions secret.
- [ ] Delete the old `anthropic-api-key` secret from Azure (Key Vault or Container Apps).
- [ ] Revoke the Anthropic API key in the Anthropic console.

## Out of scope (deferred)

- Doc and spec text updates — Slice 7.
- Cost/latency monitoring dashboard changes — separate future work.

## Rollback

If the prod deploy fails:
1. Revert the Bicep commit on the migration branch.
2. Re-deploy from `main` (which still has the Anthropic config).
3. The old `ANTHROPIC_API_KEY` secret is still present (per the manual-steps guardrail above), so rollback deploys work immediately.
4. Diagnose the Gemini config issue on the branch, then re-attempt.

If `google-genai` SDK fails at runtime but the secret is present: this is a Slice 2 bug surfacing in prod, not a Slice 4 bug. Roll back to `main` and fix on the branch.
