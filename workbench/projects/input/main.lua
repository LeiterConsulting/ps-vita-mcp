local seen,held,neutral=0,0,0
local baseline
local function point(panel,x,y)
 for _,p in ipairs(panel) do if p.raw_x==x and p.raw_y==y then return true end end
 return false
end
return {
 update=function(dt,i)
  if not baseline and dt>0 and i.buttons==0 and #i.front==0 and #i.rear==0 then baseline={i.lx,i.ly,i.rx,i.ry} end
  local mask=0
  if i.buttons & (vita.buttons.RIGHT|vita.buttons.CROSS)==(vita.buttons.RIGHT|vita.buttons.CROSS) then mask=mask|1 end
  if baseline and math.abs(i.lx-baseline[1]+64)<=3 and math.abs(i.ly-baseline[2]-64)<=3 then mask=mask|2 end
  if baseline and math.abs(i.rx-baseline[3]-64)<=3 and math.abs(i.ry-baseline[4]+64)<=3 then mask=mask|4 end
  if point(i.front,700,400) then mask=mask|8 end
  if point(i.rear,1300,700) then mask=mask|16 end
  seen=seen|mask;if mask==31 then held=held+1 end
  if baseline and held>0 and i.buttons==0 and #i.front==0 and #i.rear==0 and math.abs(i.lx-baseline[1])<=3 and math.abs(i.ly-baseline[2])<=3 and math.abs(i.rx-baseline[3])<=3 and math.abs(i.ry-baseline[4])<=3 then neutral=1 end
  vita.metric("observed_mask",seen);vita.metric("held_frames",held);vita.metric("neutral_after",neutral)
 end,
 draw=function()
  vita.rect(24,100,912,380,vita.rgb(20,32,49))
  vita.text(44,155,1.2,vita.rgb(64,220,191),"WORKBENCH INPUT TRIAL")
  vita.text(44,225,1,vita.rgb(232,239,249),string.format("Channels %d / 31 | matching frames %d | neutral %d",seen,held,neutral))
 end
}
