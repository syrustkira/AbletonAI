#ifndef N0TE_RING_H
#define N0TE_RING_H
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
typedef struct {float*data;size_t capacity;_Atomic size_t read_index;_Atomic size_t write_index;_Atomic uint64_t sequence;_Atomic uint64_t overruns;_Atomic uint64_t underruns;} n0te_ring;
int n0te_ring_init(n0te_ring*,float*,size_t);
size_t n0te_ring_write(n0te_ring*,const float*,size_t);
size_t n0te_ring_read(n0te_ring*,float*,size_t);
void n0te_ring_reset(n0te_ring*);
#endif
