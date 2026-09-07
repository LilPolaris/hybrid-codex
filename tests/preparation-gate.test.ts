import {expect,test} from 'bun:test';
import {LauncherBrowserHelperClient} from '../vendor/cursor-chatgpt-web/src/adapters/chatgpt-web/launcher-helper-client';

test('UI preparation is serialized but generations overlap after submission',async()=>{
  const client:any=new LauncherBrowserHelperClient({} as any);
  const started:string[]=[];
  const finishes=new Map<string,()=>void>();
  client.runPrepared=async(turn:any)=>{
    started.push(turn.traceId);
    await new Promise<void>(resolve=>finishes.set(turn.traceId,resolve));
    return turn.traceId;
  };
  const first=client.run({traceId:'a'});
  const second=client.run({traceId:'b'});
  await Bun.sleep(5);
  expect(started).toEqual(['a']);
  client.preparationReleases.get('a')(); // helper's submitted event
  await Bun.sleep(5);
  expect(started).toEqual(['a','b']);
  expect(finishes.has('a')).toBe(true); // a's generation has not finished
  finishes.get('b')!(); finishes.get('a')!();
  expect(await Promise.all([first,second])).toEqual(['a','b']);
});
