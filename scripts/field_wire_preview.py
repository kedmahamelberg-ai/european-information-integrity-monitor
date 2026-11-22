"""Draw the edition graphic from the same public rows used by the bulletin."""


def preview_data(rows):
    samples = [r for r in rows if r["desk"] == 2]
    total = sum(r["total"] for r in samples)
    if total:
        support = sum(r["alignment"].get("supports", 0) for r in samples)
        oppose = sum(r["alignment"].get("opposes", 0) for r in samples)
        values = [("For", support), ("Against", oppose), ("Other", total - support - oppose)]
        return ("Responses to the video message", f"{total:,} sampled comments across {len(samples)} videos",
                values, "Classified YouTube comment samples", "audience")
    counts = [sum(r["desk"] == desk for r in rows) for desk in (0, 1)]
    return ("Coverage in this edition", f"{sum(counts)} dispatches in the log",
            list(zip(("Government", "YouTube"), counts)), "Field Wire dispatch log", "dispatches")


def draw_preview(path, stamp, chart):
    from PIL import Image, ImageDraw, ImageFont

    title, sample, values, source, _ = chart
    canvas = Image.new("RGB", (1280, 720), "#f4f3eb")
    ink, muted, green = "#19291f", "#526155", "#213b30"
    draw = ImageDraw.Draw(canvas)

    def label(x, y, value, size, color=ink, bold=False):
        options = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf")
        for name in options:
            try:
                font = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            font = ImageFont.load_default(size=size)
        draw.text((x, y), value, fill=color, font=font)

    draw.rectangle((0, 0, 1280, 86), fill=green)
    label(64, 22, "EUROPEAN SECURITY MONITOR  /  FIELD WIRE", 29, "white", True)
    label(991, 22, stamp, 29, "white")
    label(64, 125, title, 54, bold=True)
    label(66, 207, sample, 34, muted)
    maximum = max(n for _, n in values)
    for i, (name, count) in enumerate(values):
        y = 320 + 94 * i
        label(66, y - 9, name, 32, bold=True)
        draw.rectangle((305, y, 1025, y + 33), fill="#dbe1d6")
        if count:
            draw.rectangle((305, y, 305 + round(720 * count / maximum), y + 33), fill=green)
        label(1052, y - 11, f"{count:,}", 32, bold=True)
    draw.line((64, 628, 1216, 628), fill=muted, width=2)
    label(65, 650, "Source: " + source, 26, muted)
    canvas.save(path, optimize=True)
