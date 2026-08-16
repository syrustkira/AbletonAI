#include "n0te_dsp.h"
#include "n0te_ring.h"
#include <assert.h>
#include <math.h>
int main(void){
 float audio[]={.5f,-.5f,2.f};n0te_gain gain={.5f,0};n0te_gain_process(&gain,audio,3);assert(fabsf(audio[0]-.25f)<1e-6f);assert(audio[2]==1.f);
 n0te_gain hot={2.f,0};n0te_gain_process(&hot,audio,3);assert(audio[2]==2.f);
 n0te_polarity_process(audio,3,0);assert(audio[0]<0);
 float memory[8],input[]={1,2,3},output[3]={0};n0te_ring ring;assert(n0te_ring_init(&ring,memory,8));assert(n0te_ring_write(&ring,input,3)==3);assert(n0te_ring_read(&ring,output,3)==3);assert(output[2]==3);assert(atomic_load(&ring.sequence)==1);
 n0te_limiter limiter={.5f,.99f,1.f,0};float loud[]={1.f,1.f};n0te_limiter_process(&limiter,loud,2);assert(loud[0]<=.5f);
 n0te_compressor compressor={.5f,4.f,0.f,.99f,0.f,1.f,0};float compressed[]={2.f};n0te_compressor_process(&compressor,compressed,1);assert(compressed[0]>1.f);
 n0te_transient transient={-.5f,0,0,0,.9f,.99f,0};float hit[]={0,1.5f,0};n0te_transient_process(&transient,hit,3);assert(hit[1]<1.5f);assert(hit[1]>0.f);
 n0te_transient boost={.5f,0,0,0,.9f,.99f,0};float boosted[]={0,1.5f,0};n0te_transient_process(&boost,boosted,3);assert(boosted[1]>1.5f);
 return 0;
}
