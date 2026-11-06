// 发布会电影感模板公用引擎：时间轴、缓动、逐字显现、打字、素材窗挖洞、字幕、转场
// 页面加 ?hole=1 时进入「挖洞模式」：背景透明，素材窗那块挖空，用来渲染成透明 webm 叠在素材上
const E={oc:x=>1-Math.pow(1-x,3),oq:x=>1-Math.pow(1-x,5),ob:x=>{const c1=1.4,c3=c1+1;return 1+c3*Math.pow(x-1,3)+c1*Math.pow(x-1,2)},
  io:x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2,ox:x=>x>=1?1:1-Math.pow(2,-10*x),is:x=>-(Math.cos(Math.PI*x)-1)/2};
const cl=x=>Math.max(0,Math.min(1,x)),P=(t,a,d)=>cl((t-a)/d),L=(a,b,k)=>a+(b-a)*k,$=id=>document.getElementById(id);
function T(el,o){if(typeof el==='string')el=$(el);if(!el)return;const{x=0,y=0,z=0,s=1,r=0,rx=0,ry=0,op=1}=o;
  el.style.transform=`perspective(1800px) translate3d(${x}px,${y}px,${z}px) rotateX(${rx}deg) rotateY(${ry}deg) rotate(${r}deg) scale(${s})`;
  el.style.opacity=op;if('bl' in o)el.style.filter=o.bl>0.05?`blur(${o.bl.toFixed(2)}px)`:'none';}
window.HOLE=new URLSearchParams(location.search).has('hole');
if(HOLE){document.documentElement.style.background='transparent';document.body.style.background='transparent';document.body.classList.add('hole');}

// 把元素里的字拆成单字 span.c（保留嵌套的 span，比如渐变字）
function splitChars(el){if(typeof el==='string')el=$(el);const walk=n=>{[...n.childNodes].forEach(c=>{if(c.nodeType===3){const f=document.createDocumentFragment();
  [...c.textContent].forEach(ch=>{const s=document.createElement('span');s.className='c';s.textContent=ch;if(ch===' ')s.style.width='.3em';f.appendChild(s);});c.replaceWith(f);}
  else if(c.nodeType===1&&!c.classList.contains('c'))walk(c);});};walk(el);return el;}
// 逐字：模糊→清晰、从下浮起（发布会式）
function chars(el,lt,at,st=0.045,dur=0.7,dy=26,bl=22){if(typeof el==='string')el=$(el);el.querySelectorAll('.c').forEach((c,i)=>{const k=P(lt,at+i*st,dur);
  c.style.opacity=E.oc(k);c.style.transform=`translateY(${L(dy,0,E.oq(k))}px)`;c.style.filter=k<1?`blur(${L(bl,0,E.oc(k)).toFixed(1)}px)`:'none';});}
// 整块：模糊淡入
function fadeIn(el,lt,at,dur=0.8,dy=24,bl=16){const k=P(lt,at,dur);T(el,{y:L(dy,0,E.oq(k)),op:E.oc(k),bl:L(bl,0,E.oc(k))});}
// 打字
function typing(el,caret,lt,at,dur,text){const n=Math.floor(L(0,text.length,P(lt,at,dur)));$(el).textContent=text.slice(0,n);
  $(caret).style.opacity=(lt<at||n<text.length||Math.floor(lt*2.4)%2)?1:0;}
// 素材窗挖洞路径（evenodd：整屏减去圆角矩形）
function holePath(x,y,w,h,r){r=Math.max(0,Math.min(r,w/2,h/2));if(w<=0||h<=0)return 'none';
  return `path(evenodd, "M0 0H1080V1920H0Z M${x+r} ${y}H${x+w-r}A${r} ${r} 0 0 1 ${x+w} ${y+r}V${y+h-r}A${r} ${r} 0 0 1 ${x+w-r} ${y+h}H${x+r}A${r} ${r} 0 0 1 ${x} ${y+h-r}V${y+r}A${r} ${r} 0 0 1 ${x+r} ${y}Z")`;}
function setHole(rect){document.querySelectorAll('.bgl').forEach(e=>{e.style.clipPath=rect?holePath(...rect):'none';});}

let CH=[];
function buildSubs(){CH=[];TL.subs.forEach(([a,b,ch])=>{const tot=ch.join('').length;let c=a;ch.forEach(tx=>{const d=(b-a)*tx.length/tot;CH.push([c,c+d,tx]);c+=d;});});}
function render(t){
  let cur=TL.scenes[0];for(const s of TL.scenes)if(t>=s[1])cur=s;
  for(const s of TL.scenes)$(s[0]).style.display=(s===cur)?'block':'none';
  const [id,st,en]=cur;const lt=t-st;
  setHole(null);
  V[id](lt,t,en-st);
  if(V.global)V.global(t,id,lt);
  const c=CH.find(c=>t>=c[0]&&t<c[1]);const sp=$('subt');sp.textContent=c?c[2]:'';
  if(c){const k=P(t,c[0],.22);sp.style.opacity=E.oc(k);sp.style.filter=k<1?`blur(${L(8,0,k).toFixed(1)}px)`:'none';
    const w=sp.scrollWidth;sp.style.transform=`scale(${Math.min(1,960/w)})`;}
  // 转场：每个场景交界处「沉到底色」再起来
  let d=0;for(let i=1;i<TL.scenes.length;i++){const b=TL.scenes[i][1];d=Math.max(d,1-Math.abs(t-b)/(V.dipW||0.32));}
  $('dip').style.opacity=E.is(cl(d));
}
window.DUR=0;
function boot(){buildSubs();window.DUR=TL.scenes[TL.scenes.length-1][2];document.querySelectorAll('[data-ep]').forEach(e=>{e.textContent=EP[e.dataset.ep];});
  document.querySelectorAll('[data-split]').forEach(splitChars);if(V.init)V.init();window.render=render;render(0);}
