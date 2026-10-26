const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const ReaderMarks = vm.runInNewContext(readFileSync('src/second_brain/web/highlights.js', 'utf8') + '\nReaderMarks;');
const plain = value => JSON.parse(JSON.stringify(value));

test('DOM UTF-16 offsets map to server code points, including multiline code', () => {
  const text = '😀 A\necho 🧠\nend';
  const start = text.indexOf('echo');
  assert.deepEqual(plain(ReaderMarks.offsets(text, start, start + 'echo 🧠'.length)), {start: 4, end: 10, quote: 'echo 🧠'});
  assert.equal(ReaderMarks.offsets(text, 0, 2).quote, '😀');
  for (const [a,b] of [[0,1], [1,2], [-1,2], [3,3], [0,99], [.5,2]]) assert.throws(() => ReaderMarks.offsets(text,a,b));
  assert.throws(() => ReaderMarks.offsets('   ',0,3));
  assert.throws(() => ReaderMarks.offsets('a'.repeat(4001),0,4001));
});

test('overlap splits preserve exact source and all marks with latest color precedence', () => {
  const text = '😀 command\ncode';
  const items = [
    {id:'a', created_at:'1', quote:'😀 command', color:'yellow', anchor:{status:'resolved',start:0,end:9}},
    {id:'b', created_at:'2', quote:'command\ncode', color:'blue', anchor:{status:'resolved',start:2,end:14}},
    {id:'c', created_at:'3', quote:'bad', anchor:{status:'unresolved',start:null,end:null}},
    {id:'d', created_at:'4', quote:'mismatch', anchor:{status:'resolved',start:0,end:1}}
  ];
  const before = JSON.stringify(items);
  const segments = plain(ReaderMarks.segments(items,text));
  assert.equal(segments.map(s=>text.slice(s.start,s.end)).join(''),text);
  const overlap = segments.find(s=>s.items.length===2);
  assert.equal(text.slice(overlap.start,overlap.end),'command');
  assert.equal(overlap.items.at(-1).color,'blue');
  assert.equal(JSON.stringify(items),before);
  assert.deepEqual(plain(ReaderMarks.segments([], '')), []);
  const tied = items.slice(0,2).map((item,i)=>({...item,id:i ? 'a' : 'z',created_at:'2026-10-16T12:00:00Z'}));
  assert.equal(plain(ReaderMarks.segments(tied,text)).find(s=>s.items.length===2).items.at(-1).color,'blue');
});


test('fragment navigation refuses stale anchors and keeps unresolved marks repairable', () => {
  let message = '', focused = false, scrolled = false;
  const saved = {open:false};
  const row = {dataset:{markId:'a'}, querySelector:()=>({focus:()=>{focused=true;}}), scrollIntoView:()=>{scrolled=true;}};
  const Marks = vm.runInNewContext(readFileSync('src/second_brain/web/highlights.js','utf8')+'\nReaderMarks;', {
    $:()=>({children:[row]}), document:{querySelector:()=>saved}
  });
  const reader = {items:[{id:'a',anchor:{status:'resolved',revision:'new'}}],doc:{revision:'old'},message:text=>{message=text;}};
  Marks.prototype.focusMark.call(reader,'a');
  assert.match(message,/cambiado/);
  assert.equal(focused,false);
  reader.items[0].anchor={status:'unresolved',revision:'old'};
  Marks.prototype.focusMark.call(reader,'a');
  assert.match(message,/reparación/);
  assert.ok(focused && scrolled && saved.open);
  Marks.prototype.focusMark.call(reader,'gone');
  assert.match(message,/no está disponible/);
});

test('fragment navigation selects exact code-point range across DOM nodes and overlapping marks', () => {
  const text='😀 before command\nend';
  const parent={focus:()=>{},scrollIntoView:()=>{}};
  const nodes=['😀 before ','com','mand\nend'].map(data=>({data,length:data.length,parentElement:parent}));
  let i=-1, starts, ends, selected;
  const range={setStart:(node,offset)=>{starts=[nodes.indexOf(node),offset];range.startContainer=node;},setEnd:(node,offset)=>{ends=[nodes.indexOf(node),offset];}};
  const walker={nextNode:()=>++i<nodes.length,get currentNode(){return nodes[i];}};
  const Marks = vm.runInNewContext(readFileSync('src/second_brain/web/highlights.js','utf8')+'\nReaderMarks;', {
    $:()=>({children:[]}), NodeFilter:{SHOW_TEXT:4},
    document:{querySelector:()=>({}),createTreeWalker:()=>walker,createRange:()=>range},
    getSelection:()=>({removeAllRanges:()=>{},addRange:r=>{selected=r;}})
  });
  const reader={items:[{id:'a',anchor:{status:'resolved',revision:'same',start:9,end:20}}],doc:{revision:'same',text},message:()=>{}};
  Marks.prototype.focusMark.call(reader,'a');
  assert.deepEqual(starts,[1,0]);
  assert.deepEqual(ends,[2,8]);
  assert.equal(selected,range);
});
