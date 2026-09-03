import datetime as dtt
import re
from datetime import datetime
from io import BytesIO
from typing import Callable, Dict, List, Tuple, Union

from colorthief import ColorThief
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from utils.color import clamp_luminance, pack_rgb, rgb_to_hsp
from utils.misc import executor
from utils.text import difficulty_stars, humanize_points, plural

DIR = "data/assets"
TEXT_LAYOUT = ImageFont.Layout.BASIC


def save(img: Image.Image) -> BytesIO:
    buf = BytesIO()
    img.save(buf, format="png")
    buf.seek(0)
    return buf


def center(size: int, area_size: int = 0) -> int:
    return int((area_size - size) / 2)


def round_rectangle(
        size: Tuple[int, int], radius: int, *, color: Tuple[int, int, int, int]
) -> Image.Image:
    width, height = size

    radius = min(width, height, radius * 2)
    width *= 2
    height *= 2

    corner = Image.new("RGBA", (radius, radius))
    draw = ImageDraw.Draw(corner)
    xy = (0, 0, radius * 2, radius * 2)
    draw.pieslice(xy, 180, 270, fill=color)

    rect = Image.new("RGBA", (width, height), color=color)
    rect.paste(corner, (0, 0))  # upper left
    rect.paste(corner.rotate(90), (0, height - radius))  # lower left
    rect.paste(corner.rotate(180), (width - radius, height - radius))  # lower right
    rect.paste(corner.rotate(270), (width - radius, 0))  # upper right

    return rect.resize(size, reducing_gap=1.0)  # antialiasing


def auto_font(
        font: Union[ImageFont.FreeTypeFont, Tuple[str, int]],
        text: str,
        max_width: int,
        *,
        check: Callable = lambda w, _: w,
) -> ImageFont.FreeTypeFont:
    if isinstance(font, tuple):
        font = ImageFont.truetype(*font, layout_engine=TEXT_LAYOUT)

    while check(font.getbbox(text)[2], font.size) > max_width:
        font = ImageFont.truetype(font.path, font.size - 1, layout_engine=font.layout_engine)

    return font


def wrap_new(
        canv: ImageDraw.ImageDraw,
        box: Tuple[Tuple[int, int], Tuple[int, int]],
        text: str,
        *,
        font: ImageFont.FreeTypeFont,
):
    left, top, right, bottom = font.getbbox("yA")
    _, h = right - left, bottom

    max_width = box[1][0] - box[0][0]
    max_height = box[1][1]

    def write(x: int, y: int, line: List[str]):
        text_ = " ".join(line)
        font_ = auto_font(font, text_, max_width)
        left, top, right, bottom = font_.getbbox(text_)
        w, h = right - left, bottom
        xy = (x + center(w, max_width), y)
        canv.text(xy, text_, fill="black", font=font_)

    x, y = box[0]
    line = []
    for word in text.split():
        left, top, right, bottom = font.getbbox(" ".join(line + [word]))
        w, _ = right - left, bottom

        if w > max_width:
            write(x, y, line)

            y += h
            if y > max_height:
                return

            line = [word]
        else:
            line.append(word)

    if line:
        write(x, y, line)


