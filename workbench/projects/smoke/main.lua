local frames,seconds=0,0
return {
 update=function(dt,input)
   frames=frames+1;seconds=seconds+dt
   vita.metric("frames",frames);vita.metric("seconds",seconds)
 end,
 draw=function()
   vita.rect(24,100,912,380,vita.rgb(20,32,49))
   vita.text(44,155,1.2,vita.rgb(64,220,191),"WORKBENCH SMOKE TRIAL")
   vita.text(44,225,1,vita.rgb(232,239,249),string.format("Frames %d | seconds %.2f",frames,seconds))
 end
}
