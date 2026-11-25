import pytest, json, socket, struct, time
from core import *
def test_inventory():
    c=defaults();assert len(channels(c))==144;assert validate_config(c)==c
@pytest.mark.parametrize('capacity',[-1,513,1.5,True])
def test_capacity(capacity):
    c=defaults();c['modules'][1]['capacity']=capacity
    with pytest.raises(ValueError):validate_config(c)
def test_duplicate():
    c=defaults();c['drives'].append(c['drives'][0]);
    with pytest.raises(ValueError):validate_config(c)
def test_auth(tmp_path):
    s=Store(tmp_path/'db');s.create('admin','long-password-123','Administrator');assert s.login('ADMIN','long-password-123')=='Administrator';assert s.login('admin','wrong') is None
    with pytest.raises(ValueError):s.user_update('admin','Viewer',False)
    assert s.login('admin','long-password-123')=='Administrator';s.password('admin','long-password-123','new-password-123');assert s.login('admin','new-password-123')=='Administrator'
def test_persistence(tmp_path):
    p=tmp_path/'db';s=Store(p);c=defaults();c['names']['DI-001']={'name':'Limit'};s.save(c);s.event('RAISED','DI-001','X','Test');s2=Store(p);assert s2.load()==c;assert len(s2.history())==1
def frame():return {'version':1,'sequence':1,'drives':{'D':{'status':'OK','cw':65535}},'io':{},'modules':{},'alarms':[]}
def test_frame():assert decode_frame(json.dumps(frame()))==frame()
@pytest.mark.parametrize('word',[-1,65536,'1',True])
def test_word(word):
    d=frame();d['drives']['D']['cw']=word
    with pytest.raises(ValueError):decode_frame(json.dumps(d))
def test_nonfinite():
    d=frame();d['drives']['D']['speed']=float('nan')
    with pytest.raises(ValueError):decode_frame(json.dumps(d))
def test_csv():assert csv_safe('=1+1')=="'=1+1";assert csv_safe('normal')=='normal'
def test_tcp():
    with socket.socket() as s:s.bind(('127.0.0.1',0));p=s.getsockname()[1]
    r=Receiver(p);r.start()
    try:
        for _ in range(30):
            try:s=socket.create_connection(('127.0.0.1',p),timeout=.2);break
            except OSError:time.sleep(.03)
        else:pytest.fail('Receiver unavailable')
        with s:
            raw=json.dumps(frame()).encode();packet=struct.pack('!I',len(raw))+raw;s.sendall(packet[:2]);s.sendall(packet[2:]);assert r.inbox.get(timeout=2)[1]==frame()
    finally:r.stop_event.set();r.join(3)
