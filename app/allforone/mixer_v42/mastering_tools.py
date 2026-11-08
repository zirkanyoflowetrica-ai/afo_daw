"""Limitación enlazada 4x por bloques: memoria acotada para canciones largas."""
import numpy as np
from scipy.signal import resample_poly
from scipy.ndimage import maximum_filter1d

def oversampled_blocks(x,block):
    for start in range(0,x.shape[-1],block):
        end=min(x.shape[-1],start+block)
        left=max(0,start-64);right=min(x.shape[-1],end+64)
        up=resample_poly(x[:,left:right],4,1,axis=-1).astype('float32')
        yield start,end,left,right,up

def true_peak_db(x,sr):
    peak=0.
    for start,end,left,right,up in oversampled_blocks(x,sr*4):
        core=up[:,(start-left)*4:(end-left)*4]
        if core.size:peak=max(peak,float(np.max(abs(core))))
    return 20*np.log10(max(peak,1e-6)) if peak else -120.

def limit_linked(x,sr,ceiling_db=-1.,max_reduction_db=5.):
    if not x.size:
        return x.copy(),dict(max_reduction_db=0.,p95_reduction_db=0.,limited_percent=0.,drive_trim_db=0.)
    step=max(1,sr//1000)
    block=step*4096
    n=x.shape[-1]
    count=(n+step-1)//step
    peaks=np.zeros(count,dtype='float32')
    for start,end,left,right,up in oversampled_blocks(x,block):
        values=np.max(abs(up[:,(start-left)*4:(end-left)*4]),axis=0)
        padding=(-len(values))%(step*4)
        values=np.pad(values,(0,padding)).reshape(-1,step*4).max(axis=1)
        index=start//step
        peaks[index:index+len(values)]=values
    ceiling=10**((ceiling_db-.12)/20)
    peak=float(peaks.max())
    trim=min(1.,ceiling*10**(max_reduction_db/20)/max(peak,1e-12))
    future=maximum_filter1d(peaks*trim,size=7,mode='nearest')
    held=np.empty_like(future)
    release=np.exp(-step/(sr*.1))
    last=0.
    for i,v in enumerate(future):
        last=max(float(v),last*release);held[i]=last
    db=np.minimum(0.,20*np.log10(ceiling/np.maximum(held,1e-12)))
    positions=np.arange(len(db))*step*4
    out=np.empty_like(x)
    max_gr=0.
    for start,end,left,right,up in oversampled_blocks(x,block):
        up*=trim
        gain_db=np.interp(np.arange(left*4,right*4),positions,db).astype('float32')
        bound=np.minimum(1.,ceiling/np.maximum(np.max(abs(up),axis=0),1e-12))
        curve=np.minimum(10**(gain_db/20),bound)
        core_curve=curve[(start-left)*4:(end-left)*4]
        maximum=float(-20*np.log10(max(float(core_curve.min()),1e-12)))
        max_gr=max(max_gr,maximum)
        native=resample_poly(up*curve[None,:],1,4,axis=-1)
        out[:,start:end]=native[:,start-left:end-left]
    return out,dict(max_reduction_db=max_gr,p95_reduction_db=float(np.percentile(-db,95)),limited_percent=float(np.mean(db<-.1)*100),drive_trim_db=float(-20*np.log10(trim)))

def dynamics_summary(x,sr):
    if not x.size:return dict(crest_db=0.,window_range_db=0.,stereo_correlation=None)
    energy=float(np.einsum('ij,ij->',x,x,dtype=np.float64)/x.size)
    levels=[]
    for i in range(0,x.shape[-1],sr*3):
        z=x[:,i:i+sr*3]
        p=float(np.einsum('ij,ij->',z,z,dtype=np.float64)/z.size)
        if p>1e-10:levels.append(10*np.log10(p))
    crest=20*np.log10(max(float(np.max(abs(x))),1e-12)/max(np.sqrt(energy),1e-12))
    spread=float(np.percentile(levels,90)-np.percentile(levels,10)) if levels else 0.
    corr=None
    if x.shape[0]==2:
        e=np.einsum('ij,ij->i',x,x,dtype=np.float64)
        corr=float(np.einsum('i,i->',x[0],x[1],dtype=np.float64)/max(np.sqrt(e[0]*e[1]),1e-12))
    return dict(crest_db=float(crest),window_range_db=spread,stereo_correlation=corr)
