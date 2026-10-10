# Roadmap

## v0.1 — deterministic monitoring (implemented)

- Configurable URLs, native CSS selectors, text/attribute extraction, and output types.
- Validated baseline context; missing/ambiguous selectors and invalid/changed data reports.
- Conservative suggestions for manual review; JSON output and useful exit codes.
- Existing synchronous Playwright Page integration, local fixtures, and CLI tests.

## v0.2 — stronger evidence and integration

- Async Page integration and explicit frame/shadow-root scope.
- Regex, numeric ranges/tolerances, and user-defined validators.
- Opt-in capture redaction, retained baseline history, and review diffs.
- Authenticated browser contexts without persisting credentials in snapshots.
- More explicit semantic anchors and evaluation fixtures for suggestion accuracy.
- Scheduling/CI examples using exit codes; alert integrations as separate opt-ins.

## Later — optional AI-assisted healing

Core monitoring must continue to work without an LLM. Add an optional `ai` extra
and a provider interface with **Gemini**, **OpenAI**, and **Ollama** adapters.
Provider and model selection must be explicit. Cloud adapters receive only
reviewed, bounded, redacted context; Ollama offers a local path. Credentials are
read from environment variables, never saved in snapshots or reports. Add
request timeouts, per-run cost limits, and recorded provider/model metadata.

The first AI release should support selector proposals, not arbitrary Python
rewrites. A proposed workflow:

1. `scrapeguard propose --provider ...` produces a persisted proposal artifact
   containing the original config/baseline fingerprints, old/new selector,
   explanation, and evidence. No source changes occur here.
2. Treat page content and model output as untrusted data. The provider returns a
   structured selector string; never execute generated code or page instructions.
3. Validate the proposal in Playwright: selector syntax, exactly one match,
   declared output type, configured business validators, and semantic/context
   evidence. Run against retained deterministic fixtures and fresh captures.
   Merely finding a number is insufficient. Changed values require extra evidence
   instead of forced equality to stale data.
4. Present a precise diff and validation report to the developer. Do not claim a
   confidence probability without calibration against a labeled evaluation set.
5. Require **explicit human approval of that exact proposal** before patch
   application. A separate `apply` operation references its proposal ID; in an
   interactive flow, show the diff and require affirmative approval. Noninteractive
   automation must supply a separately approved proposal artifact and digest.
   Broad approval or a model's own recommendation is insufficient.
6. Before applying, verify that the config, baseline, and proposal digests still
   match; stale proposals must be revalidated and approved again. Apply only the
   allowed selector change, atomically, with a backup and audit record.
7. Run the resulting scraper and validators again. Roll back a failing change,
   preserve the report, and require separate explicit approval to replace a
   baseline. A successful selector patch must not silently accept new data.

Do not add unattended healing until evidence, approval boundaries, rollback,
and provider-specific tests are established. No AI dependencies or network calls
are present in v0.1 beyond the websites Playwright is configured to visit.