def skin_renderer(img):
    image = img

    image_body_shadow = image.crop((96, 0, 192, 96))
    image_feet_shadow_back = image.crop((192, 64, 255, 96))
    image_feet_shadow_front = image.crop((192, 64, 255, 96))
    image_body = image.crop((0, 0, 96, 96))
    image_feet_front = image.crop((192, 32, 255, 64))
    image_feet_back = image.crop((192, 32, 255, 64))

    # default eyes
    image_default_left_eye = image.crop((64, 96, 96, 128))
    image_default_right_eye = image.crop((64, 96, 96, 128))

    # evil eyes
    image_evil_l_eye = image.crop((96, 96, 128, 128))
    image_evil_r_eye = image.crop((96, 96, 128, 128))

    # hurt eyes
    image_hurt_l_eye = image.crop((128, 96, 160, 128))
    image_hurt_r_eye = image.crop((128, 96, 160, 128))

    # happy eyes
    image_happy_l_eye = image.crop((160, 96, 192, 128))
    image_happy_r_eye = image.crop((160, 96, 192, 128))

    # surprised eyes
    image_surprised_l_eye = image.crop((224, 96, 255, 128))
    image_surprised_r_eye = image.crop((224, 96, 255, 128))

    def resize_image(image, scale):
        width, height = image.size
        new_width = int(width * scale)
        new_height = int(height * scale)
        return image.resize((new_width, new_height))

    image_body_resized = resize_image(image_body, 0.66)
    image_body_shadow_resized = resize_image(image_body_shadow, 0.66)

    image_left_eye = resize_image(image_default_left_eye, 0.8)
    image_right_eye = resize_image(image_default_right_eye, 0.8)
    image_right_eye_flipped = ImageOps.mirror(image_right_eye)

    image_evil_l_eye = resize_image(image_evil_l_eye, 0.8)
    image_evil_r_eye = resize_image(image_evil_r_eye, 0.8)
    image_evil_r_eye_flipped = ImageOps.mirror(image_evil_r_eye)

    image_hurt_l_eye = resize_image(image_hurt_l_eye, 0.8)
    image_hurt_r_eye = resize_image(image_hurt_r_eye, 0.8)
    image_hurt_r_eye_flipped = ImageOps.mirror(image_hurt_r_eye)

    image_happy_l_eye = resize_image(image_happy_l_eye, 0.8)
    image_happy_r_eye = resize_image(image_happy_r_eye, 0.8)
    image_happy_r_eye_flipped = ImageOps.mirror(image_happy_r_eye)

    image_surprised_l_eye = resize_image(image_surprised_l_eye, 0.8)
    image_surprised_r_eye = resize_image(image_surprised_r_eye, 0.8)
    image_surprised_r_eye_flipped = ImageOps.mirror(image_surprised_r_eye)

    def paste_part(part, canvas, pos):
        padded = Image.new("RGBA", canvas.size)
        padded.paste(part, pos)
        return Image.alpha_composite(canvas, padded)

    def create_tee_image(image_left_eye, image_right_eye_flipped):
        tee = Image.new("RGBA", (96, 64), (0, 0, 0, 0))

        tee = paste_part(image_body_shadow_resized, tee, (16, 0))
        tee = paste_part(image_feet_shadow_back, tee, (8, 30))
        tee = paste_part(image_feet_shadow_front, tee, (24, 30))
        tee = paste_part(image_feet_back, tee, (8, 30))
        tee = paste_part(image_body_resized, tee, (16, 0))
        tee = paste_part(image_left_eye, tee, (39, 18))
        tee = paste_part(image_right_eye_flipped, tee, (47, 18))
        tee = paste_part(image_feet_front, tee, (24, 30))

        return tee

    tee_images = {
        "default": create_tee_image(image_left_eye, image_right_eye_flipped),
        "evil": create_tee_image(image_evil_l_eye, image_evil_r_eye_flipped),
        "hurt": create_tee_image(image_hurt_l_eye, image_hurt_r_eye_flipped),
        "happy": create_tee_image(image_happy_l_eye, image_happy_r_eye_flipped),
        "surprised": create_tee_image(
            image_surprised_l_eye, image_surprised_r_eye_flipped
        ),
    }
    return tee_images


