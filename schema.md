# HomePersona Benchmark — Schema

## Mission

HomePersona's research question is: *can a small local model learn who you are through interaction and eventually act without being asked?*

This benchmark exists to measure that — not just whether a model can execute instructions, but whether it can learn preferences, set up automations, and incorporate corrections over time. A generic voice assistant only needs to handle commands. HomePersona must handle all four ways a user interacts with their home AI.

**The ambiguity in home AI is not a language problem — it's a context problem.** "Dim the lights" is unambiguous in language. It is ambiguous because the system doesn't know which room, which device, how much, or what this specific user means by it given their history. The model resolves ambiguity by combining three signals:
1. **Device context** — what devices and capabilities exist in this home
2. **Situational context** — time, room, occupancy, activity (internal)
3. **External context** — outdoor temperature, weather, season (conditions the environment but is outside the home)

External context is a first-class training signal, not metadata. A user's thermostat pattern is not "18°C on Tuesday nights" — it is "18°C on Tuesday nights *when outdoor temperature is above 10°C*." The model must learn rules conditioned on external context, and the benchmark must test this.

---

## The Learning Arc

HomePersona is not a static model — it is a system that evolves. The benchmark must measure this evolution, not just a point-in-time snapshot.

The system progresses through four phases:

**Phase 1 — Command Execution (reactive)**
User explicitly says what to do. System executes. No proactive behaviour yet.
- "Turn off the kitchen lights" → `light.set(room=kitchen, state=off)`
- Benchmark role: Tier 1 rows. Establishes baseline accuracy. Also the **forgetting anchor** — re-run after every adaptation step to detect catastrophic forgetting.

**Phase 2 — Pattern Recognition → Suggest (ASK)**
System notices a recurring pattern from telemetry. Confident enough to attempt a proactive action on a new instance of the pattern — but not yet confident enough to act silently. Acts once and asks for confirmation.
- Telemetry: user has manually turned on the study lamp on 3 consecutive evenings
- [System turns on lamp] → "I turned on the study lamp — was that right?"
- User: "Yes"
- Benchmark role: Tier 2–3 rows with `expected_initiative=ask`. Each confirmation cycle is one data point toward generalisation. Alignment Velocity measurement begins here.

**Phase 3 — Habit Generalised → Proactive (ACT)**
After sufficient confirmation cycles, the model has generalised the context→action mapping. It now acts silently on *variations* of the learned pattern — not just the exact same time or trigger. This is what distinguishes learning from rule execution.
- Day 10: user enters study at 6:30pm (different time than usual) → lamp turns on without prompting
- Day 12: user settles in study after dinner at 8pm → lamp turns on without prompting
- The model learned `context=study + evening + occupied → lamp on`, not `time=19:00 → lamp on`
- Benchmark role: Same Tier 3 row, adapted-user evaluation condition, `expected_initiative=act`. Alignment Velocity = number of confirmation cycles to reach silent generalised ACT on novel context instances.

**Phase 4 — Anomaly Detected → Pause (ASK)**
Learned automation would fire, but a context variable directly relevant to that automation is anomalous. System pauses and checks rather than acting blindly.
- [7pm arrives, but guests are in the study] → "Guests are in the study — shall I still turn on the lamp?"
- Benchmark role: v0.3 chaos scenarios. Tests Graceful Degradation (Axis D). Bounce-back test after chaos block resolves tests intra-routine forgetting.

This arc is the core research contribution. Existing benchmarks (PersonalHomeBench, SmartBench) evaluate static command execution. HomePersona evaluates whether the full arc executes correctly — including the transitions between phases.

---

## Evaluation Architecture

The benchmark ships as two layers. They test different things and require different setups.

### Layer 1 — Static Evaluation (v0.1)

Evaluate any fixed model on a point-in-time snapshot. No training during evaluation.

