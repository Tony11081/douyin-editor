import { createRequire } from 'module';import fs from 'fs';import path from 'path';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');
const here=path.dirname(new URL(import.meta.url).pathname);
const [, , mode, a, b, c] = process.argv;
const br=await chromium.launch({executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome',args:['--force-color-profile=srgb','--disable-lcd-text','--font-render-hinting=none']});
const p=await br.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
await p.goto('file://'+here+'/docu_tpl.html');await p.evaluate(()=>document.fonts.ready);
const shot=async(t,f)=>{await p.evaluate(t=>window.render(t),t);await p.screenshot({path:f,omitBackground:true,type:'png'})};
if(mode==='stills'){fs.mkdirSync(here+'/stills',{recursive:true});for(const t of a.split(',').map(Number))await shot(t,`${here}/stills/s_${t.toFixed(2)}.png`)}
else{const shard=+a,shards=+b,total=+c;const d=here+'/frames';fs.mkdirSync(d,{recursive:true});
 for(let i=shard;i<total;i+=shards){const f=`${d}/f${String(i).padStart(5,'0')}.png`;if(!fs.existsSync(f))await shot(i/30,f)}}
await br.close();
