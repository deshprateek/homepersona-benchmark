"""
Generate publication-quality charts for the HomePersona v0.1 baseline results.
Run from the repo root: python charts/generate_charts.py
Output: charts/chart_t2_flatness.png, charts/chart_false_act_rate.png
"""
import pathlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

OUT_DIR = pathlib.Path(__file__).parent
OUT_DIR.mkdir(exist_ok=True)

# ── Global style ──────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.alpha": 0.2,
    "grid.linestyle": "--",
    "grid.color": "#9CA3AF",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

BLUE_DARK  = "#1D4ED8"
BLUE_MID   = "#3B82F6"
BLUE_LIGHT = "#93C5FD"
AMBER      = "#D97706"
RED        = "#DC2626"
GREEN      = "#059669"
ORANGE     = "#F59E0B"
GREY       = "#6B7280"

# ── Data ──────────────────────────────────────────────────────────────────────
# T2 flatness chart — ordered by parameter count (ascending)
# Llama 3B excluded: 43% parse error rate makes T2 result unreliable
t2_models = [
    "Mistral 7B\n(Q4 local)",
    "Qwen 32B\n(Q4 local)",
    "Llama 70B\n(fp16 cloud)",
    "Qwen 32B\n(fp16 cloud)",
    "GPT-4o\n(~1T cloud)",
]
t2_values     = [45, 60, 54, 50, 60]
t2_full_run   = [False, True, False, False, True]

# False act rate chart — ordered by rate descending (most dangerous first)
far_models = [
    "Llama 3.2 3B\n(Q4 local)",
    "Mistral 7B\n(Q4 local)",
    "Qwen 32B\n(Q4 local)",
    "Llama 3.3 70B\n(fp16 cloud)",
    "GPT-4o\n(~1T cloud)",
    "Qwen 32B\n(fp16 cloud)",
]
far_values   = [100, 100, 70, 46, 12, 7]
far_full_run = [False, False, True, False, True, False]


# ── Chart 1: T2 flatness ──────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 4.8))

x = np.arange(len(t2_models))
bar_colors = [BLUE_DARK if f else BLUE_LIGHT for f in t2_full_run]
bars = ax.bar(x, t2_values, color=bar_colors, width=0.52, zorder=3,
              edgecolor="white", linewidth=0.5)

# Highlight the 45–60% ceiling band
ax.axhspan(44, 61, color="#FEF9C3", alpha=0.7, zorder=0)
ax.axhline(44, color=AMBER, linewidth=0.9, linestyle="--", zorder=1)
ax.axhline(61, color=AMBER, linewidth=0.9, linestyle="--", zorder=1)
ax.text(len(t2_models) - 0.45, 52, "45–60%\nceiling", fontsize=8.5,
        color="#92400E", ha="right", va="center", fontstyle="italic")

# Value labels
for bar, val, is_full in zip(bars, t2_values, t2_full_run):
    marker = "●" if is_full else "○"
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 1.8,
        f"{val}%{' ●' if is_full else ''}",
        ha="center", va="bottom", fontsize=10,
        color="#111827", fontweight="semibold" if is_full else "normal",
    )

ax.set_xticks(x)
ax.set_xticklabels(t2_models, fontsize=9.5, linespacing=1.3)
ax.set_ylabel("Level 2 accuracy (%)", fontsize=10.5)
ax.set_ylim(0, 90)
ax.yaxis.grid(True, zorder=0)
ax.set_axisbelow(True)
ax.tick_params(axis="x", length=0, pad=6)

ax.set_title(
    "Contextual command accuracy is stuck at 45–60% across all model sizes",
    fontsize=12.5, fontweight="bold", pad=14, loc="left", color="#111827",
)

full_patch   = mpatches.Patch(facecolor=BLUE_DARK,  label="Full 840-row run (●)")
sample_patch = mpatches.Patch(facecolor=BLUE_LIGHT, label="42-row sample")
ax.legend(handles=[full_patch, sample_patch], loc="upper left", fontsize=9,
          framealpha=0.95, edgecolor="#E5E7EB", bbox_to_anchor=(0.01, 0.97))

plt.tight_layout()
out1 = OUT_DIR / "chart_t2_flatness.png"
plt.savefig(out1, dpi=150, bbox_inches="tight")
print(f"Saved {out1}")
plt.close()


# ── Chart 2: False act rate ───────────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(9, 4.8))

y = np.arange(len(far_models))

bar_colors2 = []
for v in far_values:
    if v > 50:
        bar_colors2.append(RED)
    elif v > 20:
        bar_colors2.append(ORANGE)
    else:
        bar_colors2.append(GREEN)

bars2 = ax2.barh(y, far_values, color=bar_colors2, alpha=0.82, height=0.52, zorder=3)

for bar, is_full in zip(bars2, far_full_run):
    if is_full:
        bar.set_edgecolor("#111827")
        bar.set_linewidth(1.8)
        bar.set_alpha(1.0)

# Value labels
for bar, val, is_full in zip(bars2, far_values, far_full_run):
    suffix = " ●" if is_full else ""
    ax2.text(
        bar.get_width() + 1.5,
        bar.get_y() + bar.get_height() / 2,
        f"{val}%{suffix}",
        va="center", fontsize=10,
        fontweight="semibold" if is_full else "normal",
        color="#111827",
    )

# Danger zone line
ax2.axvline(50, color=RED, linewidth=1.0, linestyle="--", alpha=0.4, zorder=1)
ax2.text(51, len(far_models) - 0.45, "danger zone", color=RED,
         fontsize=8.5, fontstyle="italic", va="top")

# Bracket the two Qwen 32B models to show quantization effect
qwen_q4_idx = far_models.index("Qwen 32B\n(Q4 local)")
qwen_fp16_idx = far_models.index("Qwen 32B\n(fp16 cloud)")
ax2.annotate(
    "", xy=(108, qwen_fp16_idx), xytext=(108, qwen_q4_idx),
    arrowprops=dict(arrowstyle="<->", color=GREY, lw=1.2),
)
ax2.text(109.5, (qwen_q4_idx + qwen_fp16_idx) / 2,
         "same\narch.", fontsize=8, color=GREY, va="center", ha="left",
         fontstyle="italic")

ax2.set_yticks(y)
ax2.set_yticklabels(far_models, fontsize=9.5, linespacing=1.3)
ax2.set_xlabel("False act rate — acted when it should have asked (%)", fontsize=10.5)
ax2.set_xlim(0, 120)
ax2.xaxis.grid(True, zorder=0, alpha=0.2)
ax2.set_axisbelow(True)
ax2.tick_params(axis="y", length=0, pad=6)

ax2.set_title(
    "Quantisation strips safety behaviour — same architecture, very different risk",
    fontsize=12.5, fontweight="bold", pad=14, loc="left", color="#111827",
)

full_patch2   = mpatches.Patch(facecolor=GREY, edgecolor="#111827", linewidth=1.5,
                               label="Full 840-row run (●)")
sample_patch2 = mpatches.Patch(facecolor=GREY, alpha=0.6, label="42-row sample")
ax2.legend(handles=[full_patch2, sample_patch2], loc="lower right", fontsize=9,
           framealpha=0.95, edgecolor="#E5E7EB")

plt.tight_layout()
out2 = OUT_DIR / "chart_false_act_rate.png"
plt.savefig(out2, dpi=150, bbox_inches="tight")
print(f"Saved {out2}")
plt.close()
