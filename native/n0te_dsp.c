#include "n0te_dsp.h"
#include <math.h>
static float clamp(float x,float lo,float hi){return x<lo?lo:(x>hi?hi:x);}
void n0te_gain_process(n0te_gain*s,float*x,size_t n){if(s->bypass)return;for(size_t i=0;i<n;i++)x[i]*=s->gain;}
void n0te_polarity_process(float*x,size_t n,int bypass){if(bypass)return;for(size_t i=0;i<n;i++)x[i]=-x[i];}
void n0te_biquad_reset(n0te_biquad*s){s->x1=s->x2=s->y1=s->y2=0;}
void n0te_biquad_process(n0te_biquad*s,float*x,size_t n){if(s->bypass)return;for(size_t i=0;i<n;i++){float y=s->b0*x[i]+s->b1*s->x1+s->b2*s->x2-s->a1*s->y1-s->a2*s->y2;s->x2=s->x1;s->x1=x[i];s->y2=s->y1;s->y1=y;x[i]=y;}}
void n0te_compressor_process(n0te_compressor*s,float*x,size_t n){if(s->bypass)return;for(size_t i=0;i<n;i++){float peak=fabsf(x[i]);float c=peak>s->envelope?s->attack:s->release;s->envelope=c*s->envelope+(1-c)*peak;float target=1;if(s->envelope>s->threshold)target=powf(s->threshold/s->envelope,1-1/s->ratio);s->gain=.9f*s->gain+.1f*target;x[i]*=s->gain;}}
void n0te_limiter_process(n0te_limiter*s,float*x,size_t n){if(s->bypass)return;for(size_t i=0;i<n;i++){float peak=fabsf(x[i]);float target=peak>s->ceiling?s->ceiling/peak:1;s->gain=target<s->gain?target:s->release*s->gain+(1-s->release)*target;x[i]=clamp(x[i]*s->gain,-s->ceiling,s->ceiling);}}
void n0te_transient_process(n0te_transient*s,float*x,size_t n){if(s->bypass)return;for(size_t i=0;i<n;i++){float peak=fabsf(x[i]);s->fast=s->fast_coeff*s->fast+(1-s->fast_coeff)*peak;s->slow=s->slow_coeff*s->slow+(1-s->slow_coeff)*peak;float transient=fmaxf(0,s->fast-s->slow)/fmaxf(s->fast,1e-9f);float gain=fmaxf(0,1+s->attack*transient+s->sustain*(1-transient)*.5f);x[i]*=gain;}}
