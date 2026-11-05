 n1(lt,b,t){S.news('n1',lt,b,t);const d=TL.durs;const tS=0.3+d[1]*0.28,tG=0.3+d[1]*0.68;
  S.stk('n1-stkA',lt,1.4,b-0.25);S.stk('n1-stkB',lt,b+d[2]*0.55);
  $('n1-b0').style.width=(E.io(P(lt,tS,2.4))*55)+'%';$('n1-b1').style.width=(E.io(P(lt,tS,1.2))*100)+'%';
  const kp=P(lt,tS+1.2,0.4);T('n1-pct',{s:L(0.4,1,E.ob(kp)),op:kp>0?1:0});
  const kg=P(lt,tG,0.45);T('n1-gif',{s:L(0.3,1,E.ob(kg)),r:L(-12,0,E.oc(kg)),op:kg>0?1:0});
  const fr=Math.floor(Math.max(0,lt-tG)*8)%8;T('n1-ball',{y:-60*Math.abs(Math.sin(fr/8*Math.PI)),x:(fr-4)*6});$('n1-fr').textContent='帧 '+(fr+1)+'/8';
  ['n1-c0','n1-c1','n1-c2'].forEach((e,i)=>{const k=P(lt,b+d[2]*0.45+i*0.25,0.4);T(e,{s:L(0.4,1,E.ob(k)),op:k>0?1:0});});},
 n2(lt,b,t){S.news('n2',lt,b,t);const d=TL.durs;S.stk('n2-stk',lt,1.5);
  const kq=P(lt,0.3+d[3]*0.42,0.4);T('n2-q',{y:L(30,0,E.oc(kq)),op:kq});
  const ka=P(lt,0.3+d[3]*0.55,0.45);T('n2-ans',{s:L(0.5,1,E.ob(ka)),op:ka>0?1:0});
  ['n2-c0','n2-c1','n2-c2'].forEach((e,i)=>{const k=P(lt,0.3+d[3]*0.68+i*0.35,0.4);T(e,{s:L(0.4,1,E.ob(k)),op:k>0?1:0});});
  const kb=P(lt,b+0.2,0.45);T('n2-btn',{s:L(0.4,1,E.ob(kb))*(1+0.03*Math.sin(Math.max(0,lt-b-0.7)*6)),op:kb>0?1:0});
  const kst=P(lt,b+d[4]*0.4,0.3);T('n2-st',{op:kst});
  [0.42,0.62,0.95].forEach((h,i)=>{const k=E.oc(P(lt,b+d[4]*0.45+i*0.3,0.5));$('n2-g'+i).style.height=(h*170*k)+'px';});
  T('n2-gl',{op:P(lt,b+d[4]*0.45+1.0,0.3)});},
 n3(lt,b,t){S.news('n3',lt,b,t);const d=TL.durs;const tA=0.3+d[5]*0.22,t1=0.3+d[5]*0.5,t2=0.3+d[5]*0.72;
  S.stk('n3-stk',lt,b+d[6]*0.62);
  const lines=['$ scan linux/kernel','  mm/   fs/   net/','  → reproduce ...','  → exploit → root'];
  const nl=lt<tA?0:Math.min(4,1+Math.floor((lt-tA)/0.5));$('n3-log').textContent=lines.slice(0,nl).join('\n');
  $('n3-n1').textContent=Math.round(1724*E.io(P(lt,t1,1.6))).toLocaleString('en-US');
  $('n3-n2').textContent=Math.round(948*E.io(P(lt,t2,1.4)));
  T('n3-patch',{op:P(lt,t2+1.8,0.4)});
  const kc=P(lt,b+0.2,0.4);T('n3-cost',{y:L(40,0,E.oc(kc)),op:kc});
  const ke=P(lt,b+d[6]*0.3,0.4);T('n3-each',{y:L(40,0,E.oc(ke)),op:ke});},