@executor
def generate_points_image(data: Dict[str, List[Tuple[dtt.date, int]]]) -> BytesIO:
    font_small = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 16, layout_engine=TEXT_LAYOUT)

    color_light = (100, 100, 100)
    color_dark = (50, 50, 50)
    colors = (
        "orange",
        "red",
        "forestgreen",
        "dodgerblue",
        "orangered",
        "orchid",
        "burlywood",
        "darkcyan",
        "royalblue",
        "olive",
    )

    base = Image.open(f"{DIR}/points_background.png")
    canv = ImageDraw.Draw(base)

    width, height = base.size
    margin = 50

    plot_width = width - margin * 2
    plot_height = height - margin * 2

    end_date = datetime.now(dtt.timezone.utc).date()
    is_leap = end_date.month == 2 and end_date.month == 29
    start_date = min(r[0] for d in data.values() for r in d)
    start_date = min(
        start_date, end_date.replace(year=end_date.year - 1, day=end_date.day - is_leap)
    )

    total_points = max(sum(r[1] for r in d) for d in data.values())
    total_points = max(total_points, 1000)

    days_mult = plot_width / (end_date - start_date).days
    points_mult = plot_height / total_points

    # draw area bg
    bg = Image.new("RGBA", (plot_width, plot_height), color=(0, 0, 0, 100))
    base.alpha_composite(bg, dest=(margin, margin))

    # draw years
    prev_x = margin
    for year in range(start_date.year, end_date.year + 2):
        date = datetime(year=year, month=1, day=1).date()
        if date < start_date:
            continue

        if date > end_date:
            x = width - margin
        else:
            x = margin + (date - start_date).days * days_mult
            xy = ((x, margin), (x, height - margin))
            canv.line(xy, fill=color_dark, width=1)

        text = str(year - 1)
        left, top, right, bottom = font_small.getbbox(text)
        w, h = right - left, bottom
        area_width = x - prev_x
        if w <= area_width:
            xy = (prev_x + center(w, area_width), height - margin + h)
            canv.text(xy, text, fill=color_light, font=font_small)

        prev_x = x

    # draw points
    thresholds = {
        15000: 5000,
        10000: 2500,
        5000: 2000,
        3000: 1000,
        1000: 500,
        0: 250,
    }

    steps = next(s for t, s in thresholds.items() if total_points > t)
    left, top, right, bottom = font_small.getbbox("00.0K")  # max points label width
    w, _ = right - left, bottom
    points_margin = center(w, margin)
    for points in range(0, total_points + 1, int(steps / 5)):
        y = height - margin - points * points_mult
        xy = ((margin, y), (width - margin - 1, y))

        if points % steps == 0:
            canv.line(xy, fill=color_light, width=2)

            text = humanize_points(points)
            left, top, right, bottom = font_small.getbbox(text)
            w, h = right - left, bottom
            xy = (margin - points_margin - w, y + center(h))
            canv.text(xy, text, fill=color_light, font=font_small)
        else:
            canv.line(xy, fill=color_dark, width=1)

    # draw players
    extra = 2
    size = (plot_width * 2, (plot_height + extra * 2) * 2)
    plot = Image.new("RGBA", size, color=(0, 0, 0, 0))
    plot_canv = ImageDraw.Draw(plot)

    labels = []
    for dates, color in reversed(list(zip(data.values(), colors))):
        x = 0
        y = (plot_height + extra) * 2
        xy = [(x, y)]

        prev_date = start_date
        for date, points in dates:
            delta = (date - prev_date).days * days_mult * 2
            x += delta
            if delta / (plot_width * 2) > 0.1:
                xy.append((x, y))

            y -= points * points_mult * 2
            xy.append((x, y))

            prev_date = date

        if prev_date != end_date:
            xy.append((plot_width * 2, y))

        plot_canv.line(xy, fill=color, width=6)

        labels.append((margin - extra + y / 2, color))

    size = (plot_width, plot_height + extra * 2)
    plot = plot.resize(size, resample=Image.LANCZOS, reducing_gap=1.0)  # antialiasing
    base.alpha_composite(plot, dest=(margin, margin - extra))

    # remove overlapping labels
    left, top, right, bottom = font_small.getbbox("0")
    _, h = right - left, bottom
    offset = center(h)
    for _ in range(len(labels)):
        labels.sort()
        for i, (y1, _) in enumerate(labels):
            if i == len(labels) - 1:
                break

            y2 = labels[i + 1][0]
            if y1 - offset >= y2 + offset and y2 - offset >= y1 + offset:
                labels[i] = ((y1 + y2) / 2, "white")
                del labels[i + 1]

    # draw player points
    for y, color in labels:
        points = int((height - margin - y) / points_mult)
        text = humanize_points(points)
        xy = (width - margin + points_margin, y + offset)
        canv.text(xy, text, fill=color, font=font_small)

    # draw header
    def check(w: int, size: int) -> float:
        return w + (size / 3) * (4 * len(data) - 2)

    font = auto_font(
        (f"{DIR}/fonts/normal.ttf", 24), "".join(data), plot_width, check=check
    )
    space = int(font.size / 3)

    x = margin
    for player, color in zip(data, colors):
        y = center(space, margin)
        xy = ((x, y), (x + space, y + space))
        canv.rectangle(xy, fill=color)
        x += space * 2

        left, top, right, bottom = font.getbbox(player)
        w, _ = right - left, bottom
        left, top, right, bottom = font.getbbox(
            "yA"
        )  # max name height, needs to be hardcoded to align names
        _, h = right - left, bottom
        xy = (x, center(h, margin))
        canv.text(xy, player, fill="white", font=font)
        x += w + space * 2

    return save(base.convert("RGB"))


