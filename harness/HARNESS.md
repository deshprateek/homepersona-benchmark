# HomePersona v0.1 — Evaluation Harness

All decisions recorded here. Update this file when any design decision changes.

---

## Purpose

Run baseline models against the v0.1 benchmark dataset. Measure whether model size matters for home automation command comprehension before investing in LoRA personalisation (v0.2).

The harness is deliberately simple — it does not score during the run. Raw model outputs are logged to JSONL and scored separately. This decouples model inference cost from scoring iteration cost.

---

## Two-Script Design

### `run.py` — Model inference

- Loads all 7 CSVs into a single dataframe (840 rows)
- Filters to 42-row sample if `--sample-only` flag is set
- Verifies data version hash before running (blocks if mismatch)
- For each row: builds prompt → calls model → appends record to JSONL immediately
- Never overwrites an existing run file — exits with an error if file already exists

**Input:** CSVs + `eval_system_prompt.md` + `config.yaml`
**Output:** `runs/{run_id}.jsonl`

### `score.py` — Scoring and summary

- Reads a run JSONL
- Loads the CSVs to get ground truth labels (`expected_initiative`, `expected_action`)
- Joins on `row_id`
- Scores each row on two axes
- Outputs a scored CSV and prints a summary table

**Input:** `runs/{run_id}.jsonl` + CSVs
**Output:** `runs/{run_id}_scores.csv` + printed summary table

---

## What the Model Sees

Only the `command` field from the CSV row goes to the model as the user turn. All other CSV fields are labels used by `score.py` — the model must not see them.

```
System:  eval_system_prompt.md with one situational snapshot injected
User:    <command field from CSV row>
```

The model returns a JSON object:
```json
{
  "initiative": "act" | "ask",
  "action": "<DSL expression>",
  "clarification": "<question — only present when initiative=ask>"
}
```

---

## JSONL Record Format

One record per row, written immediately after the model call (append-only):

```json
{
  "run_id": "mistral7b_snapshot_a_v0.1.0_20260526",
  "row_id": "LGT-001",
  "category": "lighting",
  "tier": 1,
  "interaction_type": "command",
  "expected_initiative": "act",
  "expected_action": "light.set(room=kitchen state=off)",
  "utterance": "Turn off the kitchen lights",
  "model": "mistral:7b",
  "snapshot": "A",
  "model_raw_response": "{\"initiative\": \"act\", \"action\": \"light.set(room=kitchen state=off)\"}",
  "parse_error": false,
  "timestamp": "2026-05-26T20:30:00Z"
}
```

If the model returns malformed JSON: retry once with a stricter prompt. If it fails again: log `parse_error: true`, `model_raw_response` contains the raw string, continue to next row.

---

## Run ID Format

```
{model}_{snapshot}_{data_version}_{date}
```

Example: `mistral7b_snapshot_a_v0.1.0_20260526`

Each run writes to its own file. `run.py` exits with an error if the file already exists — delete manually to rerun.

---

## Data Versioning

`VERSION` file in `benchmark/`:

```
v0.1.0
cmds_hash: <hash>
# Bump version + update cmds_hash only when the `command` column changes in any CSV.
# Label-only changes (expected_action, expected_initiative, notes, tier) do not require a bump.
# Run `python harness/check_version.py` to verify. run.py calls this automatically at startup.
```

`check_version.py`:
- Reads all 7 CSVs, extracts the `command` column from each
- Hashes the concatenated result
- Compares to `cmds_hash` in `VERSION`
- Prints `OK` or `MISMATCH — bump VERSION before running`
- `run.py` calls this at startup and refuses to proceed on mismatch

---

## Partial Run Recovery

If `run.py` crashes mid-run: on restart it reads the existing JSONL, collects already-written `row_id`s, and skips them. No duplicate records, no data loss, no re-spend on already-called rows.

---

## Two-Track Design

v0.1 runs two parallel tracks. Same benchmark rows, same system prompt, same snapshot — only the model and precision differ. The gap between tracks measures the quantization tax.

**Why two tracks:**
- fp16 track is the clean academic baseline — full model capability, directly comparable across models and to GPT-4o
- Q4 track is on-device deployment reality — quantized, runs locally, what a user would actually experience
- Together they answer: which models survive quantization well enough for on-device deployment?

**v0.2 repeats the same two-track design for LoRA:**
- fp16 LoRA via cloud fine-tuning endpoint (Together AI)
- QLoRA local via HuggingFace + PEFT + bitsandbytes

