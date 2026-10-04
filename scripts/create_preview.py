"""Render a deterministic, dependency-light product preview image.

This is a documentation preview for environments without a display server;
the shipped desktop UI itself is native Tkinter and is rendered by Windows.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int, bold: bool = False):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render(destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 940), "#111827")
    draw = ImageDraw.Draw(image)
    title = _font(28, True); section = _font(16, True); body = _font(14); small = _font(12)

    draw.rectangle((0, 0, 1600, 72), fill="#1b2433")
    draw.text((30, 20), "RESEARCH OS", fill="#edf2f7", font=title)
    draw.text((285, 30), "Personal Research Operating System · structured graph", fill="#9aa9bd", font=body)
    draw.rounded_rectangle((1360, 20, 1565, 52), radius=10, fill="#168b83")
    draw.text((1400, 28), "+ New", fill="#06151a", font=section)

    draw.rectangle((0, 72, 230, 940), fill="#1b2433")
    draw.text((28, 102), "WORKSPACE", fill="#5eead4", font=section)
    nav = ["⌂  Dashboard", "◎  Research Graph", "▤  Entities", "▥  Paper Notes", "✓  Claim Ledger", "⚗  Experiment Notebook", "⌕  Search", "◈  Timeline", "☷  Daily Research Log", "⌘  Question Tree", "▣  Templates"]
    y = 145
    for item in nav:
        fill = "#33455f" if item == "◎  Research Graph" else "#1b2433"
        draw.rounded_rectangle((16, y - 5, 214, y + 29), radius=7, fill=fill)
        draw.text((28, y + 3), item, fill="#edf2f7", font=body)
        y += 42
    # Keep the data actions below the complete workspace list; older preview
    # versions reused ``y`` from the loop and drew DATA on top of Templates.
    data_y = y + 18
    draw.line((18, data_y - 18, 212, data_y - 18), fill="#344258", width=1)
    draw.text((28, data_y), "DATA", fill="#5eead4", font=section)
    y = data_y + 40
    for item in ("↔  Add Relation", "⇩  Export Archive", "⟳  Backup Database", "✓  Integrity Check"):
        draw.text((28, y), item, fill="#edf2f7", font=body); y += 31

    draw.text((270, 105), "Research Graph", fill="#edf2f7", font=title)
    draw.text((270, 148), "Scroll to zoom · drag nodes · middle-drag to pan", fill="#9aa9bd", font=body)
    draw.rounded_rectangle((270, 182, 1565, 865), radius=12, fill="#0b1220", outline="#334155", width=2)

    # Edges first.
    nodes = {
        "paper": (480, 350, "Paper", "A Synthetic Study"),
        "claim": (760, 275, "Claim", "Episodic memory improves"),
        "hyp": (1010, 390, "Hypothesis", "Benefit after horizon 4"),
        "exp": (1255, 280, "Experiment", "Horizon sweep"),
        "result": (1270, 585, "Result", "Advantage at horizon 8"),
        "dataset": (800, 620, "Dataset", "Synthetic tasks v1"),
        "idea": (520, 675, "Idea", "Adaptive memory budgets"),
    }
    edges = [("paper", "claim", "SUPPORTS"), ("claim", "hyp", "INSPIRES"), ("hyp", "exp", "TESTED_BY"), ("exp", "result", "PRODUCES"), ("exp", "dataset", "USES"), ("idea", "hyp", "EXTENDS")]
    for a, b, label in edges:
        x1, y1, *_ = nodes[a]; x2, y2, *_ = nodes[b]
        draw.line((x1, y1, x2, y2), fill="#52637b", width=3)
        draw.text(((x1 + x2) // 2 - 35, (y1 + y2) // 2 - 15), label, fill="#7f91aa", font=small)
    colors = {"Paper": "#6da8ff", "Claim": "#ffb86b", "Hypothesis": "#f5df68", "Experiment": "#63d9d4", "Result": "#7dd3fc", "Dataset": "#c0a0ff", "Idea": "#f9a8d4"}
    for key, (x, y, typ, label) in nodes.items():
        draw.ellipse((x - 56, y - 56, x + 56, y + 56), fill=colors[typ], outline="#dbeafe", width=3)
        words = label.split()
        lines = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if len(candidate) > 18 and current:
                lines.append(current); current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        draw.multiline_text((x - 45, y - 20), "\n".join(lines), fill="#0b1220", font=small, align="center", spacing=2)
        draw.text((x - 42, y + 66), typ, fill="#b8c6d8", font=small)

    draw.rounded_rectangle((270, 880, 1565, 920), radius=8, fill="#1b2433")
    draw.text((290, 892), "51 entities  ·  55 relations  ·  Demo: Agent Memory Research  ·  SQLite autosave enabled", fill="#9aa9bd", font=body)
    image.save(path)
    return path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(render(root / "screenshots" / "researchos_ui_preview.png"))
