// Axis-specific metadata. Two bits encode membership in either of the two fixed physical hole families.
static uint32_t xmd[120],ymd[550],moveTable[17100+2200],srcmd[496],vqX[239],vqY[1099];
static void initcompact(){
 for(int x=0;x<120;++x){unsigned hole=(x<16?1u:0u)|(x>=76&&x<90?2u:0u);xmd[x]=unsigned(vertical707[x])|(unsigned(prefixX707[x])<<11)|(hole<<28);}
 for(int y=0;y<550;++y){unsigned hole=(!arch.exists(0,y)?1u:0u)|(!arch.exists(80,y)?2u:0u);ymd[y]=unsigned(horizontal707[y])|(unsigned(prefixY707[y])<<11)|(unsigned(y/100)<<17)|(unsigned(blockMask707[y])<<20)|(hole<<28);for(int x=0;x<120;x++)require(arch.exists(x,y)==!bool((xmd[x]&ymd[y])>>28),"hole factor");}
 for(int p=0;p<496;++p){auto s=ports707[p];bool h=s.dx!=0;unsigned base=s.start==65535?17040:s.start;
  srcmd[p]=unsigned(s.source+1) | (base<<9) | (unsigned(h)<<25)|(unsigned(16+(h?s.dx:s.dy))<<26);
  if(s.source<0 || s.start==65535)continue;
  for(int y=0;y<550;y++)for(int x=0;x<120;++x){if(!arch.exists(x,y))continue;int o=h?x+horizontal707[y]:y+vertical707[x];auto m=motion707[base+o];if(m.coordinate==65535){moveTable[base+o]=0x80000000;continue;}
   int eff=int(m.coordinate)-(h?x+s.dx:y+s.dy),dp=h?prefixX707[m.coordinate]-prefixX707[x]:prefixY707[m.coordinate]-prefixY707[y];int cost=m.fee+m.line;require(eff>=-128&&eff<128&&dp>=-512&&dp<512&&cost<8192,"move pack");
   moveTable[base+o]=unsigned(eff+128)|(unsigned(dp+512)<<8)|(unsigned(cost)<<18);
  }
 }
 std::fill(moveTable+17040,moveTable+sizeof(moveTable)/4,128u+(512u<<8));
 for(int dx=-119;dx<=119;++dx){unsigned x=std::abs(dx);vqX[dx+119]=(125u*(x/10)<<14)|((18*(dx<0)+3*(unsigned(x>=20)+unsigned(x>=60)))<<7)|(12*(x%10));}
 for(int dy=-549;dy<=549;++dy){unsigned y=std::abs(dy);vqY[dy+549]=((dy<0?125u:127u)*(y/12)<<14)|((9*(dy<0)+unsigned(y>=48)+unsigned(y>=168))<<7)|(y%12);}
}
