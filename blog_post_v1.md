# Your Smart Home Doesn't Know When to Shut Up — or When to Act

*Prateek Deshmukh and Samir Jibhakate*

---

It's 10pm. You tell your smart home "make sure everything is secure." It locks all the doors, arms the alarm in away mode, and turns off all the lights. You're still inside. Your partner is still in the garden. The system did exactly what you asked. And completely missed what you meant.

Now flip it. You say "make it cozy." The thermostat stays at 19°C. The lights stay at full brightness. Nothing happens. The system wasn't sure what you meant, so it asked four clarifying questions before doing anything. You give up and do it yourself.

Both failures come from the same root problem: the system doesn't know when to act and when to ask. Get it wrong one way and it's dangerous. Get it wrong the other way and it's useless.

We built a benchmark of 840 home automation commands to measure one specific thing: does the model know when to act immediately versus when to ask the user first? We call this **initiative calibration** — and we tested it across seven AI models, from a small quantized model running entirely on a laptop to GPT-4o. What we found is that no model gets it right, the failure modes are completely different depending on model size, and the problem does not get better as models get larger.

---

## Not all commands are equal

Home automation commands sit on a spectrum. Some have one right answer. Others are impossible to answer correctly without knowing who you are.

We split them into four levels:

**Level 1 — Clear commands.** "Turn off the kitchen lights." One right answer. The system should just do it, no questions asked. Any hesitation here is annoying and erodes trust.

**Level 2 — Contextual commands.** "Turn off the lights." Which room? A smart system can often infer this from context — it's 11pm, you're in the bedroom, the kitchen light is the only one still on. Context fills the gap. The system should usually act, occasionally ask.

**Level 3 — Personal commands.** "Make it cozy." There is no universal answer. Your cozy is 21°C and warm dim lighting at 30%. Your neighbour's cozy is 18°C and complete silence. A system that doesn't know you personally cannot act on this correctly. It should ask first.

**Level 4 — History-dependent commands.** "Same as last Friday." Impossible to answer without knowing what happened last Friday specifically. The system should always ask.

The jump from Level 1 to Level 3 is the jump from "any AI can handle this" to "only a system that knows you specifically can handle this." That gap is where home automation breaks down for almost everyone today.

---

## What we built

We created a benchmark of 840 commands spread across all four levels and seven categories: lighting, climate, access control, media, appliances, cameras, and multi-device routines.

For each command we defined the correct answer: either act immediately (and what action to take), or ask the user first. Then we asked a simple question — do current AI models know which type of command they're looking at?

The metric we care most about is the **false act rate** — how often the model acts when it should have asked first. This is the dangerous failure. A model that asks too much is annoying. A model that acts without asking can lock you out of your house, run your vacuum while guests are sitting in the living room, or disarm your alarm while you're asleep.

The benchmark and full harness are open source at [github.com/deshprateek/homepersona-benchmark](https://github.com/deshprateek/homepersona-benchmark).

---

## What we found

![HomePersona v0.1 baseline results across seven models](https://raw.githubusercontent.com/deshprateek/homepersona-benchmark/main/charts/chart_results_table.png)

![False act rate across models — acted when it should have asked](https://raw.githubusercontent.com/deshprateek/homepersona-benchmark/main/charts/chart_false_act_rate.png)

**Small models act on everything.** Tell a 7B model "make it cozy" or "good morning" and it will confidently execute something — dim the lights to 20%, start the heating, unlock the front door — without asking whether that's what you meant. It never asks. On every command where it should have asked first, it acted instead.

**Quantisation strips safety behaviour.** Qwen 2.5 32B in cloud fp16 acts without asking only 7% of the time. The same architecture quantised to Q4 and run locally shows a 70% false act rate. Compression that costs barely anything on benchmark accuracy costs a great deal on the safety-critical behaviour of knowing when not to act.

**Nobody gets the personal commands right.** On Level 3 commands — the ones that genuinely require knowing the user — GPT-4o still acts without asking 17% of the time. The local quantised 32B model does it 84% of the time. Size helps but does not solve it.

**The most striking finding: Level 2 accuracy is completely flat.** On the two full 840-row runs, both GPT-4o and Qwen 2.5 32B Q4 landed at exactly 60% on contextual commands. A trillion-parameter cloud model and a 32B local model, the same score. This is not a scale problem.

![Level 2 accuracy across model sizes — stuck at 45–60% regardless of scale](https://raw.githubusercontent.com/deshprateek/homepersona-benchmark/main/charts/chart_t2_flatness.png)

---

## Why bigger models don't fix this

Level 2 and Level 3 failures are not failures of language understanding. These models understand the words perfectly. "Make it cozy" is not a confusing sentence.

The failure is a missing prior: the model has no idea what cozy means *to you specifically*. It has been trained on billions of documents written by millions of people with millions of different preferences. When you say cozy, it averages across all of them. The average is wrong for almost everyone.

A bigger model trained on more data averages across more people. It does not get closer to you. It gets closer to a statistical average of humanity — which is precisely the wrong thing to optimise for when you want a system that controls your home.

---

## What we're testing next

The fix is not a bigger model. It's a model that knows you — but built in two steps.

**Step 1: start with a model that already knows when to ask.** The v0.1 results point directly at the right base: Qwen 32B fp16 asks for clarification on 86% of personal commands correctly, with only a 7% false act rate. Before any personalisation begins, the model already knows it doesn't know your preferences. Ask is its default on ambiguous commands. That is the correct starting state.

**Step 2: personalise with LoRA.** On top of that calibrated base, we add a small adapter trained on your specific preferences — a technique that updates a fraction of the model's parameters without retraining from scratch. The core questions:

- **Alignment velocity** — the base model already knows to ask about "make it cozy." After how many personal examples does it stop asking and just act — with the specific values it has learned for you? Does the curve plateau at 50 examples or 500?
- **Catastrophic forgetting** — does fine-tuning on personal preferences degrade the model's general home automation capability?
- **Forward transfer** — when preferences shift over time (new routine, new device, new season), does prior personalisation make adaptation faster, or do old habits interfere?

The hypothesis: a model that already asks correctly by default, further tuned on your specific preferences, should outperform GPT-4o on your personal commands — while running entirely on your home hardware with no data leaving your network.

We'll know soon whether that hypothesis holds.

---

*The benchmark dataset and evaluation harness are open source: [github.com/deshprateek/homepersona-benchmark](https://github.com/deshprateek/homepersona-benchmark)*

*Prateek Deshmukh and Samir Jibhakate are Senior Software Engineers building HomePersona, a continual learning benchmark for personal home automation.*
