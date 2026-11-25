"""Read-only monitoring core; no hardware command path."""
import csv, json, math, sqlite3, hashlib, secrets, hmac, time, re, socket, struct, threading, queue
from pathlib import Path
TYPES={'DI':60,'DO':50,'AI':20,'AO':4,'CI':8,'CO':2}
ROLES=('Administrator','Engineer','Operator','Viewer')
MAX_FRAME=1024*1024

def defaults():
    return {'system':{'plc':'Siemens S7-1515','firmware':'Unconfirmed','pc':'Windows 11 / LabVIEW','ioBus':'Local rack'},'drives':[dict(id=i,model='SINAMICS '+i.split('-')[0],bus='PROFINET',address='',telegram='Unconfirmed',pzd=32,servo=i.startswith('S120')) for i in ('S120-01','G120-01','G120-02')], 'modules':[dict(id='CPU',type='CPU',name='S7-1515',slot='CPU',capacity=0,orderNo='')]+[dict(id=f'{t}-{i+1:02}',type=t,name=t+' module',slot=f'{t}{i+1}',capacity=n,orderNo='') for t,ns in [('DI',[32,28]),('DO',[32,18]),('AI',[20]),('AO',[4]),('CI',[8]),('CO',[2])] for i,n in enumerate(ns)],'names':{},'maps':{},'refs':{}}

def channels(c):
    out=[]; counts={t:0 for t in TYPES}
    for m in c['modules']:
        t=m['type']
        if t=='CPU':continue
        for j in range(m['capacity']):
            counts[t]+=1; out.append((f'{t}-{counts[t]:03}',t,m['id']))
    return out

def validate_config(c):
    if not isinstance(c,dict) or set(c)!=set(defaults()):raise ValueError('Invalid configuration keys')
    for key in ('system','names','maps','refs'):
        if not isinstance(c[key],dict):raise ValueError(key)
    ids=set()
    for k in ('drives','modules'):
        if not isinstance(c[k],list) or len(c[k])>128:raise ValueError(k)
        for x in c[k]:
            i=x['id']
            if not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',i) or i in ids:raise ValueError('Invalid or duplicate ID')
            ids.add(i)
            if k=='drives' and (type(x['pzd']) is not int or not 1<=x['pzd']<=32 or type(x['servo']) is not bool):raise ValueError('Invalid drive')
            if k=='modules' and (x['type'] not in (*TYPES,'CPU') or type(x['capacity']) is not int or not (x['capacity']==0 if x['type']=='CPU' else 1<=x['capacity']<=512)):raise ValueError('Invalid module capacity/type')
    if sum(m['type']=='CPU' for m in c['modules'])!=1 or len(channels(c))>4096:raise ValueError('Require one CPU and at most 4096 channels')
    return c

def csv_safe(v):
    s=str(v if v is not None else '')
    return "'"+s if s.lstrip().startswith(('=','+','-','@')) or s.startswith(('\t','\r','\n')) else s

def export_csv(path,headers,rows):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows([csv_safe(v) for v in row] for row in rows)