- **Input:** utterance
- **Output:** structured action + `act`/`ask` decision
- **Model state:** fixed
- **Who can run it:** any model — GPT-4, Llama 3, fine-tuned Phi, HomePersona baseline
- **What it measures:** command comprehension, intent classification, ASK/ACT decision quality
- **Artefact:** the CSV files in this directory

This is your apples-to-apples baseline comparison. Run all models through Layer 1 to show where the field currently stands — and where it fails.

### Layer 2 — Dynamic Evaluation (v0.2+)

Evaluate a model with an adaptation mechanism across a simulated timeline. Adapter updates fire at defined points in the sequence.

- **Input:** chronological sequence of utterances + telemetry + feedback signals
- **Output:** ASK/ACT transitions across time, accuracy trajectory across adaptation steps
- **Model state:** changes — adapter updates at defined checkpoints
- **Who can run it:** models with an adaptation mechanism (LoRA or equivalent)
- **What it measures:** Alignment Velocity, Catastrophic Forgetting, Graceful Degradation
- **Artefact:** evaluation harness + chronological sequence files (v0.2)

This is the novel contribution. No existing benchmark measures personalisation dynamics over a simulated interaction timeline.

### User Personality Archetypes

The validation set is not one sequence — it is one sequence **per personality archetype**. Alignment Velocity and Catastrophic Forgetting are reported per archetype, not as a single average. A result that collapses across personalities obscures the most important finding: the system learns some types of users much faster than others.

Four archetypes cover the meaningful axes of variation:

| Archetype | Interaction style | Expected Alignment Velocity | Risk |
|---|---|---|---|
| **Explicit** | Specific values, clear commands — "set bedroom to 18°C at 10pm" | Fast — Tier 1–2 heavy | Low forgetting risk |
| **Implicit** | Vague, contextual — "make it cosy", "the usual" | Slow — Tier 3–4 heavy | High — model may never fully generalise |
| **Consistent** | Same preferences repeated, low day-to-day variance | Fast once learned | Low — stable target |
| **Variable** | Preferences shift by mood, weather, season | Slow, unstable | High — model chases a moving target, risks forgetting |

**Why this matters for the paper:** if Alignment Velocity is systematically higher for Explicit/Consistent users and lower for Implicit/Variable users, that is a finding about the fundamental limits of the approach — not just a benchmark result. It distinguishes where the LoRA adapter is the bottleneck from where the interaction style itself is the bottleneck.

The v0.2 chronological sequence files are generated once per archetype. Each archetype has its own sequence, its own adaptation checkpoints, and its own reported metrics. The validation protocol runs independently for each.

### Validation Protocol (continual training)

During continual training, the validation set runs **after every adaptation epoch** — not just at the end. The validation set is not shuffled. It is ordered to mirror the learning arc. **The full protocol runs once per personality archetype.**

**After each adaptation step (per archetype):**
1. Run full Tier 1 anchor set → **cross-habit forgetting check**
   If accuracy drops below baseline: catastrophic forgetting detected
2. Run current habit scenario → **alignment progress check**
   Has `expected_initiative` correctly transitioned ASK→ACT?
3. Run all previously learned habit scenarios → **cross-habit forgetting check**
   Each prior habit is re-evaluated after each new habit is added

**After a chaos block resolves (per archetype):**
4. Run Tier 1 anchor set → forgetting check
5. Run all prior habit scenarios → **bounce-back test** (intra-routine forgetting)
   Did anomaly handling corrupt the routine itself?

**Report metrics as:** mean ± std across archetypes, then broken down per archetype. The per-archetype breakdown is the interesting result.

A model that reaches 95% accuracy at the end of training but catastrophically forgets after each adaptation step is a failed model. This protocol catches it.

---

## Benchmark Versions

