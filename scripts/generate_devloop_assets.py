from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[1]
dest = ROOT / "assets/vita_devloop"
dest.mkdir(exist_ok=True)
font_path = Path("C:/Windows/Fonts/seguisb.ttf")
def font(size):
    return ImageFont.truetype(str(font_path), size) if font_path.exists() else ImageFont.load_default(size=size)
def save(image, name):
    p = image.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    p.info.clear(); p.save(dest / name, bits=8)
icon = Image.new("RGB", (128,128), (13,24,39)); d=ImageDraw.Draw(icon)
d.rounded_rectangle((7,7,120,120),radius=25,outline=(64,220,191),width=3)
for box in ((22,44,46,84),(82,44,106,84)):
    d.rounded_rectangle(box,radius=5,fill=(64,220,191))
d.line((48,64,80,64),fill=(255,197,98),width=5)
d.ellipse((56,56,72,72),fill=(255,197,98)); save(icon,"icon0.png")
bg = Image.new("RGB",(840,500),(10,17,29)); bg.paste(icon,(45,52)); d=ImageDraw.Draw(bg)
d.text((198,72),"Vita DevLoop",font=font(40),fill=(232,239,249))
d.text((198,133),"A live experiment, connected to MCP",font=font(24),fill=(64,220,191))
d.text((49,230),"Live Lua / physical inputs / screenshots / rollback",font=font(24),fill=(151,170,195))
d.text((49,278),"Version 1.03 - Edit, push, run",font=font(22),fill=(151,170,195)); save(bg,"bg.png")
startup=Image.new("RGB",(280,158),(20,32,49)); startup.paste(icon.resize((84,84)),(98,12)); d=ImageDraw.Draw(startup)
d.text((140,123),"Vita DevLoop",anchor="mm",font=font(23),fill=(64,220,191)); save(startup,"startup.png")
print("Generated indexed opaque Vita DevLoop package artwork")
