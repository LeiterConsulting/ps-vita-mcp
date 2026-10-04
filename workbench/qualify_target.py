"""Prove synthetic input in a disposable app, including an independent self-exit focus gate."""
import re,time
from .runner import Device,Journal,WORKDIR,check_identity,utc
from .session import exclusive
from .power import WorkKeeper
def qualify(expected_control_build,expected_target_build,device=None,root=WORKDIR):
    if not re.fullmatch('[0-9a-f]{64}',expected_target_build):raise ValueError('Pin the exact Input Target build')
    d=device or Device()
    with exclusive():
        j=Journal(root,'input-target');checks=[];started=False;focus_submitted=False;keeper=WorkKeeper(d.control,j.folder)
        try:
            control=d.control_status();check_identity(control,expected_control_build)
            if control.get('version') not in ('0.3.0','0.3.1','0.3.2','0.3.3') or control.get('abi')!=2:raise RuntimeError('Focus cause proof requires Control 0.3.x ABI 2')
            before=d.target();png,screen=d.screen();(j.folder/'before.png').write_bytes(png)
            if before['build_id']!=expected_target_build or screen['target_pid']!=before['pid'] or before['buttons']:raise RuntimeError('Target identity, focus or neutral baseline differs')
            keeper.start(control)
            pid=before['pid'];instance=before['run'];baseline=before['sticks'];j.report['initial_target']=before;j.report['control']=control;j.save()
            def sample():
                s=d.target()
                if s['build_id']!=expected_target_build or s['pid']!=pid or s['run']!=instance or s['frame']<=before['frame']:raise RuntimeError('Target instance or progress changed')
                return s
            values={'buttons':['right','cross'],'ttl_ms':800,'left_stick':[64,192],'right_stick':[192,64],'front_touch':[700,400],'rear_touch':[1300,700]}
            started=True;j.mutation('input_channels',{'target_pid':pid,'requested':values},lambda:d.input(pid,values));time.sleep(1.05)
            s=sample();expired=d.control_status();j.report['channels']=s;j.report['expiry']=expired
            expected=[baseline[0]-64,baseline[1]+64,baseline[2]+64,baseline[3]-64]
            channel_pass=s['last_buttons']==16416 and all(abs(a-b)<=3 for a,b in zip(s['last_sticks'],expected)) and s['front_seen']>before['front_seen'] and s['rear_seen']>before['rear_seen'] and s['front']==[700,400] and s['rear']==[1300,700] and s['active_frames']>before['active_frames'] and s['neutral_frames']>before['neutral_frames'] and s['buttons']==0 and all(abs(a-b)<=3 for a,b in zip(s['sticks'],baseline)) and expired.get('lease_remaining_ms')==0 and expired.get('last_release_reason')==1
            checks.append({'gate':'both sticks, both panels, buttons and expiry without manual release','passed':bool(channel_pass)})
            if not channel_pass:raise RuntimeError('Input channels or expiry readback failed')
            for names,mask in [(['l'],256),(['r'],512),(['up','right','down','left','l','r','triangle','circle','cross','square'],0xf3f0),(['start'],8),(['select'],1)]:
                values={'buttons':names,'ttl_ms':500};j.mutation('button_mask',{'target_pid':pid,'requested':values},lambda:d.input(pid,values));time.sleep(.6)
                s=sample();checks.append({'gate':'button_mask_'+str(mask),'passed':s['last_buttons']==mask,'readback':s})
            png,screen=d.screen();(j.folder/'channels.png').write_bytes(png)
            if screen['target_pid']!=pid:raise RuntimeError('Target lost foreground before focus test')
            prior=d.control_status();check_identity(prior,expected_control_build)
            focus_submitted=True
            receipt=j.mutation('target_self_exit',{'target_pid':pid,'buttons':['start','select'],'ttl_ms':1000},lambda:d.input(pid,{'buttons':['start','select'],'ttl_ms':1000}))
            # Foreground exit and kernel cancellation are asynchronous. Observe only;
            # expiry or another release cause must not become evidence of focus loss.
            observations=[];deadline=time.monotonic()+2
            time.sleep(.1)
            while True:
                after=d.control_status();observations.append(after)
                if after['build_id']!=expected_control_build or after.get('lease_remaining_ms')==0 or time.monotonic()>=deadline:break
                time.sleep(.05)
            j.report['focus_observations']=observations
            png,screen=d.screen();(j.folder/'self-exit.png').write_bytes(png)
            after_time=after.get('last_release_ms',0)
            focus_pass=after['build_id']==expected_control_build and after.get('lease_remaining_ms')==0 and after.get('last_release_reason')==2 and after.get('release_count',0)>prior.get('release_count',0) and screen['target_pid']!=pid and prior['sample_ms']<=after_time<=after['sample_ms']
            checks.append({'gate':'kernel focus cancellation after target exits itself','passed':bool(focus_pass),'before':prior,'input_receipt':receipt,'after':after,'screen':screen,'observations':observations})
            if not focus_pass:raise RuntimeError('Independent focus cancellation was not proven')
            if not all(c['passed'] for c in checks):raise RuntimeError('One or more button mask readbacks failed; independent focus result is retained separately')
            j.report['result']='passed';j.report['software_input_delivery']='qualified in the test app; physical controls are a separate user gate'
        except Exception as error:j.report['result']='failed';j.report['failure_type']=type(error).__name__;j.report['failure']=str(error)[:240]
        finally:
            j.report['checks']=checks;j.report['focus_self_exit_submitted']=focus_submitted
            if started:
                try:j.report['final_release']=j.mutation('release_after_observations',{},d.release)
                except Exception:j.report['final_release']='unconfirmed; one-second lease remains bounded'
            j.report['work_power']=keeper.stop();j.report['finished_utc']=utc();j.save()
        return {**j.report,'evidence_directory':str(j.folder)}
