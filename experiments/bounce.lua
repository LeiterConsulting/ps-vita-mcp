-- Change the colours/speed/text, save, and push again: no VPK rebuild needed.
local x, y, t, taps = 480, 285, 0, 0
local input = {front={}, rear={}}
local teal, gold = vita.rgb(64,220,191), vita.rgb(255,197,98)
return {
  init = function() vita.log("Bounce experiment ready") end,
  update = function(dt, sample)
    input = sample; t = t + dt
    local dx, dy = (sample.lx-128)/127, (sample.ly-128)/127
    x = math.max(45, math.min(915, x + dx*280*dt))
    y = math.max(130, math.min(455, y + dy*280*dt))
    if #sample.front > 0 then
      x = math.max(45, math.min(915, sample.front[1].x*vita.width))
      y = math.max(130, math.min(455, sample.front[1].y*vita.height))
    end
    if sample.pressed & vita.buttons.CROSS ~= 0 then
      x, y, taps = 480, 285, taps+1; vita.log("Ball reset by CROSS")
    end
    vita.metric("x", x); vita.metric("y", y); vita.metric("seconds", t)
    vita.metric("resets", taps); vita.metric("touches", #sample.front)
  end,
  draw = function()
    vita.rect(24,100,912,380,vita.rgb(20,32,49))
    for gx=44,916,40 do vita.line(gx,110,gx,470,vita.rgb(29,48,65)) end
    for gy=110,470,40 do vita.line(34,gy,926,gy,vita.rgb(29,48,65)) end
    vita.text(44,140,1.0,teal,"LIVE LUA PLAYGROUND")
    vita.text(44,169,0.8,vita.rgb(151,170,195),"Left stick moves | Front touch places | CROSS resets")
    local radius = 17 + math.sin(t*3)*3
    vita.circle(x+3,y+4,radius,vita.rgb(9,18,30))
    vita.circle(x,y,radius,#input.rear>0 and gold or teal)
    vita.circle(x-4,y-4,3,vita.rgb(222,255,247))
    vita.text(44,450,0.8,gold,string.format("time %.1fs  |  resets %d  |  x %.0f y %.0f",t,taps,x,y))
  end
}
