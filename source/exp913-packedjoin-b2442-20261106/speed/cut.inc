
namespace tariff {
extern "C" const uint8_t scPrices[],scEnd[];
asm(".pushsection .rodata\n.p2align 12\n.global scPrices,scEnd\nscPrices:\n.incbin \"p1.zst\"\nscEnd:\n.p2align 12\n.popsection");
static uint8_t* ids;static uint16_t* words;static uint8_t* price;
static constexpr unsigned groupCount=120;
static constexpr uint8_t group[120]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119};
static void init(){size_t n=13831136;ids=(uint8_t*)mmap(nullptr,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(ids!=MAP_FAILED,"cost arena");words=(uint16_t*)(ids+11427840);price=ids+12637376;
 require(ZSTD_decompress(ids,n,scPrices,scEnd-scPrices)==n,"response book");uintptr_t b=(uintptr_t(scPrices)+4095)&~uintptr_t(4095),e=uintptr_t(scEnd)&~uintptr_t(4095);if(e>b)munmap((void*)b,e-b);}
static inline unsigned at(unsigned i,unsigned nibble,unsigned bucket,unsigned x){if(!nibble)return 0;unsigned row;memcpy(&row,ids+3*(i*16+nibble),4);return price[120u*words[4*(row&0xffffffu)+bucket]+x];}
static inline int price_result(int original,int intrinsicPlusFees,unsigned key,unsigned cell,unsigned tag,int x,int X){if(!tag)return original;
 unsigned pair=key/480,ctx=key-480*pair,g=ctx,band=2u*(cell>=46)+(cell%46!=0);
 const unsigned fi=(pair/288)*480+g,bi=(208+pair%288)*480+g;
 unsigned f=at(fi,tag&15,band,x),b=at(bi,tag>>4,band,X);unsigned delta=std::max(f,b);
 return delta>=8?std::max(original,intrinsicPlusFees+int(delta)):original;}
}
