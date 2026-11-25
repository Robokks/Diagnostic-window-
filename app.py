import sys, os, json, time, copy, random
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtWidgets import *
from core import *
STYLE='''QWidget{background:#080f1b;color:#e9f2fc;font:13px Segoe UI;} QFrame,QGroupBox,QTableWidget{background:#111d2e;border:1px solid #26384d;border-radius:8px;} QPushButton,QComboBox,QLineEdit,QPlainTextEdit{background:#18334a;border:1px solid #345068;border-radius:6px;padding:8px;} QPushButton:hover{border-color:#39d5ef;} QPushButton:disabled{color:#66788a;} QHeaderView::section{background:#152439;color:#8ca3ba;padding:8px;border:0;} QTableWidget::item:selected{background:#18566a;} QLabel{background:transparent;} QTabBar::tab{background:#152439;padding:10px;} QTabBar::tab:selected{background:#087a91;}'''
PAGES=['Overview','Drive Diagnostics','PLC & Rack','I/O Explorer','Fault Center','Event History','Configuration']
SIGNALS=['speed_setpoint','speed','torque_setpoint','torque','current','speed_low','speed_high','torque_low','torque_high','current_limit','position_setpoint','position']
CW=['ON/OFF1','OFF2 permission','OFF3 permission','Enable operation','Ramp enable','Ramp continue','Setpoint enable','Fault acknowledge','Jog 1','Jog 2','PLC control','Direction / configured']
SW=['Ready to switch on','Ready to operate','Operation enabled','Fault active','OFF2 inactive','OFF3 inactive','Switch-on inhibited','Warning active','Speed deviation','Control requested','Threshold','Torque limit']

def text_dialog(parent,title,label,value='',password=False):
    v,ok=QInputDialog.getText(parent,title,label,QLineEdit.EchoMode.Password if password else QLineEdit.EchoMode.Normal,str(value));return v if ok else None

def table(headers,rows):
    t=QTableWidget(len(rows),len(headers));t.setHorizontalHeaderLabels(headers);t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);t.verticalHeader().hide()
    for r,row in enumerate(rows):
        for c,v in enumerate(row):
            item=QTableWidgetItem('—' if v is None else str(v));t.setItem(r,c,item)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);return t

def simulator(c,alarms,seq):
    bad={a['target']:a['severity'] for a in alarms};return {'version':1,'sequence':seq,'drives':{d['id']:dict(status=bad.get(d['id'],'OK'),speed=1450,current=8.4,torque=31.6,speed_setpoint=1600,torque_setpoint=34,cw=0x047f,sw=0x0287 if d['id'] in bad else 0x0637,position=120.45,position_setpoint=125) for d in c['drives']},'io':{i:dict(status=bad.get(i,'OK'),value=int(j%3==0) if t in ('DI','DO','CO') else j*1.2,raw=j,quality='SIMULATED') for j,(i,t,m) in enumerate(channels(c))},'modules':{m['id']:dict(status='WARN' if any(i in bad for i,t,mid in channels(c) if mid==m['id']) else 'OK') for m in c['modules']},'alarms':alarms.copy()}
