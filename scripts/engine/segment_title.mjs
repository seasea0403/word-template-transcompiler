// Read plain text on stdin; never change the original title.
let input='';
for await (const chunk of process.stdin) input+=chunk;
const text=JSON.parse(input).text;
if(typeof text!=='string') throw new Error('Expected title text');
const segmenter=new Intl.Segmenter('zh',{granularity:'word'});
let count=0; const boundaries=[]; const tokens=[];
for(const item of segmenter.segment(text)) {
  tokens.push(item.segment); count+=Array.from(item.segment).length;
  boundaries.push(count);
}
process.stdout.write(JSON.stringify({tokens,boundaries}));
