import numpy as np, wave, sys
SR=44100; DUR=float(sys.argv[1]); BPM=84; beat=60/BPM; bar=4*beat
n=int(SR*DUR); L=np.zeros(n); R=np.zeros(n)
def hz(m): return 440*2**((m-69)/12)
# progression: Cmaj7 - Am7 - Fmaj7 - G6sus (2 bars each)
prog=[[48,55,64,71],[45,55,60,67],[41,57,60,64],[43,55,62,69]]
t_bar=np.arange(int(SR*bar*2))/SR
env=np.minimum(1,t_bar/1.2)*np.minimum(1,(t_bar[-1]-t_bar)/1.2)
rng=np.random.default_rng(3)
i=0; pos=0
while pos<n:
    ch=prog[i%4]; seg=np.zeros(len(t_bar))
    for m in ch:
        f=hz(m)
        for det in (-0.12,0.12):
            seg+=np.sin(2*np.pi*f*(1+det/100)*t_bar)*0.5+0.12*np.sin(2*np.pi*2*f*t_bar)
    seg*=env*0.05
    k=min(len(seg),n-pos); L[pos:pos+k]+=seg[:k]; R[pos:pos+k]+=seg[:k]
    # arpeggio: eighth notes, soft plucks
    arp=[ch[1]+12,ch[2]+12,ch[3]+12,ch[2]+12]
    for s in range(16):
        st=pos+int(s*beat/2*SR)
        if st>=n: break
        m=arp[s%4]; tt=np.arange(int(SR*1.4))/SR
        p=np.sin(2*np.pi*hz(m)*tt)*np.exp(-tt*3.2)*0.045*(0.8+0.4*rng.random())
        k=min(len(p),n-st); pan=0.35+0.3*(s%2)
        L[st:st+k]+=p[:k]*(1-pan); R[st:st+k]+=p[:k]*pan
    # soft bass
    tb=np.arange(len(t_bar))/SR; b=np.sin(2*np.pi*hz(ch[0]-12)*tb)*env*0.06
    k=min(len(b),n-pos); L[pos:pos+k]+=b[:k]; R[pos:pos+k]+=b[:k]
    pos+=len(t_bar); i+=1
# simple reverb-ish echo
for d,g in ((0.23,0.3),(0.41,0.2),(0.67,0.12)):
    s=int(d*SR); L[s:]+=g*R[:-s]; R[s:]+=g*L[:-s]
fade=np.ones(n); f=int(3*SR); fade[:f]=np.linspace(0,1,f); fade[-f:]=np.linspace(1,0,f)
st=np.stack([L*fade,R*fade],1); st/=np.abs(st).max()/0.8
w=wave.open('music.wav','wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((st*32767).astype('<i2').tobytes()); w.close()
