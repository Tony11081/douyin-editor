// 知识讲解·纪录片式 公用逻辑（先引 ../cinema/core.js）
// 每个变体定义 window.TL = {dur, cuts:[换素材的秒数], subs:[...]}、window.IDS（所有分段元素 id）和 window.SEG(t)。
const vis=(t,a,b)=>t>=a&&t<b;
function hideAll(){(window.IDS||[]).forEach(i=>{const e=$(i);if(e)e.style.visibility='hidden';});}
function show(...ids){ids.forEach(i=>{const e=$(i);if(e)e.style.visibility='visible';});}
function fadeAway(ids,lt,at,d=.45){const k=E.io(P(lt,at,d));if(k<=0)return 0;ids.forEach(i=>{const e=$(i);e.style.opacity=(parseFloat(e.style.opacity)||1)*(1-k);});return k;}
// 钩子：字从镜头前砸进来，最后朝镜头飞出去
function hook(a,b,t,t0,t1){if(!vis(t,t0,t1))return;show(a,b);const lt=t-t0;chars(a,lt,.25,.05,.55,0,18);chars(b,lt,.75,.06,.6,0,22);
  document.querySelectorAll('#'+a+' .c,#'+b+' .c').forEach((c,i)=>{const k=P(lt,.25+i*.055,.5);c.style.transform=`scale(${L(1.9,1,E.oq(k))})`;});
  const ko=E.io(P(lt,(t1-t0)-.6,.6));[a,b].forEach((i,j)=>T(i,{s:L(1,2.4,ko),y:L(0,j?260:-200,ko),op:1-ko,bl:L(0,30,ko)}));}
function drawPath(id,k){const p=$(id);const len=p.getTotalLength();p.style.strokeDasharray=len;p.style.strokeDashoffset=len*(1-k);}
function kitBoot(){document.querySelectorAll('[data-ep]').forEach(e=>{e.textContent=EP[e.dataset.ep];});document.querySelectorAll('[data-split]').forEach(splitChars);
  buildSubs();window.DUR=TL.dur;window.render=kitFrame;kitFrame(0);}
function kitFrame(t){const w=$('world');w.style.transform=`translate(${6*Math.sin(t*.7)}px,${5*Math.cos(t*.53)}px) scale(${1+.012*Math.sin(t*.4)})`;
  $('dot').style.opacity=.35+.65*Math.abs(Math.sin(t*3));fadeIn('tag',t,.1,.6,0,6);fadeIn('brand',t,.2,.6,0,6);
  hideAll();SEG(t);
  let f=0;(TL.cuts||[]).forEach(c=>{f=Math.max(f,1-Math.abs(t-c)/.28);});$('flash').style.opacity=f*.95;
  const c=CH.find(c=>t>=c[0]&&t<c[1]);const sp=$('subt');sp.textContent=c?c[2]:'';
  if(c){const k=P(t,c[0],.2);sp.style.opacity=E.oc(k);const ww=sp.scrollWidth;sp.style.transform=`scale(${Math.min(1,960/ww)})`;}}