class Window(QMainWindow):
    def __init__(self,store):
        super().__init__();self.store=store;self.c=store.load();self.role=None;self.user=None;self.demo=False;self.mode='LIVE';self.data={};self.last=0;self.activity=time.monotonic();self.active={};self.alarms=[];self.seq=0;self.page=0;self.drive='';self.sub=0;self.io_type='ALL';self.io_state='ALL';self.query='';self.receiver=Receiver();self.receiver.start();self.resize(1400,850);self.setWindowTitle('SYSTEM WINDOW | Industrial Monitoring');self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(300);self.login()
    def allowed(self,action):return self.role=='Administrator' or (self.role=='Engineer' and action in ('configure','export','simulate')) or (self.role=='Operator' and action=='simulate')
    def require(self,a):
        if not self.allowed(a):raise PermissionError('Access denied')
    def safe(self,fn):
        try:fn()
        except Exception as e:QMessageBox.warning(self,'System Window',str(e))
    def button(self,label,fn,action=None):
        b=QPushButton(label);b.clicked.connect(lambda:self.safe(fn));b.setEnabled(action is None or self.allowed(action));return b
    def login(self):
        self.role=None;self.user=None;self.demo=False;self.mode='LIVE';self.data={};self.last=0;self.active={};self.alarms=[];w=QWidget();l=QVBoxLayout(w);l.setAlignment(Qt.AlignmentFlag.AlignCenter);title=QLabel('SYSTEM WINDOW  |  ENGINEERING WORKSPACE');title.setStyleSheet('font-size:28px;color:#39d5ef;font-weight:bold');l.addWidget(title);setup=not self.store.users();l.addWidget(QLabel('Create first Administrator' if setup else 'Secure workspace access'));n=QLineEdit();n.setPlaceholderText('Username');p=QLineEdit();p.setPlaceholderText('Password');p.setEchoMode(QLineEdit.EchoMode.Password);l.addWidget(n);l.addWidget(p)
        def submit():
            if setup:self.store.create(n.text(),p.text(),'Administrator')
            r=self.store.login(n.text(),p.text());p.clear()
            if not r:raise ValueError('Invalid credentials')
            self.role=r;self.user=n.text();self.c=self.store.load();self.activity=time.monotonic();self.build()
        def demo():self.demo=True;self.mode='SIMULATION';self.role='Administrator';self.user='Demo';self.c=defaults();self.activity=time.monotonic();self.build()
        l.addWidget(self.button('Create account' if setup else 'Sign in',submit));l.addWidget(self.button('Enter isolated demo',demo));self.setCentralWidget(w)
    def build(self):
        w=QWidget();root=QHBoxLayout(w);side=QVBoxLayout();root.addLayout(side);brand=QLabel('SYSTEM WINDOW');brand.setStyleSheet('font-size:22px;color:#39d5ef;font-weight:bold');side.addWidget(brand)
        for i,p in enumerate(PAGES):side.addWidget(self.button(p,lambda i=i:self.navigate(i),'configure' if i==6 else None))
        side.addStretch();side.addWidget(QLabel('INDUSTRIAL SYSTEM MONITORING\nLabVIEW data source'));side.addWidget(self.button('Sign out',self.login));main=QVBoxLayout();root.addLayout(main,1);top=QHBoxLayout();main.addLayout(top);self.heading=QLabel();self.heading.setStyleSheet('font-size:24px;font-weight:bold');top.addWidget(self.heading);top.addStretch();self.status=QLabel();top.addWidget(self.status);top.addWidget(QLabel(f'{self.user} · {self.role}'));top.addWidget(self.button('Users',self.users,'users'));top.addWidget(self.button('Password',self.password));top.addWidget(self.button('Switch mode',self.switch,'simulate'));top.addWidget(self.button('Inject fault',self.inject,'simulate'));top.addWidget(self.button('Clear demo faults',self.clear,'simulate'));self.content=QVBoxLayout();main.addLayout(self.content,1);main.addWidget(QLabel('Monitoring only · No PLC / drive write commands'));self.setCentralWidget(w);self.navigate(0)
    def switch(self):
        self.require('simulate')
        if self.demo:raise ValueError('Sign in to use live mode')
        self.mode='SIMULATION' if self.mode=='LIVE' else 'LIVE';self.data={};self.last=0;self.active={};self.alarms=[];self.render()
    def navigate(self,i):
        if i==6:self.require('configure')
        self.page=i;self.render()
    def tick(self):
        if not self.role:return
        if time.monotonic()-self.activity>1800 and QApplication.activeModalWidget() is None:self.login();return
        changed=False
        while True:
            try:ts,d=self.receiver.inbox.get_nowait()
            except queue.Empty:break
            if self.mode=='LIVE':self.last=ts;self.data=d;self.transitions(d['alarms']);changed=True
        if self.mode=='SIMULATION':self.seq+=1;self.data=simulator(self.c,self.alarms,self.seq);self.transitions(self.alarms);changed=True
        if self.mode=='LIVE' and time.monotonic()-self.last>3:
            if self.data:self.data={};changed=True
        self.status.setText('SIMULATION ONLY' if self.mode=='SIMULATION' else 'LIVE · LabVIEW' if self.data else 'OFFLINE / STALE')
        if changed and self.page in (0,2,4):self.render()
        elif changed and self.page in (1,3):self.update_live()
    def transitions(self,alarms):
        new={(a['target'],a['code']):a for a in alarms}
        if not self.demo:
            for k,a in new.items():
                if k not in self.active:self.store.event(self.mode+' RAISED',*k,a['description'])
            for k,a in self.active.items():
                if k not in new:self.store.event(self.mode+' CLEARED',*k,a['description'])
        self.active=new
    def inject(self):
        self.require('simulate')
        if self.mode!='SIMULATION':raise ValueError('Simulation only')
        ids=[d['id'] for d in self.c['drives']]+[i for i,t,m in channels(self.c)];ids=[i for i in ids if not any(a['target']==i for a in self.alarms)]
        if ids:self.alarms.append(dict(target=random.choice(ids),code='DEMO-001',description='Simulated diagnostic mismatch',severity='FAULT',cause='Simulated feedback mismatch',action='Inspect wiring and feedback using approved procedures'))
    def clear(self):
        self.require('simulate')
        if self.mode!='SIMULATION':raise ValueError('Simulation only')
        self.alarms=[]
    def save(self):
        self.require('configure');validate_config(self.c)
        if not self.demo:self.store.save(self.c)
    def clear_layout(self):
        while self.content.count():
            item=self.content.takeAt(0);w=item.widget()
            if w:w.deleteLater()
    def add(self,w):self.content.addWidget(w);return w
    def get(self,k,i):return self.data.get(k,{}).get(i,{})
    def render(self):
        self.clear_layout();self.heading.setText(PAGES[self.page]);self.live_table=None
        if self.page==0:
            metrics=QLabel(f'SYSTEM STATUS: {"UNKNOWN" if not self.data else "FAULT / WARNING" if self.active else "MONITORING"}     |     DRIVES: {len(self.c["drives"])}     |     I/O: {len(channels(self.c))}     |     ALARMS: {len(self.active)}');metrics.setStyleSheet('font-size:20px;color:#39d5ef;padding:16px');self.add(metrics);self.add(QLabel('Drive network'));t=self.add(table(['Drive','Model','Health','Speed RPM','Current A'],[[d['id'],d['model'],self.get('drives',d['id']).get('status','UNKNOWN'),self.get('drives',d['id']).get('speed'),self.get('drives',d['id']).get('current')] for d in self.c['drives']]));t.cellDoubleClicked.connect(lambda r,c:self.open_drive(t.item(r,0).text()));self.add(QLabel('Local rack health'));self.add(table(['Module','Type','Slot','Health'],[[m['id'],m['type'],m['slot'],self.get('modules',m['id']).get('status','UNKNOWN')] for m in self.c['modules']]))
        elif self.page==1:self.drive_page()
        elif self.page==2:
            t=self.add(table(['Module','Type','Name','Slot','Capacity','Order number','Health'],[[m[k] for k in ('id','type','name','slot','capacity','orderNo')]+[self.get('modules',m['id']).get('status','UNKNOWN')] for m in self.c['modules']]));t.cellDoubleClicked.connect(lambda r,c:self.open_module(t.item(r,1).text()))
        elif self.page==3:self.io_page()
        elif self.page==4:
            a=list(self.active.values());t=self.add(table(['Severity','Equipment','Code','Description'],[[x[k] for k in ('severity','target','code','description')] for x in a]));t.cellDoubleClicked.connect(lambda r,c:QMessageBox.information(self,'Diagnostic guidance',str(a[r].get('cause','Cause not verified'))+'\n'+str(a[r].get('action','Consult approved maintenance documentation'))))
        elif self.page==5:
            rows=[] if self.demo else self.store.history();self.add(self.button('Export history CSV',lambda:self.export(['ID','UTC','Event','Equipment','Code','Description'],rows),'export'));self.add(table(['ID','UTC','Event','Equipment','Code','Description'],rows))
        else:self.config_page()
    def open_drive(self,i):self.drive=i;self.navigate(1)
    def open_module(self,t):self.io_type=t if t in TYPES else 'ALL';self.navigate(3)
    def drive_page(self):
        combo=QComboBox();combo.addItems([d['id'] for d in self.c['drives']]);combo.setCurrentText(self.drive);self.drive=combo.currentText();self.add(combo);combo.currentTextChanged.connect(lambda v:self.set_drive(v));tabs=QTabWidget();self.add(tabs);self.drive_tabs=tabs
        if not self.drive:return
        for name in ('Signals','Control Word','Status Word','Editable PZD TX','Editable PZD RX','References'):
            tab=QWidget();l=QVBoxLayout(tab);tabs.addTab(tab,name)
            if name=='Signals':self.signal_table=table(['Signal','Engineering value','Unit','Raw counts','PZD'],[]);l.addWidget(self.signal_table)
            elif name in ('Control Word','Status Word'):
                t=table(['Bit','Meaning (verify telegram)','Value'],[]);l.addWidget(t);setattr(self,'cw_table' if name=='Control Word' else 'sw_table',t)
            elif name.startswith('Editable'):
                direction=name[-2:];rows=self.mapping(direction);t=table(['Word','Signal','Class','Description','Parameter','Scale'],rows);l.addWidget(t);t.cellDoubleClicked.connect(lambda r,c,d=direction:self.safe(lambda:self.edit_mapping(d,r,c)));l.addWidget(self.button('Export mapping',lambda d=direction:self.export(['Word','Signal','Class','Description','Parameter','Scale'],self.mapping(d)),'export'));l.addWidget(self.button('Import mapping',lambda d=direction:self.import_mapping(d),'configure'))
            else:
                refs=self.c['refs'].get(self.drive,{'refSpeed':3000,'refTorque':100,'refCurrent':20,'positionScale':1000});t=table(['Reference','Value'],list(refs.items()));l.addWidget(t);t.cellDoubleClicked.connect(lambda r,c:self.safe(lambda:self.edit_ref(t.item(r,0).text(),t.item(r,1).text())))
        tabs.setCurrentIndex(self.sub);tabs.currentChanged.connect(lambda i:setattr(self,'sub',i));self.update_live()
    def set_drive(self,v):self.drive=v;self.render()
    def mapping(self,d):return self.c['maps'].get(self.drive,{}).get(d,[[i,'STW1' if d=='TX' and i==1 else 'ZSW1' if d=='RX' and i==1 else '', 'FREE','','',''] for i in range(1,33)])
    def edit_mapping(self,d,r,c):
        self.require('configure')
        if c==0:return
        rows=copy.deepcopy(self.mapping(d));v=text_dialog(self,'PZD mapping','Value',rows[r][c]);
        if v is not None:rows[r][c]=v;self.c['maps'].setdefault(self.drive,{})[d]=rows;self.save();self.render()
    def import_mapping(self,d):
        self.require('configure');p,_=QFileDialog.getOpenFileName(self,'Import mapping','','CSV (*.csv)')
        if p:
            rows=read_csv(p);result=[[int(x['Word'])]+[x[k] for k in ('Signal','Class','Description','Parameter','Scale')] for x in rows];
            if sorted(r[0] for r in result)!=list(range(1,33)):raise ValueError('Require 32 distinct words')
            self.c['maps'].setdefault(self.drive,{})[d]=sorted(result);self.save();self.render()
    def edit_ref(self,k,v):
        self.require('configure');n=text_dialog(self,'Reference',k,v)
        if n is not None:
            n=float(n)
            if not math.isfinite(n) or n<=0:raise ValueError('Positive finite reference required')
            self.c['refs'].setdefault(self.drive,{'refSpeed':3000,'refTorque':100,'refCurrent':20,'positionScale':1000})[k]=n;self.save();self.render()
    def io_page(self):
        filters=QWidget();l=QHBoxLayout(filters);t=QComboBox();t.addItems(['ALL',*TYPES]);t.setCurrentText(self.io_type);s=QComboBox();s.addItems(['ALL','OK','WARN','FAULT','OFFLINE','UNKNOWN']);s.setCurrentText(self.io_state);q=QLineEdit(self.query);q.setPlaceholderText('Search signal / channel / PLC tag');l.addWidget(t);l.addWidget(s);l.addWidget(q);l.addWidget(self.button('Export CSV',self.export_io,'export'));l.addWidget(self.button('Import CSV',self.import_io,'configure'));l.addWidget(self.button('Reset names',self.reset_names,'configure'));self.add(filters);self.io_table=self.add(table(['Channel','Type','Signal name','PLC tag','Value','Raw','Quality','State','Module'],[]));self.io_table.cellDoubleClicked.connect(lambda r,c:self.safe(lambda:self.inspect_io(r,c)));self.inspector=self.add(QLabel('Select a channel to inspect'));self.inspector.setWordWrap(True);self.inspector.setTextFormat(Qt.TextFormat.PlainText);t.currentTextChanged.connect(lambda v:self.filter_io('io_type',v));s.currentTextChanged.connect(lambda v:self.filter_io('io_state',v));q.textChanged.connect(lambda v:self.filter_io('query',v));self.update_live()
    def filter_io(self,k,v):setattr(self,k,v);self.update_live()
    def io_rows(self,filtered=True):
        rows=[]
        for i,t,m in channels(self.c):
            n=self.c['names'].get(i,{});x=self.get('io',i);row=[i,t,n.get('name',i),n.get('tag',''),x.get('value'),x.get('raw'),x.get('quality','UNKNOWN'),x.get('status','UNKNOWN'),m]
            if not filtered or ((self.io_type=='ALL' or t==self.io_type) and (self.io_state=='ALL' or row[7]==self.io_state) and self.query.lower() in ' '.join(str(v) for v in row[:4]).lower()):rows.append(row)
        return rows
    def fill(self,t,rows):
        selected=t.currentRow();t.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                value='—' if v is None else str(v);item=t.item(r,c)
                if item is None:t.setItem(r,c,QTableWidgetItem(value))
                elif item.text()!=value:item.setText(value)
        if 0<=selected<len(rows):t.selectRow(selected)
    def update_live(self):
        if self.page==1 and self.drive:
            x=self.get('drives',self.drive);self.fill(self.signal_table,[[k,x.get(k),('RPM' if 'speed' in k else 'A' if 'current' in k else '% ref' if 'torque' in k else 'mm'),x.get(k+'_raw'),x.get(k+'_pzd')] for k in SIGNALS]);
            for k,labels,t in [('cw',CW,self.cw_table),('sw',SW,self.sw_table)]:
                word=x.get(k);self.fill(t,[[i,labels[i] if i<len(labels) else 'Reserved / profile',None if word is None else (word>>i)&1] for i in range(16)])
        if self.page==3:self.fill(self.io_table,self.io_rows())
    def inspect_io(self,r,c):
        i=self.io_table.item(r,0).text();x=self.get('io',i);self.inspector.setText(i+' | '+json.dumps(x,ensure_ascii=False)+'\nCheck configured channel scaling, hardware diagnostics and expected-state rules.');
        if c in (2,3):
            self.require('configure');k='name' if c==2 else 'tag';v=text_dialog(self,'Channel mapping',k,self.io_table.item(r,c).text());
            if v is not None:self.c['names'].setdefault(i,{})[k]=v;self.save();self.update_live()
    def export(self,h,r):
        self.require('export');p,_=QFileDialog.getSaveFileName(self,'Export CSV','','CSV (*.csv)')
        if p:export_csv(p,h,r)
    def export_io(self):self.export(['ChannelID','Type','SignalName','PLCTag','Value','Raw','Quality','Status','Module'],self.io_rows(False))
    def import_io(self):
        self.require('configure');p,_=QFileDialog.getOpenFileName(self,'Import I/O','','CSV (*.csv)')
        if p:
            valid={i for i,t,m in channels(self.c)};new=copy.deepcopy(self.c['names'])
            for r in read_csv(p):
                if r['ChannelID'] not in valid:raise ValueError('Unknown channel')
                new[r['ChannelID']]={'name':r['SignalName'],'tag':r.get('PLCTag','')}
            self.c['names']=new;self.save();self.update_live()
    def reset_names(self):
        self.require('configure')
        if QMessageBox.question(self,'Reset','Reset all channel names?')==QMessageBox.StandardButton.Yes:self.c['names']={};self.save();self.update_live()
    def config_page(self):
        self.add(QLabel('Controller, drive inventory, I/O rack and mappings — local metadata only. Edit JSON or use the inventory controls.'));self.editor=self.add(QPlainTextEdit(json.dumps(self.c,indent=2)));self.add(self.button('Add drive',self.add_drive,'configure'));self.add(self.button('Add I/O module',self.add_module,'configure'));self.add(self.button('Remove equipment',self.remove_equipment,'configure'));self.add(self.button('Validate & save configuration',self.apply_config,'configure'));self.add(self.button('Import configuration JSON',self.import_config,'configure'));self.add(self.button('Export configuration JSON',self.export_config,'export'));self.add(self.button('Restore default configuration',self.reset_config,'configure'))
    def add_drive(self):
        self.require('configure');c=json.loads(self.editor.toPlainText());i=text_dialog(self,'Add drive','Unique ID');model=text_dialog(self,'Add drive','Model','SINAMICS G120')
        if i and model:c['drives'].append(dict(id=i,model=model,bus='PROFINET',address='',telegram='Unconfirmed',pzd=32,servo='S120' in model));self.editor.setPlainText(json.dumps(c,indent=2));self.apply_config()
    def add_module(self):
        self.require('configure');c=json.loads(self.editor.toPlainText());i=text_dialog(self,'Add module','Unique ID');t,ok=QInputDialog.getItem(self,'I/O module','Type',list(TYPES),0,False);n,ok2=QInputDialog.getInt(self,'Capacity','Channels',16,1,512)
        if i and ok and ok2:c['modules'].append(dict(id=i,type=t,name=t+' module',slot='',capacity=n,orderNo=''));self.editor.setPlainText(json.dumps(c,indent=2));self.apply_config()
    def remove_equipment(self):
        self.require('configure');c=json.loads(self.editor.toPlainText());i,ok=QInputDialog.getItem(self,'Remove equipment','ID',[d['id'] for d in c['drives']]+[m['id'] for m in c['modules'] if m['type']!='CPU'],0,False)
        if ok and i and QMessageBox.question(self,'Confirm','Remove '+i+'?')==QMessageBox.StandardButton.Yes:
            c['drives']=[d for d in c['drives'] if d['id']!=i];c['modules']=[m for m in c['modules'] if m['id']!=i];c['maps'].pop(i,None);c['refs'].pop(i,None);self.editor.setPlainText(json.dumps(c,indent=2));self.apply_config()
    def apply_config(self):
        self.require('configure');new=validate_config(json.loads(self.editor.toPlainText()));old=self.c;self.c=new
        try:self.save()
        except Exception:self.c=old;raise
        self.render()
    def import_config(self):
        self.require('configure');p,_=QFileDialog.getOpenFileName(self,'Import JSON','','JSON (*.json)')
        if p:
            if Path(p).stat().st_size>MAX_FRAME:raise ValueError('File too large')
            self.editor.setPlainText(Path(p).read_text(encoding='utf-8'));self.apply_config()
    def export_config(self):
        self.require('export');p,_=QFileDialog.getSaveFileName(self,'Export JSON','','JSON (*.json)')
        if p:Path(p).write_text(json.dumps(self.c,indent=2),encoding='utf-8')
    def reset_config(self):
        self.require('configure')
        if QMessageBox.question(self,'Reset','Restore default inventory and mappings?')==QMessageBox.StandardButton.Yes:self.editor.setPlainText(json.dumps(defaults()));self.apply_config()
    def users(self):
        self.require('users')
        if self.demo:raise ValueError('Demo cannot administer accounts')
        dlg=QDialog(self);dlg.setWindowTitle('User administration');l=QVBoxLayout(dlg);t=table(['Username','Role','Active'],self.store.users());l.addWidget(t)
        def add():
            n=text_dialog(dlg,'New account','Username');p=text_dialog(dlg,'New account','Password',password=True);r,ok=QInputDialog.getItem(dlg,'Role','Role',ROLES,1,False)
            if n and p and ok:self.store.create(n,p,r);dlg.accept()
        def edit():
            row=t.currentRow()
            if row<0:return
            n=t.item(row,0).text()
            if n.lower()==self.user.lower():raise ValueError('Cannot change own role or disable self')
            r,ok=QInputDialog.getItem(dlg,'Role','Role',ROLES,0,False)
            if ok:self.store.user_update(n,r,QMessageBox.question(dlg,'Account','Enable account?')==QMessageBox.StandardButton.Yes);dlg.accept()
        l.addWidget(self.button('Create user',add,'users'));l.addWidget(self.button('Change role / active state',edit,'users'));dlg.resize(650,400);dlg.exec()
    def password(self):
        if self.demo:raise ValueError('Demo has no account')
        old=text_dialog(self,'Password','Current password',password=True);new=text_dialog(self,'Password','New password',password=True)
        if old is not None and new is not None:self.store.password(self.user,old,new)
    def closeEvent(self,e):self.receiver.stop_event.set();super().closeEvent(e)
class Activity(QApplication):
    def notify(self,obj,event):
        if event.type() in (QEvent.Type.KeyPress,QEvent.Type.MouseButtonPress) and hasattr(self,'window'):self.window.activity=time.monotonic()
        return super().notify(obj,event)
if __name__=='__main__':
    app=Activity(sys.argv);app.setStyleSheet(STYLE);path=Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'SystemWindow';path.mkdir(exist_ok=True);app.window=Window(Store(path/'system.db'));app.window.showMaximized();sys.exit(app.exec())
