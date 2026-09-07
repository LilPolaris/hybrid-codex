import {test,expect} from 'bun:test';
import {mkdtempSync,rmSync,readFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {QueueBridge} from '../scripts/queue-bridge';
import {Client} from '../vendor/cursor-chatgpt-web/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import {StdioClientTransport} from '../vendor/cursor-chatgpt-web/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';

function fixture(){
  const dir=mkdtempSync(join(tmpdir(),'hybrid-queue-'));
  const q=new QueueBridge(dir,'full');
  const job={id:'t1',session:'s1',title:'task',prompt:'write and test hello',cwd:dir,baseline:[800,1500]};
  q.enqueue(job);
  return {q,dir,job,clean:()=>{q.db.close();rmSync(dir,{recursive:true,force:true});}};
}

test('persistent queue, unique claim and duplicate enqueue conflict',()=>{
  const f=fixture();try{
    expect(f.q.enqueue(f.job).status).toBe('queued');
    expect(()=>f.q.enqueue({...f.job,prompt:'different'})).toThrow('conflict');
    const t=f.q.claim({session:'s1',worker:'a'}).task;
    const other=new QueueBridge(f.dir,'full');try{
      expect(other.claim({session:'s1',worker:'b'}).task).toBeNull();
      expect(()=>other.read({id:'t1',lease:'wrong',path:'x'})).toThrow();
      expect(other.heartbeat({id:'t1',lease:t.lease}).status).toBe('claimed');
    }finally{other.db.close();}
  }finally{f.clean();}
});

test('read/write optimistic conflict, operation dedup, parent-only acceptance',()=>{
  const f=fixture();try{
    const t=f.q.claim({session:'s1',worker:'a'}).task;
    const a={id:t.id,lease:t.lease,path:'hello.txt',text:'hello',operation:'w1',expected_sha256:null};
    const r=f.q.write(a);expect(r.sha256).toBeDefined();expect(f.q.write(a)).toEqual(r);
    expect(f.q.read(a).text).toBe('hello');
    expect(f.q.write({...a,operation:'w2',text:'changed'}).error).toContain('changed');
    expect(readFileSync(join(f.dir,'hello.txt'),'utf8')).toBe('hello');
    expect(f.q.submit({...a,result:'file created'}).status).toBe('submitted');
    expect(f.q.submit({...a,result:'file created'}).status).toBe('submitted');
    expect(()=>f.q.write({...a,operation:'late'})).toThrow();
    const accepted=f.q.review({id:t.id,accepted:true,overhead:[300,600]});
    expect(accepted.net_parent_tokens_estimate).toEqual([200,1200]);
    expect(f.q.review({id:t.id,accepted:false,overhead:[300,600]}).net_parent_tokens_estimate).toEqual([-600,-300]);
  }finally{f.clean();}
});

test('cooldown blocks only session; queued cancellation and claimed cancellation',()=>{
  const f=fixture();try{
    f.q.fault({session:'s1',reason:'quota'});
    expect(f.q.claim({session:'s1',worker:'a'}).cooldown.reason).toBe('quota');
    f.q.enqueue({...f.job,id:'t2',session:'s2'});
    const t=f.q.claim({session:'s2',worker:'b'}).task;
    expect(f.q.cancel({id:t.id}).status).toBe('cancel_requested');
    expect(()=>f.q.read({id:t.id,lease:t.lease,path:'hello'})).toThrow();
    expect(f.q.acknowledgeCancel({id:t.id,lease:t.lease}).status).toBe('cancelled');
    expect(f.q.cancel({id:'t1'}).status).toBe('cancelled');
  }finally{f.clean();}
});

test('real command, dedup and read-only denial',async()=>{
  const f=fixture();try{
    const t=f.q.claim({session:'s1',worker:'a'}).task;
    const a={id:t.id,lease:t.lease,operation:'e1',command:process.platform==='win32'?"Write-Output 'hello-mcp'":"printf hello-mcp"};
    const result:any=await f.q.exec(a);expect(result.exit_code).toBe(0);expect(result.output).toContain('hello-mcp');
    expect(await f.q.exec(a)).toEqual(result);
    const readOnly=new QueueBridge(f.dir);try{expect(()=>readOnly.write({...a,path:'x',text:'x',expected_sha256:null})).toThrow('full');}finally{readOnly.db.close();}
  }finally{f.clean();}
});

test('real timeout cannot silently release command or retry it',async()=>{
  const f=fixture();try{
    const t=f.q.claim({session:'s1',worker:'a'}).task;
    const a={id:t.id,lease:t.lease,operation:'slow',command:process.platform==='win32'?'Start-Sleep -Seconds 8':'sleep 8',timeout_ms:200};
    const r:any=await f.q.exec(a);expect(r.stopped).toBe(true);
    expect(()=>f.q.submit({...a,result:'done'})).toThrow('pending');
    await expect(f.q.exec(a)).rejects.toThrow('uncertain');
    f.q.resolveOperation({...a,terminal_confirmed:true,note:'Controlled test child closed; no side effects'});
    expect(f.q.submit({...a,result:'timeout verified'}).status).toBe('submitted');
  }finally{f.clean();}
});

test('standard MCP stdio end-to-end with real filesystem and shell',async()=>{
  const f=fixture();const client=new Client({name:'acceptance',version:'1'});
  const transport=new StdioClientTransport({command:process.execPath,args:[resolve('scripts/queue-bridge.ts'),'mcp','--data',f.dir,'--access','full'],stderr:'pipe'});
  try{
    await client.connect(transport);
    const catalog=await client.listTools();const names=catalog.tools.map(t=>t.name);
    expect(names).toContain('execute_command');expect(names).not.toContain('review');
    expect(catalog.tools.find(t=>t.name==='write_file')?.annotations?.readOnlyHint).toBe(false);
    const call=async(name:string,args:any)=>{
      const r=await client.callTool({name,arguments:args});if(r.isError)throw new Error(JSON.stringify(r));
      return JSON.parse((r.content as any)[0].text);
    };
    const {task:t}=await call('claim_task',{session:'s1',worker:'standard-mcp-test'});
    const base={id:t.id,lease:t.lease};
    await call('write_file',{...base,operation:'write',path:'accepted.txt',text:'mcp-ok',expected_sha256:null});
    expect((await call('read_path',{...base,path:'accepted.txt'})).text).toBe('mcp-ok');
    const r=await call('execute_command',{...base,operation:'exec',command:process.platform==='win32'?"Get-Content -LiteralPath accepted.txt":"cat accepted.txt"});
    expect(r.output).toContain('mcp-ok');expect(r.exit_code).toBe(0);
    await call('submit_result',{...base,result:'accepted.txt created; shell readback mcp-ok'});
    expect(f.q.status({id:t.id}).status).toBe('submitted');
    expect(f.q.review({id:t.id,accepted:true,overhead:[200,500]}).net_parent_tokens_estimate).toEqual([300,1300]);
  }finally{await client.close();f.clean();}
},20000);

test('Parent can resolve stranded task only after confirmation; old lease stays revoked',()=>{
  const f=fixture();try{
    const t=f.q.claim({session:'s1',worker:'a'}).task;
    expect(()=>f.q.resolveTask({id:t.id,note:'checked'})).toThrow('Confirm');
    expect(f.q.resolveTask({id:t.id,terminal_confirmed:true,note:'test worker was not dispatched'}).status).toBe('cancelled');
    expect(()=>f.q.submit({id:t.id,lease:t.lease,result:'late'})).toThrow();
    expect(f.q.status({id:t.id}).prompt).toBeUndefined();
    expect(f.q.status({id:t.id}).lease).toBeUndefined();
  }finally{f.clean();}
});
