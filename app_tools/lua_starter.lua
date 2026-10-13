-- A small original paddle prototype for the current DevLoop Lua API.
-- Neutral input enables an attract paddle; stick/D-pad overrides it while held.
-- CROSS restarts. Files, sound, external assets and networking are not used.
local left,right,top,bottom=40,920,145,454
local radius,paddle_half,paddle_y=8,50,435
local x,y,vx,vy,paddle=480,245,180,220,480
local frames,seconds,collisions,restarts,score,bounds_ok=0,0,0,0,0,1
local function clamp(v,lo,hi) return math.max(lo,math.min(hi,v)) end
local function restart()
  x,y,vx,vy,paddle=480,245,180,220,480
  restarts=restarts+1
end
return {
  update=function(dt,input)
    if (input.pressed & vita.buttons.CROSS)~=0 then restart() end
    if dt>0 then
      frames=frames+1;seconds=seconds+dt
      local axis=(input.lx-128)/127
      if (input.buttons & vita.buttons.LEFT)~=0 then axis=axis-1 end
      if (input.buttons & vita.buttons.RIGHT)~=0 then axis=axis+1 end
      axis=clamp(axis,-1,1)
      if math.abs(axis)>.12 then paddle=paddle+axis*480*dt
      else paddle=paddle+clamp(x-paddle,-500*dt,500*dt) end
      paddle=clamp(paddle,left+paddle_half,right-paddle_half)
      local previous_y=y
      x=x+vx*dt;y=y+vy*dt
      if x<left+radius then x=left+radius;vx=math.abs(vx);collisions=collisions+1 end
      if x>right-radius then x=right-radius;vx=-math.abs(vx);collisions=collisions+1 end
      if y<top+radius then y=top+radius;vy=math.abs(vy);collisions=collisions+1 end
      if vy>0 and previous_y+radius<=paddle_y and y+radius>=paddle_y
          and math.abs(x-paddle)<=paddle_half+radius then
        y=paddle_y-radius;vy=-math.abs(vy)
        vx=clamp(vx+(x-paddle)*1.5,-360,360)
        collisions=collisions+1;score=score+1
      end
      if y>bottom-radius then restart() end
      if x<left+radius or x>right-radius or y<top+radius or y>bottom-radius
          or paddle<left+paddle_half or paddle>right-paddle_half then bounds_ok=0 end
    end
    vita.metric("frames",frames);vita.metric("seconds",seconds)
    vita.metric("collisions",collisions);vita.metric("restarts",restarts)
    vita.metric("score",score);vita.metric("bounds_ok",bounds_ok)
    vita.metric("paddle_x",paddle);vita.metric("ball_x",x)
  end,
  draw=function()
    local teal=vita.rgb(64,220,191)
    vita.rect(left,top,right-left,bottom-top,vita.rgb(20,32,49))
    vita.line(left,top,right,top,teal)
    vita.rect(paddle-paddle_half,paddle_y,paddle_half*2,10,teal)
    vita.circle(x,y,radius,vita.rgb(255,198,86))
    vita.text(44,115,1,teal,"VITA PADDLE - original Lua prototype")
    vita.text(44,465,.7,teal,string.format("Score %d  Hits %d  CROSS restarts | Stick / D-pad moves",score,collisions))
  end
}
