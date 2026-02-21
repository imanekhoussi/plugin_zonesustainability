import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#F8FAFC"
PANEL_BG  = "#FFFFFF"
GRID_COL  = "#E2E8F0"
TEXT_MAIN = "#0F172A"
TEXT_SUB  = "#475569"
TODAY_COL = "#DC2626"

PHASES = [
    {
        "title": "Cadrage & Conception",
        "color": "#2563EB",
        "light": "#EFF6FF",
        "tasks": [
            ("Analyse & Initialisation",        "2025-02-10", "2025-02-14"),
            ("Architecture & Choix Techniques", "2025-02-17", "2025-02-28"),
        ]
    },
    {
        "title": "Socle & Moteur LRS",
        "color": "#059669",
        "light": "#ECFDF5",
        "tasks": [
            ("Ingestion Shapefiles → PostGIS",  "2025-03-03", "2025-03-14"),
            ("Algorithme PK ↔ GPS + API LRS",   "2025-03-10", "2025-03-21"),
        ]
    },
    {
        "title": "Connecteurs & Interop",
        "color": "#D97706",
        "light": "#FFFBEB",
        "tasks": [
            ("Connecteurs EMS / Météo / SGEM",  "2025-03-24", "2025-04-11"),
            ("Sécurité JWT & Rôles",            "2025-04-07", "2025-04-18"),
        ]
    },
    {
        "title": "WebSIG & Front-end",
        "color": "#7C3AED",
        "light": "#F5F3FF",
        "tasks": [
            ("Carte multi-couches & Popups",    "2025-04-07", "2025-04-25"),
            ("Dashboard Admin",                 "2025-04-22", "2025-04-30"),
        ]
    },
    {
        "title": "Tests & Livraison",
        "color": "#DC2626",
        "light": "#FEF2F2",
        "tasks": [
            ("Tests & Recette",                 "2025-05-05", "2025-05-16"),
            ("Préparation Soutenance",          "2025-05-19", "2025-05-30"),
        ]
    },
    {
        "title": "Rédaction Rapport",
        "color": "#0891B2",
        "light": "#ECFEFF",
        "tasks": [
            ("Rédaction Rapport ",  "2025-03-01", "2025-05-30"),
        ]
    },
]

TODAY = datetime(2025, 2, 18)

# ── Flatten rows ──────────────────────────────────────────────────────────────
rows = []
y = 0
phase_meta = []

for phase in PHASES:
    y_start = y
    for task_label, s, e in phase["tasks"]:
        rows.append({
            "y": y,
            "label": task_label,
            "start": datetime.strptime(s, "%Y-%m-%d"),
            "end":   datetime.strptime(e, "%Y-%m-%d"),
            "color": phase["color"],
            "light": phase["light"],
        })
        y += 1
    phase_meta.append((y_start, y - 1, phase["title"], phase["color"], phase["light"]))
    y += 0.5

total_y = y

# ── Figure ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(16, 9))
fig.patch.set_facecolor(BG)
ax.set_facecolor(PANEL_BG)

xmin = datetime(2025, 2, 3)
xmax = datetime(2025, 6, 8)

# ── Phase background bands ────────────────────────────────────────────────────
for ys, ye, ptitle, pcol, plight in phase_meta:
    ax.axhspan(ys - 0.44, ye + 0.44, color=pcol, alpha=0.07, zorder=0)

# ── Vertical grid (weekly) ────────────────────────────────────────────────────
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
ax.xaxis.grid(True, which='major', color=GRID_COL, linestyle='-', linewidth=0.8, zorder=1)

# Phase title labels shown via background bands only

# ── Task bars ─────────────────────────────────────────────────────────────────
BAR_H = 0.50

for row in rows:
    duration = (row["end"] - row["start"]).days + 1

    # Ghost bar (full duration)
    ax.barh(row["y"], duration, left=row["start"],
            height=BAR_H, color=row["color"], alpha=0.18,
            align='center', zorder=2, edgecolor='none')

    # Progress bar (completed portion)
    if TODAY > row["start"]:
        done = min(duration, (TODAY - row["start"]).days + 1)
        ax.barh(row["y"], done, left=row["start"],
                height=BAR_H, color=row["color"], alpha=0.88,
                align='center', zorder=3,
                edgecolor=row["color"], linewidth=0.8)

    # No label on bars

# ── Axes styling ──────────────────────────────────────────────────────────────
ax.set_xlim(xmin, xmax)
ax.set_ylim(-0.8, total_y + 0.2)
ax.invert_yaxis()
ax.set_yticks([r["y"] for r in rows])
ax.set_yticklabels([r["label"] for r in rows], fontsize=9, color=TEXT_SUB)
ax.tick_params(axis='y', length=0, pad=8)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
ax.tick_params(axis='x', colors=TEXT_SUB, labelsize=9, length=0, pad=6)
plt.xticks(rotation=0)

for spine in ax.spines.values():
    spine.set_visible(False)

# ── Top axis — week numbers ───────────────────────────────────────────────────
ax2 = ax.twiny()
ax2.set_xlim(xmin, xmax)
ax2.set_facecolor(PANEL_BG)
ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
ax2.xaxis.set_major_formatter(mdates.DateFormatter('S%V'))
ax2.tick_params(axis='x', colors='#CBD5E1', labelsize=7.5, length=0)
for spine in ax2.spines.values():
    spine.set_visible(False)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_patches = [
    mpatches.Patch(color=p["color"], label=p["title"]) for p in PHASES
]
legend_patches.append(mpatches.Patch(color=TODAY_COL, label="Aujourd'hui — 18 Fév 2025"))
ax.legend(handles=legend_patches,
          loc='lower center', bbox_to_anchor=(0.5, -0.12),
          ncol=4, frameon=True, framealpha=1,
          facecolor=PANEL_BG, edgecolor=GRID_COL,
          labelcolor=TEXT_MAIN, fontsize=8.5,
          handlelength=1.2, columnspacing=1.2)

# ── Title ─────────────────────────────────────────────────────────────────────
fig.text(0.01, 0.98, "Planning de Réalisation — Projet WebSIG",
         fontsize=14, fontweight='bold', color=TEXT_MAIN, va='top')

plt.tight_layout()
# Sauvegarde locale (dans le dossier où se trouve votre script)
plt.savefig('gantt_websig_pro.png', dpi=300, bbox_inches='tight')
plt.show()