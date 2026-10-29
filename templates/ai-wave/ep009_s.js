 n1(lt,b,t){S.news('n1',lt,b,t);const d=TL.durs[1],f=x=>0.3+d*x;
  S.stk('n1-stkA',lt,1.4,b-0.25);S.stk('n1-stkB',lt,b+TL.durs[2]*0.45);
  [0,1,2].forEach(i=>{const k=P(lt,f(0.62+i*0.1),0.45);T('n1-c'+i,{s:L(0,1,E.ob(k)),op:k>0?1:0});T('n1-v'+i,{y:L(30,0,E.oc(k)),op:P(lt,f(0.62+i*0.1)+0.15,0.25)});});
  const d2=TL.durs[2];[0.0,0.45,0.66,0.84].forEach((x,i)=>{const at=b+d2*x;const k=P(lt,at,0.4);T('n1-r'+i,{x:L(60,0,E.oc(k)),s:L(0.7,1,E.ob(k)),op:k>0?1:0});});},
 n2(lt,b,t){S.news('n2',lt,b,t);const d=TL.durs[3],f=x=>0.3+d*x;
  S.stk('n2-stkA',lt,f(0.86),b-0.25);S.stk('n2-stkB',lt,b+TL.durs[4]*0.6);
  const kn=E.oc(P(lt,f(0.55),1.0));$('n2-num').textContent=Math.round(L(0,59,kn));
  const k1=P(lt,f(0.86),0.35);T('n2-no1',{s:L(2.4,1,E.oc(k1)),r:-6,op:k1>0?1:0});
  ['n2-b1','n2-b2'].forEach((e,i)=>{const k=P(lt,1.2+i*0.25,0.4);T(e,{y:L(30,0,E.oc(k)),op:k});});
  const kb=P(lt,b,0.35);$('n2-a').style.opacity=1-kb;$('n2-b').style.opacity=kb;
  const d4=TL.durs[4];[0,0.55,0.7].forEach((x,i)=>{const k=P(lt,b+0.2+d4*x,0.4);T('n2-q'+i,{x:L(80,0,E.oc(k)),op:k});});},
 n3(lt,b,t){S.news('n3',lt,b,t);const d=TL.durs[5],f=x=>0.3+d*x;S.stk('n3-stk',lt,f(0.9));
  const kh=E.ob(P(lt,1.0,0.5));T('n3-hub',{s:L(0.3,1,kh),op:kh>0?1:0});
  [0.52,0.6,0.68].forEach((x,i)=>{const k=P(lt,f(x),0.4);T('n3-t'+i,{s:L(0.3,1,E.ob(k)),op:k>0?1:0});$('n3-l'+i).style.opacity=k;$('n3-l'+i).style.strokeDashoffset=-lt*40;});
  const k3=P(lt,b+TL.durs[6]*0.3,0.45);T('n3-t3',{s:L(0.3,1,E.ob(k3)),op:k3>0?1:0});$('n3-l3').style.opacity=k3;$('n3-l3').style.strokeDashoffset=-lt*40;
  const kc=P(lt,b+TL.durs[6]*0.62,0.4);T('n3-chip',{y:L(30,0,E.oc(kc)),op:kc});},
 n4(lt,b,t){S.news('n4',lt,b,t);const d=TL.durs[7],f=x=>0.3+d*x;
  const ktry=P(lt,f(0.5),0.3);T('n4-try',{op:ktry>0?(0.5+0.5*Math.abs(Math.sin(lt*5))):0});
  const kc=E.io(P(lt,f(0.55),d*0.33));const kd=E.io(P(lt,b+0.2,1.6));
  const sec=Math.round(L(0,900,kc)+L(0,180,kd));$('n4-time').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');
  $('n4-fill').style.width=(sec/1080*100)+'%';
  const ka=P(lt,f(0.88),0.3);T('n4-alert',{s:L(2.2,1,E.oc(ka)),r:-4+(ka>=1&&lt<f(0.88)+0.8?Math.sin(lt*60)*3:0),op:ka>0?1:0});
  S.stk('n4-stk',lt,f(0.92));
  const kh=P(lt,b+1.6,0.4);T('n4-hand',{s:L(0.3,1,E.ob(kh)),r:3,op:kh>0?1:0});},
