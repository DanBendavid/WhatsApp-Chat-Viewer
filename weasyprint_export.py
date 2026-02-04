import argparse
import html
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


LINE_REGEX_CLASSIC = re.compile(
    r"^\[(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\]\s*(.*?):\s*(.*)$"
)
LINE_REGEX_ENGLISH = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM))\]\s*-?\s*(.*?):\s*(.*)$",
    re.IGNORECASE,
)

ATTACHMENT_RE = re.compile(
    r"<\s*pi(?:e|\u00e8|\u00c3\u00a8)ce jointe\s*:\s*([^>]+)\s*>",
    re.IGNORECASE,
)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)

IMAGE_EXTS = {"jpg", "png", "jpeg", "gif", "webp"}
VIDEO_EXTS = {"mp4", "webm", "ogg"}

PERIODS = [
    {"name": "nuit", "start": 22, "end": 24, "theme": "night"},
    {"name": "nuit", "start": 0, "end": 5, "theme": "night"},
    {"name": "matin", "start": 5, "end": 12, "theme": "day"},
    {"name": "apr\u00e8s-midi", "start": 12, "end": 17, "theme": "day"},
    {"name": "soir", "start": 17, "end": 22, "theme": "night"},
]

WEEKDAYS_FR = [
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
]
MONTHS_FR = [
    "janvier",
    "f\u00e9vrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "ao\u00fbt",
    "septembre",
    "octobre",
    "novembre",
    "d\u00e9cembre",
]


def parse_time(time_str):
    trimmed = time_str.strip()
    ampm_match = re.match(
        r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)$", trimmed, re.IGNORECASE
    )
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2))
        second = int(ampm_match.group(3) or 0)
        meridiem = ampm_match.group(4).upper()
        if meridiem == "PM" and hour < 12:
            hour += 12
        if meridiem == "AM" and hour == 12:
            hour = 0
        return hour, minute, second
    parts = trimmed.split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    return hour, minute, second


def detect_date_order(messages, prefer_mdy):
    dmy_hits = 0
    mdy_hits = 0
    for msg in messages:
        parts = msg["date"].split("/")
        if len(parts) < 2:
            continue
        part_a = int(parts[0])
        part_b = int(parts[1])
        if part_a > 12 and part_b <= 12:
            dmy_hits += 1
        elif part_b > 12 and part_a <= 12:
            mdy_hits += 1
    if mdy_hits > dmy_hits:
        return "MDY"
    if dmy_hits > mdy_hits:
        return "DMY"
    return "MDY" if prefer_mdy else "DMY"


def parse_date(date_str, time_str, date_order):
    part_a, part_b, part_c = [int(x) for x in date_str.split("/")]
    year = part_c
    if year < 100:
        year = 1900 + year if year >= 70 else 2000 + year
    day = part_a
    month = part_b
    if date_order == "MDY":
        day = part_b
        month = part_a
    if month < 1 or month > 12:
        day = part_a
        month = part_b
    hour, minute, second = parse_time(time_str)
    return datetime(year, month, day, hour, minute, second)


def get_period(date_obj):
    hour = date_obj.hour
    for period in PERIODS:
        if period["start"] <= hour < period["end"]:
            return period
    return PERIODS[2]


def format_date_fr(date_obj):
    weekday = WEEKDAYS_FR[date_obj.weekday()]
    month = MONTHS_FR[date_obj.month - 1]
    return f"{weekday} {date_obj.day} {month} {date_obj.year}"


def parse_message_content(message):
    cleaned = message.replace("\u200e", "").strip()
    file_attached_text = "(file attached)"
    file_names = []
    text_only = cleaned

    matches = list(ATTACHMENT_RE.finditer(cleaned))
    if matches:
        file_names = [match.group(1).strip() for match in matches if match.group(1).strip()]
        text_only = ATTACHMENT_RE.sub("", cleaned).strip()
    elif file_attached_text in cleaned:
        inferred = cleaned.replace(file_attached_text, "").strip()
        if inferred:
            file_names = [inferred]
        text_only = ""

    return text_only, file_names


def is_image_file(name):
    ext = name.rsplit(".", 1)[-1].lower()
    return ext in IMAGE_EXTS


def is_video_file(name):
    ext = name.rsplit(".", 1)[-1].lower()
    return ext in VIDEO_EXTS


def get_initials(name):
    cleaned = name.strip()
    if not cleaned:
        return "?"
    parts = [p for p in cleaned.split() if p]
    first = parts[0][0] if parts else ""
    last = parts[-1][0] if len(parts) > 1 else ""
    return (first + last).upper()


def merge_image_sequences(messages):
    merged = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        text_only, file_names = parse_message_content(msg["message"])
        is_image_only = (
            text_only == ""
            and file_names
            and all(is_image_file(name) for name in file_names)
        )
        if not is_image_only:
            merged.append(msg)
            i += 1
            continue

        grouped = list(file_names)
        j = i + 1
        while j < len(messages):
            next_msg = messages[j]
            if next_msg["sender"] != msg["sender"]:
                break
            next_text, next_files = parse_message_content(next_msg["message"])
            next_is_image_only = (
                next_text == ""
                and next_files
                and all(is_image_file(name) for name in next_files)
            )
            if not next_is_image_only:
                break
            grouped.extend(next_files)
            j += 1

        grouped_message = " ".join(f"< piece jointe : {name} >" for name in grouped)
        merged.append({**msg, "message": grouped_message})
        i = j
    return merged


