#ifndef N0TE_DSP_H
#define N0TE_DSP_H
#include <stddef.h>
typedef struct { float gain; int bypass; } n0te_gain;
typedef struct { float b0,b1,b2,a1,a2,x1,x2,y1,y2; int bypass; } n0te_biquad;
typedef struct { float threshold,ratio,attack,release,envelope,gain; int bypass; } n0te_compressor;
typedef struct { float ceiling,release,gain; int bypass; } n0te_limiter;
typedef struct { float attack,sustain,fast,slow,fast_coeff,slow_coeff; int bypass; } n0te_transient;
void n0te_gain_process(n0te_gain*,float*,size_t);
void n0te_polarity_process(float*,size_t,int);
void n0te_biquad_reset(n0te_biquad*);
void n0te_biquad_process(n0te_biquad*,float*,size_t);
void n0te_compressor_process(n0te_compressor*,float*,size_t);
void n0te_limiter_process(n0te_limiter*,float*,size_t);
void n0te_transient_process(n0te_transient*,float*,size_t);
#endif
