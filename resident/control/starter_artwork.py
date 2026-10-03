from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
folder=Path(__file__).resolve().parent/'assets';folder.mkdir(exist_ok=True)
for name,size in [('icon0.png',(128,128)),('bg.png',(840,500)),('startup.png',(280,158))]:
    canvas=Image.new('RGB',size,(10,17,29));draw=ImageDraw.Draw(canvas)
    draw.rectangle((8,8,size[0]-9,size[1]-9),outline=(64,220,191),width=3)
    font=ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf',20 if name=='icon0.png' else 24)
    draw.text((size[0]//2,size[1]//2),'CONTROL' if name=='icon0.png' else 'Control Starter',anchor='mm',font=font,fill=(220,232,244))
    image=canvas.quantize(colors=256);image.info.clear();image.save(folder/name,bits=8)
print('Control Starter package artwork prepared.')