def build_message_html(message, is_user):
    text_only, file_names = parse_message_content(message["message"])
    has_text = bool(text_only)
    has_media = bool(file_names)
    is_media_only = has_media and not has_text

    row_classes = ["message-row", "user" if is_user else "other"]
    msg_classes = ["message", "user" if is_user else "other"]
    if is_media_only:
        row_classes.append("media-only")
        msg_classes.append("media-only")

    parts = [f'<div class="{" ".join(row_classes)}">']
    parts.append(f'<div class="initials">{html.escape(get_initials(message["sender"]))}</div>')
    parts.append(f'<div class="{" ".join(msg_classes)}">')

    if has_text:
        parts.append(f'<div class="message-text">{html.escape(text_only)}</div>')

    if has_media:
        media_classes = ["media"]
        all_images = all(is_image_file(name) for name in file_names)
        all_videos = all(is_video_file(name) for name in file_names)
        if all_images:
            media_classes.append("media-images-only")
        if all_videos:
            media_classes.append("media-videos-only")
        parts.append(f'<div class="{" ".join(media_classes)}">')
        if len(file_names) > 1 and all_images:
            parts.append('<div class="image-grid">')
            for name in file_names:
                url = quote(name, safe="/")
                parts.append(f'<img src="{url}" alt="">')
            parts.append("</div>")
        else:
            for name in file_names:
                url = quote(name, safe="/")
                ext = name.rsplit(".", 1)[-1].lower()
                if ext in IMAGE_EXTS:
                    parts.append(f'<img src="{url}" alt="">')
                else:
                    parts.append(f'<a class="download-link" href="{url}">Download File</a>')
        parts.append("</div>")

    parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


def build_chat_html(messages, date_order, selected_user):
    html_parts = []
    current_key = None
    for msg in messages:
        date_obj = parse_date(msg["date"], msg["time"], date_order)
        period = get_period(date_obj)
        day_key = date_obj.date().isoformat()
        key = f"{day_key}-{period['name']}"
        if key != current_key:
            if current_key is not None:
                html_parts.append("</div>")
            header_text = f"{format_date_fr(date_obj)} \u2014 {period['name']}"
            html_parts.append(f'<div class="time-group {period["theme"]}">')
            html_parts.append(f'<div class="time-header">{html.escape(header_text)}</div>')
            current_key = key
        is_user = selected_user is not None and msg["sender"] == selected_user
        html_parts.append(build_message_html(msg, is_user))
    if current_key is not None:
        html_parts.append("</div>")
    return "\n".join(html_parts)


def parse_chat_file(path):
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    messages = []
    current = None
    prefer_mdy = False
    for raw_line in lines:
        line = raw_line.replace("\u200e", "").lstrip("\ufeff")
        match = LINE_REGEX_CLASSIC.match(line)
        is_english = False
        if not match:
            match = LINE_REGEX_ENGLISH.match(line)
            is_english = bool(match)
        if match:
            if current:
                messages.append(current)
            date, time_str, sender, message = match.groups()
            if is_english:
                prefer_mdy = True
            current = {
                "date": date,
                "time": time_str,
                "sender": sender,
                "message": message,
            }
        elif current:
            current["message"] += "\n" + line
    if current:
        messages.append(current)

    date_order = detect_date_order(messages, prefer_mdy)
    return messages, date_order


def inject_chat(template_text, chat_html):
    marker = '<div id="chat-container"></div>'
    if marker in template_text:
        return template_text.replace(marker, f'<div id="chat-container">{chat_html}</div>')
    pattern = r'(<div id="chat-container"[^>]*>)(.*?)(</div>)'
    return re.sub(pattern, rf"\1{chat_html}\3", template_text, flags=re.DOTALL)


def strip_scripts(html_text):
    return SCRIPT_RE.sub("", html_text)


def render_pdf(html_text, base_url, output_pdf):
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise SystemExit(
            "WeasyPrint n'est pas installe. Lancez: pip install weasyprint"
        ) from exc

    HTML(string=html_text, base_url=base_url).write_pdf(str(output_pdf))


def main():
    parser = argparse.ArgumentParser(
        description="Generate static HTML and PDF (WeasyPrint) from WhatsApp chat export."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Chat txt file (default: _chat_corrected.txt if exists, else _chat.txt)",
    )
    parser.add_argument(
        "--template",
        default="whatsapp-viewerV1.html",
        help="HTML template file.",
    )
    parser.add_argument(
        "--output-html",
        default="whatsapp-viewerV1_print.html",
        help="Output HTML file.",
    )
    parser.add_argument(
        "--output-pdf",
        default="whatsapp-chat.pdf",
        help="Output PDF file.",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="Sender name to place on the right (exact match).",
    )
    args = parser.parse_args()

    base_dir = Path.cwd()
    input_path = Path(args.input) if args.input else None
    if input_path is None:
        corrected = base_dir / "_chat_corrected.txt"
        fallback = base_dir / "_chat.txt"
        input_path = corrected if corrected.exists() else fallback
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    template_path = Path(args.template)
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    messages, date_order = parse_chat_file(input_path)
    messages = merge_image_sequences(messages)

    senders = sorted({msg["sender"] for msg in messages})
    selected_user = args.user
    if selected_user is None and len(senders) == 2:
        selected_user = senders[1]

    chat_html = build_chat_html(messages, date_order, selected_user)
    template_text = template_path.read_text(encoding="utf-8")
    output_html = inject_chat(template_text, chat_html)
    output_html = strip_scripts(output_html)

    output_html_path = Path(args.output_html)
    output_html_path.write_text(output_html, encoding="utf-8")

    output_pdf_path = Path(args.output_pdf)

    print(f"Wrote: {output_html_path}")
    try:
        render_pdf(output_html, base_dir, output_pdf_path)
    except Exception as exc:
        print("PDF generation failed. HTML output is ready.")
        print(f"Error: {exc}")
        return

    print(f"Wrote: {output_pdf_path}")


if __name__ == "__main__":
    main()
