"""Generate original simple lab artwork; no external images or private assets."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent


def main():
    folder = ROOT / 'assets'
    folder.mkdir(exist_ok=True)
    for name, size in [('icon0.png', (128, 128)), ('bg.png', (840, 500)), ('startup.png', (280, 158))]:
        image = Image.new('RGB', size, (12, 21, 35))
        draw = ImageDraw.Draw(image)
        width, height = size
        draw.rounded_rectangle((width * .08, height * .08, width * .92, height * .92), radius=height * .08,
                               outline=(57, 221, 195, 255), width=max(2, height // 50))
        draw.line((width * .2, height * .65, width * .37, height * .45, width * .53, height * .58,
                   width * .79, height * .29), fill=(251, 198, 76, 255), width=max(3, height // 25))
        if name != 'icon0.png':
            font = ImageFont.load_default(size=max(14, height // 12))
            draw.text((width * .13, height * .76), 'VITA LIFECYCLE LAB', font=font, fill=(225, 234, 244, 255))
        image.quantize(colors=256).save(folder / name, optimize=True, bits=8)
    (folder / 'template.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<livearea style="a1" format-ver="01.00" content-rev="1">\n'
        '  <livearea-background><image>bg.png</image></livearea-background>\n'
        '  <gate><startup-image>startup.png</startup-image></gate>\n'
        '</livearea>\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
