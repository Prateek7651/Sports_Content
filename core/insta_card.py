"""
Generates a ready-to-post Instagram square image (1080x1080) for a content item.
Question/statement/prompt is shown WITHOUT the answer revealed — matches how
you'd actually post a quiz sticker (answer isn't printed on the image, viewers
tap/guess first).

Uses Pillow only (no external image APIs), so it's fast and free to generate.
"""

import os
import textwrap
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

CARD_SIZE = (1080, 1080)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")

SPORT_COLORS = {
    "Cricket": ("#0B3D2E", "#1FA97C"),
    "Football": ("#1A2E4A", "#3D8BFD"),
    "Tennis": ("#3D2B1F", "#E8B84B"),
    "Badminton": ("#2B1A3D", "#B45CE8"),
    "Basketball": ("#3D1F1F", "#E85C3D"),
}

TYPE_LABELS = {
    "MCQ": "QUIZ TIME",
    "True/False": "TRUE OR FALSE?",
    "This-or-That": "THIS OR THAT?",
    "Fill-in-the-Blank": "FILL THE BLANK",
    "Guess-the-Number": "GUESS THE NUMBER",
}


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = f"{current} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _draw_gradient_bg(size, top_color, bottom_color):
    top = Image.new("RGB", size, top_color)
    bottom = Image.new("RGB", size, bottom_color)
    mask = Image.new("L", size)
    mask_data = [int(255 * (y / size[1])) for y in range(size[1]) for _ in range(size[0])]
    mask.putdata(mask_data)
    return Image.composite(bottom, top, mask)


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_card(item: dict) -> bytes:
    """
    Returns PNG bytes for the item, ready to save/download/post.
    The correct answer is intentionally NOT printed on the card.
    """
    ctype = item["content_type"]
    sport = item["sport"]
    top_hex, accent_hex = SPORT_COLORS.get(sport, ("#111111", "#4F8CFF"))
    top_rgb, accent_rgb = _hex_to_rgb(top_hex), _hex_to_rgb(accent_hex)
    bottom_rgb = tuple(max(0, c - 20) for c in top_rgb)

    img = _draw_gradient_bg(CARD_SIZE, top_rgb, bottom_rgb)
    draw = ImageDraw.Draw(img)
    W, H = CARD_SIZE
    margin = 80

    # top label pill (content type)
    label = TYPE_LABELS.get(ctype, ctype.upper())
    label_font = _font(FONT_BOLD, 34)
    label_w = draw.textlength(label, font=label_font)
    pill_pad_x, pill_pad_y = 30, 16
    pill_box = [margin, 70, margin + label_w + pill_pad_x * 2, 70 + 34 + pill_pad_y * 2]
    draw.rounded_rectangle(pill_box, radius=30, fill=accent_rgb)
    draw.text((margin + pill_pad_x, 70 + pill_pad_y), label, font=label_font, fill="white")

    # sport name, top right
    sport_font = _font(FONT_REGULAR, 34)
    sport_text = sport.upper()
    sport_w = draw.textlength(sport_text, font=sport_font)
    draw.text((W - margin - sport_w, 80), sport_text, font=sport_font, fill=(255, 255, 255, 180))

    # verified badge, just below sport name — this is the trust-signal USP:
    # every fact is checked against a live web search at generation time,
    # not just retrieved once and assumed correct
    badge_font = _font(FONT_BOLD, 26)
    if ctype == "This-or-That":
        badge_text = "🗳 OPINION"
        badge_color = (200, 200, 200)
    elif item.get("web_verified"):
        badge_text = "✓ WEB-VERIFIED"
        badge_color = (120, 230, 160)
    else:
        badge_text = "⚠ UNVERIFIED"
        badge_color = (240, 190, 100)
    badge_w = draw.textlength(badge_text, font=badge_font)
    draw.text((W - margin - badge_w, 128), badge_text, font=badge_font, fill=badge_color)

    # main question/prompt text, vertically centered-ish
    main_text = {
        "MCQ": item.get("question"),
        "True/False": item.get("statement"),
        "This-or-That": item.get("prompt"),
        "Fill-in-the-Blank": item.get("sentence_with_blank"),
        "Guess-the-Number": item.get("question"),
    }.get(ctype, "")

    q_font = _font(FONT_BOLD, 58)
    max_text_width = W - margin * 2
    lines = _wrap_text(draw, main_text, q_font, max_text_width)
    line_height = 70
    text_block_height = len(lines) * line_height
    start_y = 260

    for i, line in enumerate(lines):
        line_w = draw.textlength(line, font=q_font)
        draw.text(((W - line_w) / 2, start_y + i * line_height), line, font=q_font, fill="white")

    options_start_y = start_y + text_block_height + 60
    opt_font = _font(FONT_REGULAR, 40)
    letter_font = _font(FONT_BOLD, 40)

    if ctype in ("MCQ", "Fill-in-the-Blank"):
        for i, opt in enumerate(item.get("options", [])):
            letter = chr(65 + i)  # A, B, C, D
            y = options_start_y + i * 100
            box = [margin, y, W - margin, y + 80]
            draw.rounded_rectangle(box, radius=16, outline="white", width=3)
            draw.text((margin + 24, y + 20), f"{letter}.", font=letter_font, fill=accent_rgb)
            draw.text((margin + 90, y + 20), opt, font=opt_font, fill="white")

    elif ctype == "True/False":
        for i, opt in enumerate(["TRUE", "FALSE"]):
            box_w = (W - margin * 2 - 30) / 2
            x = margin + i * (box_w + 30)
            y = options_start_y
            box = [x, y, x + box_w, y + 100]
            draw.rounded_rectangle(box, radius=16, outline="white", width=3)
            ow = draw.textlength(opt, font=letter_font)
            draw.text((x + (box_w - ow) / 2, y + 30), opt, font=letter_font, fill="white")

    elif ctype == "This-or-That":
        opts = item.get("options", [])
        for i, opt in enumerate(opts[:2]):
            box_w = (W - margin * 2 - 30) / 2
            x = margin + i * (box_w + 30)
            y = options_start_y
            box = [x, y, x + box_w, y + 140]
            draw.rounded_rectangle(box, radius=16, fill=accent_rgb)
            opt_lines = _wrap_text(draw, opt, letter_font, box_w - 40)
            for j, ol in enumerate(opt_lines):
                ow = draw.textlength(ol, font=letter_font)
                draw.text((x + (box_w - ow) / 2, y + 30 + j * 45), ol, font=letter_font, fill="white")

    elif ctype == "Guess-the-Number":
        prompt_text = "Type your guess in the comments 👇"
        pf = _font(FONT_REGULAR, 36)
        pw = draw.textlength(prompt_text, font=pf)
        draw.text(((W - pw) / 2, options_start_y + 20), prompt_text, font=pf, fill="white")

    # footer branding / CTA
    footer_text = "Answer in comments · Follow for daily sports quizzes"
    footer_font = _font(FONT_REGULAR, 28)
    fw = draw.textlength(footer_text, font=footer_font)
    draw.text(((W - fw) / 2, H - 90), footer_text, font=footer_font, fill=(255, 255, 255, 200))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_batch_zip(items: list) -> bytes:
    """
    Bundles Instagram cards for a whole batch/calendar into a single ZIP,
    so a content creator can grab a week's worth of posts in one download
    instead of clicking each item individually.
    """
    import zipfile
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(items):
            ctype = item["content_type"].replace("/", "-")
            sport = item.get("sport", "sport")
            day = item.get("_day", "")
            prefix = f"{day}_" if day else ""
            filename = f"{prefix}{sport}_{ctype}_{i+1}.png"
            zf.writestr(filename, generate_card(item))
    return buf.getvalue()
