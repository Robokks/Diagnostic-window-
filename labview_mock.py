"""Run separately to verify TCP integration; never connects to hardware."""
import socket,struct,json,time
from core import defaults,channels
c=defaults();seq=0
while True:
    try:
        with socket.create_connection(('127.0.0.1',8767),timeout=3) as s:
            while True:
                seq+=1;d={'version':1,'sequence':seq,'drives':{x['id']:{'status':'OK','speed':1450,'current':8.4,'cw':1151,'sw':1591} for x in c['drives']},'io':{i:{'status':'OK','value':j%2,'raw':j%2,'quality':'MOCK'} for j,(i,t,m) in enumerate(channels(c))},'modules':{m['id']:{'status':'OK'} for m in c['modules']},'alarms':[]};raw=json.dumps(d).encode();s.sendall(struct.pack('!I',len(raw))+raw);time.sleep(.5)
    except OSError:time.sleep(1)