| Version | Layer | What it tests | Artefact |
|---|---|---|---|
| **v0.1** | Layer 1 — static | Command + automation comprehension. Act/ask decision quality. No adaptation. Any model can be evaluated. | CSV files |
| **v0.2** | Layer 2 — dynamic | Chronological sequences with context columns and adaptation checkpoints. Measures Alignment Velocity + Catastrophic Forgetting across the learning arc. | Sequence files + evaluation harness |
| **v0.3** | Layer 2 — dynamic | Anomaly detection — chaos block + bounce-back test. Measures Graceful Degradation (Axis D). | Chaos scenario files |

**v0.3 design note:** Chaos is bounded to the context of the devices and rooms the automation acts on. Not arbitrary external events — contextually relevant anomalies. Example: learned automation "dim bedroom lights at 10pm" fires normally, but tonight guests are present in the bedroom. The anomalous variable (guests) is directly relevant to the automation's action space. Expected behaviour: system checks with user before acting. This tests the Generalised Norm hierarchy's Priority 3 (reversibility) — when context is anomalous, ask before acting.

---

## File Format

### v0.1 — Static Evaluation Files

One CSV per device category. The schema is fixed — same columns across all category files.

| Column | Type | Description |
|---|---|---|
| `id` | string | Unique ID — format: `{CATEGORY_CODE}-{NUMBER}` e.g. `LGT-001` |
| `command` | string | Natural language utterance as a user would say it |
| `category` | string | Device category (see below) |
| `interaction_type` | string | What kind of interaction this is (see below) |
| `tier` | int | 1–4 — how much context/history is needed to act correctly |
| `expected_action` | string | Structured output the system should produce |
| `expected_initiative` | string | `act` or `ask` — whether the correct response is to act immediately or confirm with the user first |
| `notes` | string | Optional — explains ambiguity or edge cases |

**`expected_initiative` rules:** Tier 1 is always `act`. Tier 4 is always `ask`. Tiers 2–3 depend on whether the ambiguity is resolvable by common sense (`act`) or requires personal preference that has not yet been learned (`ask`). For Tier 3, a new user baseline always produces `ask`; an adapted user produces `act` with a specific learned action — these are two separate evaluation conditions.

---

### v0.2 — Sequence Files (one per personality archetype)

The v0.1 columns are the **validation instrument** — fixed, reused for every archetype. The v0.2 sequence files are the **training input** — what drives adaptation before validation runs. Same columns across all archetype files. The archetype is in the filename, not a column (within any one file every row is the same archetype — it would be redundant).

```
v0.2_sequence_explicit.csv    — Tier 1–2 heavy, specific values, precise corrections
v0.2_sequence_implicit.csv    — Tier 3–4 heavy, vague commands, contextual corrections
v0.2_sequence_consistent.csv  — same preferences repeated, low day-to-day variance
v0.2_sequence_variable.csv    — preferences shift by mood, weather, season mid-sequence
```

The evaluation harness loops over these files. For each: run the adaptation loop in day order, fire adapter updates at checkpoints, then run the full v0.1 validation set. Report Alignment Velocity, Catastrophic Forgetting, and Graceful Degradation per archetype. Report mean ± std across archetypes. The per-archetype breakdown is the result — collapsing to a single average obscures the most important finding.

**v0.2 sequence columns** (extends v0.1 columns with context and timeline fields):

| Column | Type | Description |
|---|---|---|
| `id` | string | Carries over from v0.1 — links sequence row to static validation row |
| `command` | string | Utterance — same as v0.1 |
| `category` | string | Device category — same as v0.1 |
| `interaction_type` | string | Same as v0.1 |
| `tier` | int | Same as v0.1 |
| `expected_action` | string | Same as v0.1 |
| `expected_initiative` | string | Same as v0.1 |
| `day` | int | Day in the interaction timeline (1–14) |
| `time` | string | Time of day — e.g. `19:00` |
| `context` | string | Situational snapshot — room, occupancy, activity — e.g. `room=study occupancy=user activity=working` |
| `external` | string | Outdoor conditions — e.g. `temp=8C weather=rain season=autumn` |
| `feedback` | string | User response after system action — `yes`, `no`, or correction utterance |
| `checkpoint` | bool | `true` if an adapter update fires after this row |
| `notes` | string | Optional — edge cases or anomaly flags |