@executor
def generate_profile_image(data: Dict) -> BytesIO:
    font_normal = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 24, layout_engine=TEXT_LAYOUT)
    font_bold = ImageFont.truetype(f"{DIR}/fonts/bold.ttf", 34, layout_engine=TEXT_LAYOUT)
    font_big = ImageFont.truetype(f"{DIR}/fonts/bold.ttf", 48, layout_engine=TEXT_LAYOUT)

    now = datetime.now(dtt.timezone.utc)
    if data["day"] == now.day and data["month"] == now.month:
        img = "birthday"
        color = (54, 70, 137)
    else:
        thresholds = {
            18000: ("justice_2", (184, 81, 50)),
            16000: ("back_in_the_days_3", (156, 162, 142)),
            14000: ("heartcore", (86, 79, 81)),
            12000: ("aurora", (55, 103, 156)),
            10000: ("narcissistic", (122, 32, 43)),
            9000: ("aim_10", (93, 128, 144)),
            8000: ("barren", (196, 172, 140)),
            7000: ("back_in_time", (148, 156, 161)),
            6000: ("nostalgia", (161, 140, 148)),
            5000: ("sweet_shot", (229, 148, 166)),
            4000: ("chained", (183, 188, 198)),
            3000: ("intothenight", (60, 76, 89)),
            2000: ("darkvine", (145, 148, 177)),
            1000: ("crimson_woods", (108, 12, 12)),
            1: ("kobra_4", (148, 167, 75)),
            0: ("stronghold", (156, 188, 220)),
        }

        img, color = next(
            e for t, e in thresholds.items() if data["total_points"]["points"] >= t
        )

    # The accent colours above are hand-picked per background and some are quite
    # dark, which reads poorly on the dark panel. Lift only those below a minimum
    # perceived brightness; bright accents are left exactly as chosen, since
    # clamp_luminance round-trips through HSP and would otherwise shift them too.
    if rgb_to_hsp(color)[2] < 0.6:
        color = clamp_luminance(color, 0.6)

    bg_src = Image.open(f"{DIR}/profile_backgrounds/{img}.png").convert("RGBA")
    top_h = bg_src.height
    outer = 32
    inner = outer // 2
    margin = outer + inner

    font_label = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 18, layout_engine=TEXT_LAYOUT)
    font_value = ImageFont.truetype(f"{DIR}/fonts/bold.ttf", 26, layout_engine=TEXT_LAYOUT)
    font_bar = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 18, layout_engine=TEXT_LAYOUT)

    div_y = top_h - margin + inner
    label_y = div_y + inner
    value_y = label_y + 24
    partners = (data.get("partners") or [])[:3]
    partners_block_h = 62 if partners else 0
    bars_top = value_y + 32 + inner + partners_block_h
    row_h = 30

    cats = [c for c in (data.get("categories") or []) if (c.get("points") or 0) > 0]
    bar_rows = list(cats)
    if (data["total_points"].get("total") or 0) > 0:
        bar_rows.append({
            "name": "TOTAL",
            "points": data["total_points"].get("points") or 0,
            "total": data["total_points"]["total"],
            "maps": sum(c.get("maps", 0) for c in cats),
            "maps_total": sum(c.get("maps_total", 0) for c in cats),
        })

    total_gap = (inner + inner // 2) if (bar_rows and bar_rows[-1]["name"] == "TOTAL") else 0
    extra = (bars_top - top_h) + len(bar_rows) * row_h + total_gap + margin

    full_h = top_h + extra
    scale = full_h / bg_src.height
    scaled = bg_src.resize((round(bg_src.width * scale), full_h))
    left = (scaled.width - bg_src.width) // 2
    base = scaled.crop((left, 0, left + bg_src.width, full_h))
    canv = ImageDraw.Draw(base)
    width, height = base.size

    # draw bg
    size = (width - outer * 2, height - outer * 2)
    bg = round_rectangle(size, 12, color=(0, 0, 0, 150))
    base.alpha_composite(bg, dest=(outer, outer))

    # draw name
    try:
        flag = Image.open(f'{DIR}/flags/{data["favorite_server"]["server"]}.png')
    except FileNotFoundError:
        flag = Image.open(f"{DIR}/flags/UNK.png")

    flag_w, flag_h = flag.size

    name = " " + data["name"]
    left, top, right, bottom = font_bold.getbbox(name)
    w, _ = right - left, bottom
    left, top, right, bottom = font_bold.getbbox("yA")  # hardcoded to align names
    _, h = right - left, bottom

    name_height = 50
    radius = name_height // 2

    size = (flag_w + w + radius * 2, name_height)
    name_bg = round_rectangle(size, radius, color=(150, 150, 150, 75))
    base.alpha_composite(name_bg, dest=(margin, margin))

    x = margin + radius
    dest = (x, margin + center(flag_h, name_height))
    base.alpha_composite(flag, dest=dest)

    xy = (x + flag_w, margin + center(h, name_height))
    canv.text(xy, name, fill="white", font=font_bold)

    # draw rank (the only figure in the left column now)
    points_width = int((width - margin * 2) / 3)

    x = margin + points_width + inner
    y = margin + name_height + inner

    xy = ((x, y), (x, top_h - margin))
    canv.line(xy, fill="white", width=3)

    text = f'#{data["total_points"]["rank"]}'
    left, top, right, bottom = font_big.getbbox(text)
    w, rh = right - left, bottom
    rank_x = margin + center(w, points_width)
    rank_y = y + center(rh, (top_h - margin) - y)  # vertically centred in the left column
    canv.text((rank_x, rank_y), text, fill="white", font=font_big)

    # draw ranks
    types = {
        "TEAM RANK ": (data["team_rank"]["rank"], data["team_rank"]["points"]),
        "RANK ": (data["rank"]["rank"], data["rank"]["points"]),
    }

    left, top, right, bottom = font_bold.getbbox("A")
    _, h = right - left, bottom
    yy = (margin + name_height + inner + h * 1.25, top_h - margin - h * 0.5)

    for (type_, (rank, points)), y in zip(types.items(), yy):
        line = [(type_, "white", font_normal)]
        if rank is None:
            line.append(("UNRANKED", (150, 150, 150), font_bold))
        else:
            line.extend(
                (
                    (f"#{rank}", "white", font_bold),
                    ("   ", "white", font_bold),  # border placeholder
                    (str(points), color, font_bold),
                    (plural(points, " point").upper(), color, font_normal),
                )
            )

        x = width - margin
        for text, color_, font in line[::-1]:
            left, top, right, bottom = font.getbbox(text)
            w, h = right - left, bottom
            x -= w  # adjust x before drawing since we're drawing reverse
            if text == "   ":
                xy = (
                    (x + w / 2, y - h * 0.75),
                    (x + w / 2, y - 1),
                )  # fix line width overflow
                canv.line(xy, fill=color_, width=1)
            else:
                canv.text((x, y - h), text, fill=color_, font=font)

    grey = (170, 170, 170)
    canv.line(((margin, div_y), (width - margin, div_y)), fill="white", width=2)

    def since(ts):
        return datetime.fromtimestamp(ts).strftime("%b %Y").upper() if ts else "N/A"

    def ago(ts):
        if not ts:
            return "N/A"
        days = (now - datetime.fromtimestamp(ts, dtt.timezone.utc)).days
        if days <= 0:
            return "TODAY"
        if days == 1:
            return "1 DAY AGO"
        if days < 30:
            return f"{days} DAYS AGO"
        if days < 365:
            return f"{days // 30} MO AGO"
        return f"{days // 365} YR AGO"

    def next_birthday(ts):
        # the next anniversary of the player's first finish
        if not ts:
            return "N/A"
        ff = datetime.fromtimestamp(ts)
        today = datetime.now()
        for year in (today.year, today.year + 1):
            try:
                bday = ff.replace(year=year)
            except ValueError:  # first finish was on Feb 29
                bday = ff.replace(year=year, month=2, day=28)
            if bday.date() >= today.date():
                return bday.strftime("%b %d").upper()
        return ff.strftime("%b %d").upper()

    earned = data["total_points"].get("points") or 0
    total = data["total_points"].get("total") or 0
    first = data.get("first_finish") or {}
    last = data.get("last_finish") or {}
    last_year = data.get("points_last_year")

    chips = [
        ("PLAYING SINCE", since(first.get("timestamp"))),
        ("LAST ACTIVE", ago(last.get("timestamp"))),
        ("POINTS / YEAR", f"+{last_year}" if last_year else "0"),
        ("COMPLETION", f"{round(earned / total * 100)}%" if total else "N/A"),
        ("NEXT BIRTHDAY", next_birthday(first.get("timestamp"))),
    ]
    chip_w = (width - margin * 2) / len(chips)
    for i, (label, value) in enumerate(chips):
        cx = margin + chip_w * i

        lfont = auto_font(font_label, label, int(chip_w) - 8)
        canv.text((cx + center(lfont.getbbox(label)[2], chip_w), label_y), label, fill=grey, font=lfont)
        vfont = auto_font(font_value, value, int(chip_w) - 8)
        canv.text((cx + center(vfont.getbbox(value)[2], chip_w), value_y), value, fill=color, font=vfont)

    # Favorite partners (top 3)
    if partners:
        ph_y = value_y + 42
        pc_y = value_y + 66
        header = "FAVORITE PARTNERS"
        hf = auto_font(font_label, header, width - margin * 2)
        canv.text(
            (margin + center(hf.getbbox(header)[2], width - margin * 2), ph_y),
            header, fill=grey, font=hf,
        )

        pcell_w = (width - margin * 2) / len(partners)
        texts = [f'{p.get("name", "?")} ({p.get("finishes", 0)})' for p in partners]
        pf = font_value
        for t in texts:  # one shared size that fits the widest cell
            pf = auto_font(pf, t, int(pcell_w) - 12)
        for i, p in enumerate(partners):
            cx = margin + pcell_w * i
            name = str(p.get("name", "?"))
            cnt = f' ({p.get("finishes", 0)})'
            nw = pf.getbbox(name)[2]
            sx = cx + center(nw + pf.getbbox(cnt)[2], pcell_w)
            canv.text((sx, pc_y), name, fill="white", font=pf)
            canv.text((sx + nw, pc_y), cnt, fill=grey, font=pf)

    # Per-category rows plus a TOTAL row, laid out as:
    #   "<Name> (done/total)   [====        ]   pts/total Points"
    # Maps completed sits on the left, points right-aligned, and the bar (map
    # completion) fills the space between them -- so the full row width is used.
    # All rows share one bar_x (widest left label + a gap) so the bars align.
    if bar_rows:
        gap = inner
        bar_h = 14
        h_text = font_bar.getbbox("yA")[3]

        left_labels = [
            f'{r["name"]} ({r.get("maps", 0)}/{r.get("maps_total", 0)})'
            for r in bar_rows
        ]
        point_labels = [f'{r["points"]}/{r["total"]} Points' for r in bar_rows]
        max_lw = max(font_bar.getbbox(s)[2] for s in left_labels)
        max_pw = max(font_bar.getbbox(s)[2] for s in point_labels)
        bar_x = margin + max_lw + gap
        bar_w = (width - margin - max_pw - gap) - bar_x

        for i, r in enumerate(bar_rows):
            is_total = r["name"] == "TOTAL"
            ry = bars_top + row_h * i + (total_gap if is_total else 0)
            ty = ry + center(h_text, row_h)

            if is_total:
                sep_y = int(ry - total_gap / 2)
                canv.line(((margin, sep_y), (width - margin, sep_y)), fill="white", width=1)

            canv.text((margin, ty), left_labels[i], fill="white", font=font_bar)

            by = ry + center(bar_h, row_h)
            track = round_rectangle((bar_w, bar_h), bar_h // 2, color=(255, 255, 255, 45))
            base.alpha_composite(track, dest=(int(bar_x), int(by)))
            maps_total = r.get("maps_total") or 0
            frac = min(1.0, (r.get("maps", 0) / maps_total) if maps_total else 0.0)
            fill_w = max(bar_h, int(bar_w * frac))
            fill = round_rectangle((fill_w, bar_h), bar_h // 2, color=(*color, 255))
            base.alpha_composite(fill, dest=(int(bar_x), int(by)))

            pw = font_bar.getbbox(point_labels[i])[2]
            canv.text((width - margin - pw, ty), point_labels[i], fill=(color if is_total else grey), font=font_bar)

    return save(base.convert("RGB"))


@executor
def generate_map_image(data: Dict) -> BytesIO:
    font_sizes = [48, 36, 32, 26, 24, 22, 20, 16]
    fonts = {
        size: ImageFont.truetype(f"{DIR}/fonts/normal.ttf", size, encoding="unic", layout_engine=TEXT_LAYOUT)
        for size in font_sizes
    }

    name = data["name"]

    try:
        base = Image.open(f"{DIR}/map_backgrounds/{name}.png").convert(mode="RGBA").resize((800, 500))
    except Exception:
        name = re.sub(r'\W', '_', name)
        base = Image.open(f"{DIR}/map_backgrounds/{name}.png").convert(mode="RGBA").resize(
            (800, 500))

    base = base.filter(ImageFilter.GaussianBlur(radius=3))
    canv = ImageDraw.Draw(base)

    color = ColorThief(f"{DIR}/map_backgrounds/{name}.png").get_color(quality=1)
    color = pack_rgb(color)
    color = clamp_luminance(color, 0.7)

    width, height = base.size
    outer = 32
    inner = int(outer / 2)
    margin = int(outer + inner)

    # draw bg
    size = (width - outer * 2, height - outer * 2)
    bg = round_rectangle(size, 12, color=(0, 0, 0, 175))
    base.alpha_composite(bg, dest=(outer, outer))

    # draw header
    mappers = data["mappers"]

    name_height = 50
    radius = 25

    text = name if mappers is None else f"{name} by {mappers}"
    font = auto_font(fonts[36], text, width - margin * 2 - radius * 2)
    left, top, right, bottom = font.getbbox(text)
    w, _ = right - left, bottom

    left, top, right, bottom = font.getbbox("yA")
    _, h = right - left, bottom

    size = (w + radius * 2, name_height)
    name_bg = round_rectangle(size, radius, color=(150, 150, 150, 75))
    base.alpha_composite(name_bg, dest=(margin, margin))

    xy = (margin + radius, margin + center(h, name_height))
    canv.text(xy, text, fill="white", font=font)

    # draw info
    server = data["server"]
    points = data["points"]
    finishers = data["finishers"]
    timestamp = data["timestamp"]

    info_width = (width - margin * 2) / 2.5

    x = margin + info_width + inner
    y = margin + name_height + inner
    xy = ((x, margin + name_height + inner), (x, height - margin))
    canv.line(xy, fill="white", width=3)  # border

    y += inner

    servers = {
        "Novice": (1, 0),
        "Moderate": (2, 5),
        "Brutal": (3, 15),
        "Insane": (4, 30),
        "Dummy": (5, 5),
        "DDmaX.Easy": (4, 0),
        "DDmaX.Next": (4, 0),
        "DDmaX.Pro": (4, 0),
        "DDmaX.Nut": (4, 0),
        "Oldschool": (6, 0),
        "Solo": (4, 0),
        "Race": (2, 0),
        "Fun": (2, 0),
    }

    mult, offset = servers[server]
    stars = int((points - offset) / mult)

    def format_timestamp(ts):
        if isinstance(ts, datetime):
            return ts.strftime("%b %d %Y").upper()
        elif isinstance(ts, str):
            return ts.upper()
        else:
            return "UNKNOWN"

    lines = (
        ((server.upper(), "white", fonts[32]),),
        ((difficulty_stars(stars), "white", fonts[48]),),
        (
            (str(points), color, fonts[26]),
            (plural(points, " point").upper(), "white", fonts[20]),
        ),
        (
            (str(finishers), color, fonts[26]),
            (plural(finishers, " finisher").upper(), "white", fonts[20]),
        ),
        (
            ("RELEASED ", "white", fonts[16]),
            (format_timestamp(timestamp), color, fonts[22]),
        ),
    )

    for line in lines:
        sizes = []
        for t, _, f in line:
            left, top, right, bottom = f.getbbox(t)
            w, h = right - left, bottom
            sizes.append((w, h))
        x = margin + center(sum(w for w, _ in sizes), info_width)
        y += max(h for _, h in sizes)
        for (text, color_, font), (w, h) in zip(line, sizes):
            canv.text((x, y - h), text, fill=color_, font=font)
            x += w

        y += inner

    xy = ((margin, y), (margin + info_width, y))
    canv.line(xy, fill="white", width=3)  # border
    y += inner

    # draw tiles
    tiles = data["tiles"]
    if tiles:
        size = 40
        while size * len(tiles) > info_width:
            size -= 1

        x = margin + center(size * len(tiles), info_width)
        y += center(size, height - margin - y)
        for tile in tiles:
            try:
                tile = Image.open(f"{DIR}/tiles/{tile}.png").resize((size, size))
                base.alpha_composite(tile, dest=(x, y))
                x += size
            except FileNotFoundError:
                continue

    # draw ranks
    ranks = data["ranks"]
    if ranks:
        font = fonts[24]

        def humanize_time(time):
            return "%02d:%05.2f" % divmod(abs(time), 60)

        left, top, right, bottom = font.getbbox(humanize_time(max(r[2] for r in ranks)))
        time_w, _ = right - left, bottom
        left, top, right, bottom = font.getbbox(f"#{max(r[1] for r in ranks)}")
        rank_w, _ = right - left, bottom
        left, top, right, bottom = font.getbbox("yA")
        _, h = right - left, bottom

        y = margin + name_height + inner
        space = (height - margin - y - h * 10) / 11
        for player, rank, time in ranks:
            y += space
            x = margin + info_width + inner * 2
            canv.text((x, y), f"#{rank}", fill="white", font=font)
            x += rank_w + inner

            x += time_w
            text = humanize_time(time)
            left, top, right, bottom = font.getbbox(text)
            w, _ = right - left, bottom
            canv.text((x - w, y), text, fill=color, font=font)
            x += inner

            left, top, right, bottom = font.getbbox(player)
            _, h_org = right - left, bottom
            font_player = auto_font(font, player, width - margin - x)
            left, top, right, bottom = font_player.getbbox(player)
            _, h_new = right - left, bottom
            canv.text(
                (x, y - center(h_org - h_new)), player, fill="white", font=font_player
            )
            y += h
    return save(base.convert("RGB"))


@executor
def generate_hours_image(data: Dict[str, List[Tuple[int, int]]]) -> BytesIO:
    font_small = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 16, layout_engine=TEXT_LAYOUT)

    color_light = (100, 100, 100)
    colors = (
        "orange",
        "red",
        "forestgreen",
        "dodgerblue",
        "orangered",
        "orchid",
        "burlywood",
        "darkcyan",
        "royalblue",
        "olive",
    )

    base = Image.open(f"{DIR}/hours_background.png")
    canv = ImageDraw.Draw(base)

    width, height = base.size
    margin = 50

    plot_width = width - margin * 2
    plot_height = height - margin * 2

    # draw area bg
    bg = Image.new("RGBA", (plot_width, plot_height), color=(0, 0, 0, 100))
    base.alpha_composite(bg, dest=(margin, margin))

    # draw hours
    x = margin
    y = height - margin
    hour_width = int(plot_width / 24)
    now = datetime.now(dtt.timezone.utc)
    for hour in range(25):
        xy = ((x, margin), (x, y - 1))  # fix overflow
        canv.line(xy, fill=color_light, width=1)

        if 0 <= hour <= 23:
            text = str(hour)
            left, top, right, bottom = font_small.getbbox(text)
            w, h = right - left, bottom
            xy = (x + center(w, hour_width), y + h)
            color = "green" if hour == now.hour else color_light
            canv.text(xy, text, fill=color, font=font_small)

        x += hour_width

    # draw players
    extra = 2
    size = (plot_width * 2, (plot_height + extra * 2) * 2)
    plot = Image.new("RGBA", size, color=(0, 0, 0, 0))
    plot_canv = ImageDraw.Draw(plot)

    for hours, color in reversed(list(zip(data.values(), colors))):
        hours = [next((h[1] for h in hours if h[0] == i), 0) for i in range(24)]

        mult = lambda f: plot_height * 2 * (1 - f / max(hours)) + extra

        x = -hour_width
        xy = [(x, mult(hours[-1]))]
        for finishes in hours:
            x += hour_width * 2
            y = mult(finishes)

            rect_xy = ((x - 5, y - 5), (x + 5, y + 5))
            plot_canv.rectangle(rect_xy, fill=color)

            xy.append((x, y))

        xy.append((x + hour_width * 2, mult(hours[0])))
        plot_canv.line(xy, fill=color, width=6)

    size = (plot_width, plot_height + extra * 2)
    plot = plot.resize(size, resample=Image.LANCZOS, reducing_gap=1.0)  # antialiasing
    base.alpha_composite(plot, dest=(margin, margin - extra))

    # draw header
    def check(w: int, size: int) -> int:
        return int(w + (size / 3) * (4 * len(data) - 2))

    font = auto_font(
        (f"{DIR}/fonts/normal.ttf", 24), "".join(data), plot_width, check=check
    )
    space = int(font.size / 3)

    x = margin
    left, top, right, bottom = font.getbbox(
        "yA"
    )  # max name height, needs to be hardcoded to align names
    _, h = right - left, bottom
    for player, color in zip(data, colors):
        y = center(space, margin)
        xy = ((x, y), (x + space, y + space))
        canv.rectangle(xy, fill=color)
        x += space * 2

        left, top, right, bottom = font.getbbox(player)
        w, _ = right - left, bottom
        xy = (x, center(h, margin))
        canv.text(xy, player, fill="white", font=font)
        x += w + space * 2

    return save(base.convert("RGB"))