---

## Models

### fp16 Track (Groq API — cloud inference, full precision)

| Config model name | Groq model ID | Size | Role |
|---|---|---|---|
| `groq/llama-3.1-8b-instant` | `llama-3.1-8b-instant` | 8B | Small baseline |
| `groq/llama-3.3-70b-versatile` | `llama-3.3-70b-versatile` | 70B | Large open model |
| `groq/qwen/qwen3-32b` | `qwen/qwen3-32b` | 32B | Size-matched to Q4 Qwen track |
| `gpt-4o` | OpenAI | ~1T | Ceiling |

Note: `llama-3.2-3b-preview` was decommissioned by Groq; replaced with `llama-3.1-8b-instant`.
`qwen3-32b` uses chain-of-thought thinking by default — expect higher token usage and rate limit pressure on full runs.
Set `GROQ_API_KEY` env var before running fp16 track.

### Q4 Track (Ollama — local inference, 4-bit quantized)

| Config model name | Size | RAM needed | Role |
|---|---|---|---|
| `llama3.2:3b` | 3B | ~3GB | Small, matches fp16 track |
| `mistral:7b` | 7B | ~6GB | Mid-size |
| `qwen2.5:32b` | 32B | ~22GB | Large local model |

Phi-3 Mini excluded — broken with long system prompts in Ollama.
Set nothing — all local, no API key needed.

`model.py` exposes a single `call(model, system_prompt, user_message) -> str` function.
Routing: `groq/*` → Groq API, `gpt-4o` → OpenAI, everything else → Ollama.

---

## Fixed Sample (42 rows)

Used for all harness testing until the full run is validated. Stored in `sample_ids.txt` — never changes unless the sample itself is intentionally replaced.

6 rows per category (7 categories = 42 rows total), stratified:

| Slot | Tier | Type | Expected initiative |
|---|---|---|---|
| 1 | 1 | command | act |
| 2 | 1 | command | act |
| 3 | 2 | command | act or ask |
| 4 | 3 | command | ask |
| 5 | 1 | automation | act |
| 6 | 2 | automation | act or ask |

---

## Scoring (`score.py`)

### Initiative score
Exact match: `expected_initiative` vs parsed `initiative` from model response.
- `1` = correct
- `0` = wrong
- `null` = parse error

### Action score
- **T1 / T2**: DSL parse + structural comparison. Extract verb and key-value pairs from both strings. Compare: device/verb match (0/1) + parameter match (0/1). Total: 0, 1, or 2.
- **T3 / T4**: LLM judge. Send expected action + model action to GPT-4o with a rubric. Returns score 0–2 + reason string. Rationale: T3/T4 actions are partial or contain `unknown` — structural comparison is too brittle.

### Summary output
Printed table + `{run_id}_scores.csv`:

```
Model: mistral:7b  |  Snapshot: A  |  Data: v0.1.0

                    Initiative Acc    Action Acc (0-2)
                    ──────────────    ────────────────
T1  command (35)       x.xx              x.xx
T2  command (28)       x.xx              x.xx
T3  command (14)       x.xx              x.xx
T4  command  (7)       x.xx              x.xx
T1  auto    (15)       x.xx              x.xx
T2  auto    (12)       x.xx              x.xx
T3  auto     (6)       x.xx              x.xx
T4  auto     (3)       x.xx              x.xx
─────────────────────────────────────────────
Overall            x.xx              x.xx

Parse errors: N / 840
```

---

## File Structure

```
benchmark/
  harness/
    HARNESS.md          ← this file
    run.py              ← main loop: load, call model, write JSONL
    score.py            ← read JSONL + CSVs, score, print summary
    model.py            ← Ollama + OpenAI behind one call() interface
    check_version.py    ← hash CSVs command column, compare to VERSION
    sample_ids.txt      ← fixed 42 row IDs for harness testing
    config.yaml         ← model, snapshot, paths, sample_only flag
  runs/                 ← gitignored — raw JSONL and scored CSVs live here
  VERSION               ← data version string + cmds_hash
```

---

## Build Order

1. `sample_ids.txt` — pick the 42 rows
2. `VERSION` + `check_version.py` — data versioning guard
3. `model.py` — Ollama + OpenAI behind one interface
4. `config.yaml`
5. `run.py` — load, verify version, loop, write JSONL
6. Test: `--sample-only` on Mistral 7B via Ollama
7. `score.py` — once we have real output to score against

Do not build `score.py` before step 6. Score against real model output, not invented output.
