local sample = {buttons=0, lx=128, ly=128, rx=128, ry=128, front={}, rear={}, motion={read_result=-1,ax=0,ay=0,az=0,gx=0,gy=0,gz=0}}
local teal, gold, white = vita.rgb(64,220,191), vita.rgb(255,197,98), vita.rgb(232,239,249)
return {
  init = function() vita.log("Physical input scope ready") end,
  update = function(dt, input)
    sample = input
    vita.metric("buttons",input.buttons); vita.metric("front",#input.front); vita.metric("rear",#input.rear)
    vita.metric("ax",input.motion.ax); vita.metric("ay",input.motion.ay); vita.metric("az",input.motion.az)
  end,
  draw = function()
    vita.rect(24,100,912,380,vita.rgb(20,32,49))
    vita.text(44,139,1.0,teal,"PHYSICAL INPUT SCOPE")
    vita.text(44,170,0.8,white,string.format("buttons 0x%05X  |  motion result %d",sample.buttons,sample.motion.read_result))
    vita.text(44,200,0.8,gold,string.format("accel %.3f %.3f %.3f",sample.motion.ax,sample.motion.ay,sample.motion.az))
    vita.text(44,230,0.8,white,string.format("gyro  %.3f %.3f %.3f",sample.motion.gx,sample.motion.gy,sample.motion.gz))
    for n, stick in ipairs({{sample.lx,sample.ly,190},{sample.rx,sample.ry,420}}) do
      vita.rect(stick[3]-64,275,128,128,vita.rgb(29,48,65))
      vita.line(stick[3]-64,339,stick[3]+64,339,white)
      vita.line(stick[3],275,stick[3],403,white)
      vita.circle(stick[3]+(stick[1]-128)*0.45,339+(stick[2]-128)*0.45,10,teal)
    end
    vita.rect(580,275,310,128,vita.rgb(29,48,65))
    for _, point in ipairs(sample.front) do vita.circle(580+point.x*310,275+point.y*128,8,teal) end
    for _, point in ipairs(sample.rear) do vita.circle(580+point.x*310,275+point.y*128,5,gold) end
    vita.text(44,450,0.8,white,string.format("Front contacts %d | Rear contacts %d | Touch dots: teal front, gold rear",#sample.front,#sample.rear))
  end
}
