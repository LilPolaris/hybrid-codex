/** Official MCP transport only: no browser automation, cookies or model calls.
 * Parent CLI: bun queue-bridge.ts <enqueue|status|cancel|review> --data DIR
 * ChatGPT connector: bun queue-bridge.ts mcp --data DIR --access full
 * JSON arguments on stdin for CLI operations. Keep data outside the repository.
 */
import { Database } from 'bun:sqlite';
import { randomUUID, createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, readdirSync, existsSync, statSync, renameSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { spawn, spawnSync } from 'node:child_process';

const hash = (s: string) => createHash('sha256').update(s).digest('hex');
const error = (s: string): never => { throw new Error(s); };
const range = (a: any) => {
  if (a == null) return null;
  if (!Array.isArray(a) || a.length !== 2 || a.some(x => typeof x !== 'number' || !Number.isFinite(x) || x < 0) || a[0] > a[1]) error('Invalid token range');
  return a;
};
const required = (s: any) => typeof s === 'string' && s.trim() ? s : error('Nonempty string required');

export class QueueBridge {
  db: Database;
  constructor(public data: string, public access = 'read-only') {
    mkdirSync(data, { recursive: true });
    this.db = new Database(join(data, 'queue.sqlite'), { create: true });
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=10000;
      CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, session TEXT, title TEXT,
        prompt TEXT, cwd TEXT, status TEXT, lease TEXT, worker TEXT, created INTEGER,
        updated INTEGER, result TEXT, baseline TEXT, overhead TEXT, fault TEXT);
      CREATE TABLE IF NOT EXISTS operations(job TEXT, id TEXT, kind TEXT, request TEXT,
        status TEXT, result TEXT, PRIMARY KEY(job,id));
      CREATE TABLE IF NOT EXISTS cooldowns(session TEXT PRIMARY KEY, until INTEGER, reason TEXT);
    `);
  }
  get(id: string): any { return this.db.query('SELECT * FROM jobs WHERE id=?').get(required(id)) ?? error('Unknown task'); }
  enqueue(a: any) {
    const id = required(a.id), session = required(a.session), title = required(a.title);
    const prompt = required(a.prompt), cwd = resolve(required(a.cwd));
    if (!statSync(cwd).isDirectory()) error('cwd is not a directory');
    const baseline = JSON.stringify(range(a.baseline));
    const old: any = this.db.query('SELECT * FROM jobs WHERE id=?').get(id);
    if (old) {
      if (old.session !== session || old.prompt !== prompt || old.cwd !== cwd || old.baseline !== baseline || old.title !== title) error('Task ID conflict');
      return this.publicJob(old);
    }
    const now = Date.now();
    this.db.query('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run(
      id,session,title,prompt,cwd,'queued',null,null,now,now,null,baseline,'null',null);
    return this.publicJob(this.get(id));
  }
  publicJob(j: any) {
    const { lease, prompt, ...rest } = j;
    const cool: any = this.db.query('SELECT * FROM cooldowns WHERE session=? AND until>?').get(j.session,Date.now());
    const costs = JSON.parse(j.overhead), base = JSON.parse(j.baseline);
    const benefit = j.status === 'accepted' ? base : j.status === 'rejected' ? [0,0] : null;
    const estimate = benefit && costs ? [benefit[0]-costs[1],benefit[1]-costs[0]] : null;
    return {...rest, cooldown: cool ?? null, net_parent_tokens_estimate: estimate,
      card: `${j.title} | ChatGPT MCP | ${j.status} | ${Math.round((j.updated-j.created)/1000)}s（含排队） | 主模型净节省估算 ${estimate ? estimate.join('…') : '未知'} tokens（非账单）`};
  }
  status(a: any) {
    if (a.id) return this.publicJob(this.get(a.id));
    return (this.db.query('SELECT * FROM jobs WHERE session=? ORDER BY created').all(required(a.session)) as any[]).map(j=>this.publicJob(j));
  }
  claim(a: any) {
    return this.db.transaction(() => {
      const session = required(a.session), worker = required(a.worker);
      const cool: any = this.db.query('SELECT * FROM cooldowns WHERE session=? AND until>?').get(session,Date.now());
      if (cool) return {task:null,cooldown:cool};
      // One mutating worker per session; no expiry-based reassignment of live work.
      if (this.db.query("SELECT 1 FROM jobs WHERE session=? AND status IN ('claimed','cancel_requested')").get(session)) return {task:null,reason:'active lease; finish or cancel it first'};
      const j: any = this.db.query("SELECT * FROM jobs WHERE session=? AND status='queued' ORDER BY created,id LIMIT 1").get(session);
      if (!j) return {task:null,reason:'queue empty; stop, do not poll indefinitely'};
      const lease=randomUUID();
      this.db.query("UPDATE jobs SET status='claimed',lease=?,worker=?,updated=? WHERE id=?").run(lease,worker,Date.now(),j.id);
      return {task:{...this.publicJob(this.get(j.id)),prompt:j.prompt,lease}, access:this.access};
    }).immediate();
  }
  authorized(a: any, cancelOK=false) {
    const j=this.get(a.id);
    if (!a.lease || j.lease !== a.lease || !(j.status==='claimed' || cancelOK && j.status==='cancel_requested')) error('Invalid, revoked or completed lease');
    return j;
  }
  heartbeat(a: any) {
    const j=this.authorized(a,true);
    this.db.query('UPDATE jobs SET updated=? WHERE id=?').run(Date.now(),j.id);
    return {status:j.status,cancel_requested:j.status==='cancel_requested'};
  }
  submit(a: any) {
    const j=this.get(a.id), text=required(a.result);
    if (j.status==='submitted' && j.lease===a.lease && j.result===text) return this.publicJob(j);
    this.authorized(a);
    if (this.db.query("SELECT 1 FROM operations WHERE job=? AND status IN ('running','uncertain')").get(j.id)) error('Resolve pending operations before submitting');
    this.db.query("UPDATE jobs SET status='submitted',result=?,updated=? WHERE id=?").run(text,Date.now(),j.id);
    return this.publicJob(this.get(j.id));
  }
  cancel(a: any) {
    const j=this.get(a.id);
    if (j.status==='queued') this.db.query("UPDATE jobs SET status='cancelled',updated=? WHERE id=?").run(Date.now(),j.id);
    else if (j.status==='claimed') this.db.query("UPDATE jobs SET status='cancel_requested',updated=? WHERE id=?").run(Date.now(),j.id);
    return this.publicJob(this.get(j.id));
  }
  acknowledgeCancel(a: any) {
    this.authorized(a,true);
    if (this.db.query("SELECT 1 FROM operations WHERE job=? AND status IN ('running','uncertain')").get(a.id)) error('A command is running or unresolved');
    this.db.query("UPDATE jobs SET status='cancelled',lease=NULL,updated=? WHERE id=?").run(Date.now(),a.id);
    return this.publicJob(this.get(a.id));
  }
  review(a: any) {
    const j=this.get(a.id);
    if (!['submitted','accepted','rejected'].includes(j.status)) error('Only submitted results can be reviewed');
    if (typeof a.accepted !== 'boolean') error('accepted must be boolean');
    this.db.query('UPDATE jobs SET status=?,overhead=?,updated=? WHERE id=?').run(
      a.accepted?'accepted':'rejected',JSON.stringify(range(a.overhead)),Date.now(),a.id);
    return this.publicJob(this.get(a.id));
  }
  fault(a: any) {
    const seconds: any = {auth:1800,quota:3600,unavailable:600,transient:60};
    if (!seconds[a.reason]) error('Unknown fault type');
    this.db.query(`INSERT INTO cooldowns VALUES(?,?,?) ON CONFLICT(session) DO UPDATE SET
      until=MAX(until,excluded.until),reason=excluded.reason`).run(required(a.session),Date.now()+seconds[a.reason]*1000,a.reason);
    return {reason:a.reason,seconds:seconds[a.reason]};
  }
  read(a: any) {
    const j=this.authorized(a), path=resolve(j.cwd,required(a.path));
    const f=statSync(path);
    if (f.isDirectory()) return {path,entries:readdirSync(path).slice(0,1000)};
    if (f.size>1024*1024) error('File exceeds 1 MiB; use a focused shell read');
    const text=readFileSync(path,'utf8'); return {path,text,sha256:hash(text)};
  }
  beginOperation(a: any, kind: string, request: string): any {
    if (this.access!=='full') error('Local writes and commands require --access full');
    this.authorized(a);
    return this.db.transaction(()=> {
      const old:any=this.db.query('SELECT * FROM operations WHERE job=? AND id=?').get(a.id,required(a.operation));
      if (old) {
        if (old.kind!==kind || old.request!==request) error('Operation ID conflict');
        if (old.status!=='done') error('Operation running/uncertain: inspect before retrying');
        return JSON.parse(old.result);
      }
      if (this.db.query("SELECT 1 FROM operations WHERE job=? AND status IN ('running','uncertain')").get(a.id)) error('Another operation is unresolved');
      this.db.query('INSERT INTO operations VALUES(?,?,?,?,?,?)').run(a.id,a.operation,kind,request,'running',null);
      return null;
    }).immediate();
  }
  finishOperation(a: any, result: any, state='done') {
    this.db.query('UPDATE operations SET status=?,result=? WHERE job=? AND id=?').run(state,JSON.stringify(result),a.id,a.operation);
    return result;
  }
  write(a: any) {
    const j=this.authorized(a), path=resolve(j.cwd,required(a.path));
    const text=typeof a.text==='string'?a.text:error('text required');
    if (Buffer.byteLength(text)>1024*1024) error('Write exceeds 1 MiB');
    const request=JSON.stringify({path,text,expected:a.expected_sha256});
    const old=this.beginOperation(a,'write',request); if(old) return old;
    try {
      const current=existsSync(path)?hash(readFileSync(path,'utf8')):null;
      if(a.expected_sha256!==current) error('File changed; read again before writing (null means create only)');
      mkdirSync(dirname(path),{recursive:true});
      const tmp=path+'.hybrid-'+randomUUID(); writeFileSync(tmp,text,'utf8'); renameSync(tmp,path);
      return this.finishOperation(a,{path,sha256:hash(text)});
    } catch(e) {return this.finishOperation(a,{error:String(e)});}
  }
  async exec(a: any) {
    const j=this.authorized(a), command=required(a.command);
    const timeout=a.timeout_ms ?? 30000;
    if(!Number.isInteger(timeout)||timeout<100||timeout>60000) error('timeout_ms must be 100..60000');
    const old=this.beginOperation(a,'exec',JSON.stringify({command,timeout})); if(old) return old;
    const started=Date.now();
    return await new Promise(resolveResult=> {
      const win=process.platform==='win32';
      const p=spawn(win?'powershell.exe':'/bin/sh',win?['-NoProfile','-NonInteractive','-Command',command]:['-c',command],{cwd:j.cwd,windowsHide:true,stdio:['ignore','pipe','pipe']});
      let output='',truncated=false,stopped=false,done=false;
      const add=(b:Buffer)=>{if(output.length<64000)output+=b.toString().slice(0,64000-output.length);else truncated=true;};
      p.stdout.on('data',add);p.stderr.on('data',add);
      const kill=()=>{stopped=true;if(p.pid){if(win)spawnSync('taskkill',['/PID',String(p.pid),'/T','/F'],{windowsHide:true});else p.kill('SIGKILL');}};
      const timer=setTimeout(kill,timeout);
      const cancellation=setInterval(()=>{if(this.get(a.id).status==='cancel_requested'&&!stopped)kill();},200);
      const finish=(value:any,state='done')=>{if(done)return;done=true;clearTimeout(timer);clearInterval(cancellation);resolveResult(this.finishOperation(a,{...value,output,truncated,seconds:(Date.now()-started)/1000},state));};
      p.once('error',e=>finish({error:String(e)}));
      p.once('close',code=>finish({exit_code:code,stopped},stopped?'uncertain':'done'));
    });
  }
  operations(a:any) {return this.db.query('SELECT id,kind,status,result FROM operations WHERE job=?').all(required(a.id));}
  resolveOperation(a:any) {
    if(a.terminal_confirmed!==true)error('Inspect local process state and side effects first');
    const op:any=this.db.query('SELECT * FROM operations WHERE job=? AND id=?').get(a.id,a.operation);
    if(!op)error('Unknown operation');
    if(op.status!=='done')this.finishOperation(a,{previous:op.result,note:required(a.note),parent_confirmed:true});
    return this.operations(a);
  }
  resolveTask(a:any) {
    if(a.terminal_confirmed!==true)error('Confirm the worker stopped and inspect side effects first');
    const j=this.get(a.id);
    if(!['claimed','cancel_requested'].includes(j.status))error('Only stranded active tasks can be resolved');
    if(this.db.query("SELECT 1 FROM operations WHERE job=? AND status IN ('running','uncertain')").get(a.id))error('Resolve pending commands first');
    this.db.query("UPDATE jobs SET status='cancelled',lease=NULL,fault=?,updated=? WHERE id=?").run(required(a.note),Date.now(),a.id);
    return this.publicJob(this.get(a.id));
  }
}

export async function connectMcp(q: QueueBridge, transport:any) {
  const {McpServer}=await import('../vendor/cursor-chatgpt-web/node_modules/@modelcontextprotocol/sdk/dist/esm/server/mcp.js');
  const z=await import('../vendor/cursor-chatgpt-web/node_modules/zod/index.js');
  const server=new McpServer({name:'hybrid-task-queue',version:'1.0.0'}, {instructions:
    'User-started ChatGPT MCP worker. Claim from the supplied session. Use returned lease on every operation. Read/write/execute only for the assigned task. Check cancellation. Submit concise evidence and changed files. Stop when queue empty. Never call browser automation. Full access is OS-user access, not a sandbox. Parent reviews results.'});
  const lease={id:z.string(),lease:z.string()};
  const register=(name:string,description:string,schema:any,fn:(a:any)=>any,readOnly=false)=>server.registerTool(name,{description,inputSchema:schema,annotations:{readOnlyHint:readOnly,destructiveHint:!readOnly,openWorldHint:true}},async a=>{
    try{const r=await fn(a);return {content:[{type:'text' as const,text:JSON.stringify(r)}],isError:!!r?.error};}
    catch(e){return {content:[{type:'text' as const,text:String(e)}],isError:true};}
  });
  register('claim_task','Use to claim the next task from the session supplied by the user.',{session:z.string(),worker:z.string()},a=>q.claim(a));
  register('heartbeat','Check whether Parent requested cancellation.',lease,a=>q.heartbeat(a));
  register('read_path','Read a local UTF-8 file or directory for the claimed task.',{...lease,path:z.string()},a=>q.read(a),true);
  if(q.access==='full'){
    register('write_file','Create/update a file. Supply its previous sha256, or null to create only. Use a unique operation ID.',{...lease,operation:z.string(),path:z.string(),text:z.string(),expected_sha256:z.string().nullable()},a=>q.write(a));
    register('execute_command','Run a local command for this task, with OS-user permissions. Max 60 seconds. Do not launch detached processes. Use a unique operation ID; never repeat an uncertain command.',{...lease,operation:z.string(),command:z.string(),timeout_ms:z.number().int().min(100).max(60000).optional()},a=>q.exec(a));
  }
  register('submit_result','Submit verified observations, changed files and test results. Parent decides acceptance.',{...lease,result:z.string()},a=>q.submit(a));
  register('acknowledge_cancel','Release task only after all operations stopped.',lease,a=>q.acknowledgeCancel(a));
  await server.connect(transport); return server;
}

if(import.meta.main){
  const args=process.argv.slice(2),action=args.shift();
  const option=(key:string)=>{const i=args.indexOf(key);return i<0?undefined:args[i+1];};
  const data=option('--data');if(!data)error('--data private directory required');
  const access=option('--access')??'read-only';if(!['full','read-only'].includes(access))error('Invalid access');
  const q=new QueueBridge(resolve(data!),access);
  if(action==='mcp'){
    const {StdioServerTransport}=await import('../vendor/cursor-chatgpt-web/node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js');
    await connectMcp(q,new StdioServerTransport());
  }else{
    const actions:any={enqueue:'enqueue',status:'status',cancel:'cancel',review:'review',fault:'fault',operations:'operations','resolve-operation':'resolveOperation','resolve-task':'resolveTask',watch:'status'};
    if(!actions[action!])error('Use mcp, enqueue, status, cancel, review, fault, operations, resolve-operation');
    try{
      const a=JSON.parse(await Bun.stdin.text());
      if(action==='watch'){
        const deadline=Date.now()+Math.min(60000,Math.max(0,a.wait_ms??30000));
        let previous='';
        do{
          const result=q.status(a),encoded=JSON.stringify(result);
          if(encoded!==previous){console.log(encoded);previous=encoded;}
          const rows=Array.isArray(result)?result:[result];
          if(rows.length && rows.every((j:any)=>!['queued','claimed','cancel_requested'].includes(j.status)))break;
          if(Date.now()>=deadline)break;
          await Bun.sleep(Math.min(500,deadline-Date.now()));
        }while(true);
      }else console.log(JSON.stringify(await (q as any)[actions[action!]](a),null,2));
    }
    finally{q.db.close();}
  }
}