---

## Interaction Types

Five interaction types in total. `command` and `automation` appear in v0.1 static evaluation rows. `preference` and `feedback` appear only in v0.2 sequence files — they require sequence context to be meaningful (preference only arises in response to a model question or as an inferred standing rule; feedback requires knowing the model's prior output). `telemetry` appears only in v0.2 sequence files as passive device state changes with no utterance.

### `command`
Direct instruction. User wants something done now.
- "Turn off the kitchen lights"
- "Set the thermostat to 20 degrees"
- "Lock the front door"

*Why it matters:* Foundation of the dataset. Tests basic understanding.  
*Training signal:* Labeled (command, action) tuple.

### `preference` *(v0.2 sequence files only)*
User expresses how they like things. Not an instruction to act now — a signal to remember. Preference utterances do not appear in v0.1 because they are not standalone — they only arise as responses to a model question, as inferred standing rules from telemetry, or during an ongoing sequence. Testing them in isolation produces unrealistic rows.
- "I like it cold when I sleep"
- "I never want the TV on when we have guests"
- "I prefer warm light in the evenings"

*Why it matters:* This is how the LoRA adapter learns who you are. Preference expressions are the input to the data flywheel.  
*Training signal:* Stored preference — shapes future command handling.

### `automation`
User explicitly sets a rule or trigger. The system should act in the future when conditions are met, not now.
- "When guests arrive, dim the lights and put on soft music"
- "Every morning at 7am, open the blinds"
- "When I say goodnight, lock everything and turn off all lights"

*Why it matters:* Proactive behaviour — the system acts without being asked. This is what distinguishes a personalised home AI from a voice assistant.  
*Training signal:* Trigger-action rule stored and activated on future events.

### `feedback` *(v0.2 sequence files only)*
User corrects or confirms the system's action. The system got it wrong (or right) and the user responds. Feedback utterances do not appear in v0.1 because each row requires knowing what the model output — feedback is a response to a prior model turn, not a standalone utterance. Evaluating it in isolation requires mocking the model's prior output, which conflates the evaluation with the generation.
- "No, I wanted the bedroom not the kitchen"
- "A bit warmer than that"
- "Yes, exactly like that"
- "Not that bright"

*Why it matters:* Correction signals are DPO preference pairs — the core of the personal RLHF layer. Every correction is a (rejected_action, preferred_action) pair.  
*Training signal:* DPO preference pair — the strongest learning signal in the pipeline.

### `telemetry` *(v0.2 sequence files only)*
Passive device state change observed by the system — no utterance from the user. The user physically interacted with a device (dimmed a light, adjusted a thermostat, turned on a fan) without saying anything. The system observes the state change via device telemetry.

- User walks to thermostat and sets it to 18°C at 10pm — no voice command
- User manually dims bedroom lights to 30% — no voice command
- User turns off the TV via remote — no voice command

*Why it matters:* Most home interactions are silent. A system that only learns from explicit commands misses the majority of the signal. Telemetry rows are the passive observation layer — the system watches what the user does, not just what they say.  
*Training signal:* Same as command — labeled (context, action) tuple. Mechanism doesn't matter, signal is identical.  
*`utterance` column:* empty for telemetry rows.  
*`confirmation_count`:* increments on every telemetry row, same as command and feedback rows. The harness counts all three toward the same pattern — see Confirmation Count below.

---

## Confirmation Count (v0.2 harness-derived)

`confirmation_count` is not a column in any CSV. It is computed by the evaluation harness at runtime by counting how many times the same (context → action) pattern has appeared in the sequence so far, regardless of interaction type.

All three mechanisms increment the same counter for the same pattern:

| Mechanism | Interaction type | Utterance | Counts toward |
|---|---|---|---|
| User physically adjusts device | `telemetry` | empty | confirmation_count |
| User issues explicit command | `command` | present | confirmation_count |
| User confirms system suggestion | `feedback` | present | confirmation_count |

**Why this matters for inner vs outer belief measurement:**

To test whether the model implicitly learns inner/outer belief structure, v0.2 sequences are designed with two habit types:

- **High-confirmation habits** — same (context → action) pattern appears 15–20 times across the sequence via any combination of telemetry, command, and feedback rows. These are candidate inner beliefs.
- **Low-confirmation habits** — pattern appears 2–3 times. These are candidate outer beliefs.

When a conflicting preference is introduced, the harness measures which habits forget. If high-confirmation habits resist forgetting while low-confirmation habits update freely — the model has implicitly learned inner/outer belief structure. If both forget at the same rate — all preferences are equally fragile and the model has no such structure.

This is not manually labelled. It is an emergent property of the sequence design and the adapter's behaviour under it.

---

## Device Capability Graph

The device capability graph defines what the benchmark's reference home can do. It is a static layer — part of the benchmark definition, not part of the model's learned state.

**v0.1:** No capability graph. All rows assume a fully capable home. Action format is **device-agnostic** — it tests comprehension (did the model correctly resolve room, device type, action, and parameters from the utterance?) not device integration (did it output the right API call for a specific manufacturer).

**v0.2:** Introduces a capability graph. Two benchmark home profiles with different capability classes:

```yaml
# Home A — fully capable
kitchen:
  - type: colour_light      # on/off, dim 0-100%, colour temperature
bedroom:
  - type: dimmable_light    # on/off, dim 0-100%
hallway:
  - type: non_dimmable_light  # on/off only

# Home B — partially capable
kitchen:
  - type: non_dimmable_light
bedroom:
  - type: colour_light
hallway:
  - type: non_dimmable_light
```

Same utterance ("dim the hallway light to 50%") produces different correct actions depending on which home profile the model is evaluated against. Home A → `light.set(room=hallway, brightness=50%)`. Home B → `ask` (hallway has no dimming capability — correct response is to inform user and offer alternative).

**Capability classes (device-agnostic — not manufacturer-specific):**

| Class | Capabilities |
|---|---|
| `non_dimmable_light` | state: on/off |
| `dimmable_light` | state: on/off, brightness: 0–100% |
| `colour_light` | state: on/off, brightness: 0–100%, colour_temp, colour_rgb |
| `programmable_thermostat` | temp, mode: heat/cool/auto, schedule |
| `smart_lock` | state: locked/unlocked, user: string |
| `smart_speaker` | volume: 0–100%, source, genre, state: play/pause/stop |
| `smart_appliance` | state: run/stop/pause, program: string |
| `ip_camera` | state: active/inactive, stream, motion_alert |

Device-specific API translation (Hue vs LIFX vs Lutron) is an integration engineering problem solved once per device type. It is not a research problem and not part of this benchmark.

---

## Device Categories

| Code | Category | Covers |
|---|---|---|
| `LGT` | lighting | On/off, dim, colour, room-specific light control |
| `CLM` | climate | Thermostat, heating, cooling, fans, air quality |
| `ACC` | access | Locks, doors, garage, alarm, security |
| `MED` | media | TV, speakers, music, volume, streaming |
| `APP` | appliances | Kitchen appliances, washing machine, dishwasher, robot vacuum |
| `CAM` | cameras | Indoor/outdoor cameras, doorbells, feeds |
| `ROU` | routines | Multi-device sequences triggered by a single utterance |

---

## Tier Definitions

Tiers apply across all interaction types. The question is always: how much context or learned history does the system need to act correctly? The examples below focus on `command` and `automation` (the v0.1 types); `preference`, `feedback`, and `telemetry` follow the same tier logic in v0.2.

### Tier 1 — Fully Specified
Everything needed to act is in the utterance itself. No ambiguity.
- command: "Turn off the kitchen lights" → clear device, room, action
- automation: "Every morning at 7am, turn on the kitchen lights" → specific trigger + action

**Forgetting Anchor:** Tier 1 rows are never used for training. They are the static baseline. After every adaptation epoch, the full Tier 1 set is re-evaluated. A drop in Tier 1 accuracy is the signal for catastrophic forgetting — the model has learned a new habit at the cost of a prior one. Target: Tier 1 accuracy stays flat at baseline throughout all adaptation cycles.

### Tier 2 — Partially Specified
Device or intent is clear but room, amount, or target requires common-sense inference.
- command: "Dim the lights" → which room? how much? → infer from situational context
- automation: "When I get home, set it up for me" → trigger clear, action vague → ask

### Tier 3 — Implicit Intent
Command describes an outcome or situation, not a device action. Multi-device or heavily context-dependent. Always `ask` on v0.1 — a new user baseline has no learned preferences to draw on.
- command: "Set the mood for dinner" → no device, room, or value specified
- automation: "When it's time to wind down, you'll know what to do" → action requires history

### Tier 4 — Personal / Habitual
Requires learned user history to interpret. Impossible to act on without personalisation data. Always `ask` on v0.1.
- command: "The usual please" → undefined without prior interaction history
- automation: "Like you did that one time when we had people over" → requires episodic memory

---

## Target Distribution

### v0.1 — Static Evaluation

| Interaction Type | Count | Rationale |
|---|---|---|
| `command` | 588 (84 per category) | Foundation — tests command comprehension and act/ask decision |
| `automation` | 252 (36 per category) | Proactive behaviour — tests trigger-action comprehension |
| **Total** | **840** | |

Tier distribution within each type per category:

| Tier | command | automation | Expected initiative |
|---|---|---|---|
| 1 | 35 | 15 | always `act` |
| 2 | 28 | 12 | `act` or `ask` depending on resolvability |
| 3 | 14 | 6 | always `ask` |
| 4 | 7 | 3 | always `ask` |

### v0.2 — Sequence Files

`preference`, `feedback`, and `telemetry` rows appear in the v0.2 sequence files. Distribution is per-archetype and defined when sequence files are generated. No fixed count — sequences are designed around the personality archetype's interaction style.

---

## Expected Action Format

**v0.1 action format is device-agnostic.** All actions are expressed in capability-class terms, not manufacturer-specific API calls. This isolates comprehension accuracy from integration accuracy. The benchmark measures whether the model understood what the user wanted — not whether it knows a Philips Hue brightness range is 0–254.

### command (v0.1)
```
light.set(room=kitchen state=off)
thermostat.set(temp=20 unit=C)
lock.set(door=front state=locked)
speaker.play(room=living_room genre=jazz)
multi.set([light.set(room=dining brightness=40%) speaker.play(genre=ambient)])
unknown                                             ← Tier 3/4 when action is unresolvable without history
```

### automation (v0.1)
```
automation.create(trigger=event=guests_arrive action=multi.set([light.set(brightness=40%) speaker.play(genre=ambient)]))
automation.create(trigger=time=07:00 action=light.set(room=kitchen state=on))
automation.create(trigger=utterance=goodnight action=multi.set([lock.set(all=true) light.set(all=off)]))
```

### preference (v0.2 only)
```
preference.store(condition=time=night device=thermostat value=18C room=bedroom)
preference.store(condition=guests=present device=tv value=off)
preference.store(condition=time=evening device=light value=warm_tone)
```

### feedback (v0.2 only)
```
feedback.correction(rejected=light.set(room=kitchen) preferred=light.set(room=bedroom))
feedback.correction(rejected=thermostat.set(temp=20) preferred=thermostat.set(temp=18))
feedback.confirmation(action=thermostat.set(temp=20))
feedback.correction(direction=warmer magnitude=small)   ← Tier 2 — direction without exact value
```
