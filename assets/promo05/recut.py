import re,json
W=[]  # (start,end,text,sent)
for line in open('transcript.txt'):
    m=re.match(r'S(\d+) \[',line)
    if m: s=int(m.group(1)); continue
    for a,b,t in re.findall(r'([\d.]+)~([\d.]+)(\S+)',line):
        W.append((float(a),float(b),t,s))
def idx(t):  # index of word starting at time t
    return min(range(len(W)),key=lambda i:abs(W[i][0]-t))
def idxe(t):
    return min(range(len(W)),key=lambda i:abs(W[i][1]-t))
# 选段：(第一个词开始时间, 最后一个词结束时间, zoom)
SEL=[(0.14,1.58,1.0),(4.44,9.36,1.0),(11.00,11.98,1.0),(13.40,14.76,1.0),(16.86,19.52,1.0),
     (29.53,32.05,1.0),(40.64,43.48,1.12),
     (52.06,56.32,1.0),(60.82,65.68,1.0),(67.62,84.34,1.0),(88.44,93.54,1.08),
     (98.70,109.12,1.0),
     (141.62,152.42,1.0),(202.92,206.80,1.1),(227.64,231.52,1.12),(233.95,235.09,1.0),(237.37,237.51,1.0)]
GAP=0.45   # 段内停顿超过这个就剪掉，两边各留一点
HEAD,TAIL=0.14,0.30
clips=[]
for a,b,z in SEL:
    i,j=idx(a),idxe(b)
    # 段内按长停顿拆开
    start=i
    for k in range(i,j+1):
        last = k==j or (W[k+1][0]-W[k][1])>GAP
        if last:
            s0=W[start][0]; e0=W[k][1]
            prev_end=W[start-1][1] if start>0 else 0
            nxt=W[k+1][0] if k+1<len(W) else e0+1
            cs=max(s0-HEAD, prev_end+0.04) if start>i or start==i else s0-HEAD
            cs=max(s0-HEAD, prev_end+0.04)
            ce=min(e0+TAIL, nxt-0.04)
            txt=''.join(W[q][2] for q in range(start,k+1))
            clips.append({"start":round(cs,2),"end":round(ce,2),"zoom":z,"text":re.sub(r'[,，。?？]$','',txt).replace('Cloud','Claude').replace(',','，').replace('Dark Listing','Draft Listing')})
            start=k+1
tot=0
for c in clips:
    d=c['end']-c['start'];tot+=d
    print(f"{c['start']:7.2f}-{c['end']:7.2f} {d:5.2f} z{c['zoom']} {c['text']}")
print('total',round(tot,2))
json.dump(clips,open('clips2.json','w'),ensure_ascii=False)