def read_csv(path):
    if Path(path).stat().st_size>MAX_FRAME:raise ValueError('CSV too large')
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def hash_password(p,s):return hashlib.pbkdf2_hmac('sha256',p.encode(),s,600000)
class Store:
    def __init__(self,path):
        self.db=sqlite3.connect(path); self.db.execute('PRAGMA journal_mode=WAL');self.db.executescript('CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY COLLATE NOCASE, salt BLOB, hash BLOB, role TEXT, active INTEGER); CREATE TABLE IF NOT EXISTS config(id INTEGER PRIMARY KEY, body TEXT); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time TEXT, event TEXT, target TEXT, code TEXT, description TEXT);')
    def users(self):return self.db.execute('SELECT name,role,active FROM users ORDER BY name').fetchall()
    def create(self,name,p,role):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}',name) or not 12<=len(p)<=256 or role not in ROLES:raise ValueError('Invalid username, password (12–256 characters), or role')
        s=secrets.token_bytes(16)
        with self.db:self.db.execute('INSERT INTO users VALUES(?,?,?,?,1)',(name,s,hash_password(p,s),role))
    def login(self,n,p):
        r=self.db.execute('SELECT salt,hash,role,active FROM users WHERE name=?',(n,)).fetchone()
        if len(p)>256:return None
        digest=hash_password(p,r[0] if r else bytes(16))
        return r[2] if r and hmac.compare_digest(digest,r[1]) and r[3] else None
    def password(self,n,old,new):
        if not self.login(n,old) or not 12<=len(new)<=256:raise ValueError('Invalid password')
        s=secrets.token_bytes(16)
        with self.db:self.db.execute('UPDATE users SET salt=?,hash=? WHERE name=?',(s,hash_password(new,s),n))
    def user_update(self,n,role,active):
        if role not in ROLES:raise ValueError('Invalid role')
        with self.db:
            self.db.execute('UPDATE users SET role=?,active=? WHERE name=?',(role,int(active),n))
            if not self.db.execute("SELECT 1 FROM users WHERE role='Administrator' AND active=1").fetchone():raise ValueError('At least one active administrator required')
    def load(self):
        r=self.db.execute('SELECT body FROM config WHERE id=1').fetchone();return validate_config(json.loads(r[0])) if r else defaults()
    def save(self,c):
        validate_config(c)
        with self.db:self.db.execute('INSERT OR REPLACE INTO config VALUES(1,?)',(json.dumps(c,allow_nan=False),))
    def event(self,kind,target,code,desc):
        with self.db:self.db.execute('INSERT INTO events(time,event,target,code,description) VALUES(datetime(\'now\'),?,?,?,?)',(kind,target,code,desc))
    def history(self):return self.db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 10000').fetchall()

def decode_frame(raw):
    def reject(v):raise ValueError('Nonfinite number')
    d=json.loads(raw,parse_constant=reject)
    if not isinstance(d,dict) or d.get('version')!=1 or type(d.get('sequence')) is not int or d['sequence']<0:raise ValueError('Invalid frame header')
    for key in ('drives','io','modules'):
        if not isinstance(d.get(key),dict) or len(d[key])>4096:raise ValueError(key)
        for i,x in d[key].items():
            if not isinstance(x,dict) or x.get('status') not in ('OK','WARN','FAULT','OFFLINE','UNKNOWN'):raise ValueError('Invalid state')
            for v in x.values():
                if isinstance(v,float) and not math.isfinite(v):raise ValueError('Nonfinite')
    if not isinstance(d.get('alarms'),list) or len(d['alarms'])>1024:raise ValueError('Invalid alarms')
    for a in d['alarms']:
        if not isinstance(a,dict) or a.get('severity') not in ('WARN','FAULT') or any(not isinstance(a.get(k),str) or len(a[k])>2048 for k in ('target','code','description')):raise ValueError('Invalid alarm')
    for x in d['drives'].values():
        for k in ('cw','sw'):
            if k in x and (type(x[k]) is not int or not 0<=x[k]<=65535):raise ValueError('Invalid word')
    return d

def recv_exact(s,n):
    b=bytearray()
    while len(b)<n:
        x=s.recv(n-len(b))
        if not x:raise EOFError('Disconnected')
        b.extend(x)
    return bytes(b)
class Receiver(threading.Thread):
    def __init__(self,port=8767):
        super().__init__(daemon=True);self.port=port;self.stop_event=threading.Event();self.inbox=queue.Queue(maxsize=64);self.error='Waiting for LabVIEW'
    def run(self):
        try:
            with socket.socket() as srv:
                srv.bind(('127.0.0.1',self.port));srv.listen(1);srv.settimeout(.5)
                while not self.stop_event.is_set():
                    try:conn,_=srv.accept()
                    except socket.timeout:continue
                    with conn:
                        conn.settimeout(2);seq=-1
                        try:
                            while not self.stop_event.is_set():
                                n=struct.unpack('!I',recv_exact(conn,4))[0]
                                if not 0<n<=MAX_FRAME:raise ValueError('Frame size')
                                d=decode_frame(recv_exact(conn,n))
                                if d['sequence']<=seq:raise ValueError('Out-of-order sequence')
                                seq=d['sequence'];self.inbox.put((time.monotonic(),d),timeout=1);self.error='Receiving'
                        except (OSError,EOFError,ValueError,queue.Full,RecursionError) as e:self.error=str(e)
        except OSError as e:self.error=str(e)
