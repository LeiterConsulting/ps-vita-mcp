local mask, held_frames, neutral_after = 0, 0, 0
local sample = {buttons=0,lx=128,ly=128,rx=128,ry=128,front={},rear={}}
local baseline
local teal = vita.rgb(64,220,191)
local white = vita.rgb(232,239,249)
local gold = vita.rgb(255,197,98)
local function has_point(panel,x,y)
  for _,p in ipairs(panel) do
    if p.raw_x == x and p.raw_y == y then return true end
  end
  return false
end
return {
  init = function() vita.log("MCP input proof ready; synthetic delivery test") end,
  update = function(dt,input)
    sample = input
    if not baseline and dt > 0 and input.buttons == 0 and #input.front == 0 and #input.rear == 0 then
      baseline = {lx=input.lx,ly=input.ly,rx=input.rx,ry=input.ry}
    end
    local seen = 0
    if input.buttons & (vita.buttons.RIGHT | vita.buttons.CROSS) == (vita.buttons.RIGHT | vita.buttons.CROSS) then seen = seen | 1 end
    if baseline and math.abs(input.lx - (baseline.lx - 96)) <= 3 and math.abs(input.ly - (baseline.ly + 96)) <= 3 then seen = seen | 2 end
    if baseline and math.abs(input.rx - (baseline.rx + 96)) <= 3 and math.abs(input.ry - (baseline.ry - 96)) <= 3 then seen = seen | 4 end
    if has_point(input.front,700,400) then seen = seen | 8 end
    if has_point(input.rear,1300,700) then seen = seen | 16 end
    mask = mask | seen
    if seen == 31 then held_frames = held_frames + 1 end
    if baseline and held_frames > 0 and input.buttons == 0 and #input.front == 0 and #input.rear == 0 and math.abs(input.lx - baseline.lx) <= 3 and math.abs(input.rx - baseline.rx) <= 3 then neutral_after = 1 end
    vita.metric("observed_mask",mask)
    vita.metric("held_frames",held_frames)
    vita.metric("neutral_after",neutral_after)
    vita.metric("buttons",input.buttons)
    vita.metric("front_contacts",#input.front)
    vita.metric("rear_contacts",#input.rear)
    vita.metric("left_x",input.lx)
    vita.metric("right_x",input.rx)
  end,
  draw = function()
    vita.rect(24,100,912,380,vita.rgb(20,32,49))
    vita.text(44,140,1.1,teal,"MCP INPUT DELIVERY PROOF")
    vita.text(44,180,0.9,white,string.format("Observed capabilities %d / 31 | matching frames %d",mask,held_frames))
    vita.text(44,220,0.9,gold,string.format("Returned to neutral after lease: %d",neutral_after))
    vita.text(44,260,0.8,white,string.format("Buttons 0x%05X | front %d | rear %d",sample.buttons,#sample.front,#sample.rear))
    vita.text(44,300,0.8,white,string.format("Left %d,%d | Right %d,%d",sample.lx,sample.ly,sample.rx,sample.ry))
    vita.text(44,360,0.8,white,"Bits: 1 buttons, 2 left stick, 4 right stick, 8 front, 16 rear")
    vita.text(44,410,0.8,white,"Sticks use measured center offsets; request expires alone.")
    vita.text(44,450,0.7,teal,"This tests emulated input delivery, not physical controls.")
  end
}
