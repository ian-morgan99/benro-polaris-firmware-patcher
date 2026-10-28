/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
static void be16(unsigned char*p,unsigned v){p[0]=v>>8;p[1]=v;}
static void be32(unsigned char*p,unsigned v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
int main(int ac,char**av){const char*in=0,*out=0,*json=0;FILE*f,*g;long n;size_t jlen,i;unsigned char*buf,*app;char*text;const char prefix[]="ASCII\0\0\0";
for(i=1;i<(size_t)ac;i++){if(!strcmp(av[i],"--in"))in=av[++i];else if(!strcmp(av[i],"--out"))out=av[++i];else if(!strcmp(av[i],"--json"))json=av[++i];else return 2;}if(!in||!out||!json)return 2;
f=fopen(in,"rb");if(!f)return 3;fseek(f,0,SEEK_END);n=ftell(f);fseek(f,0,SEEK_SET);if(n<2){fclose(f);return 3;}buf=malloc((size_t)n);if(!buf||fread(buf,1,(size_t)n,f)!=(size_t)n){fclose(f);free(buf);return 3;}fclose(f);
f=fopen(json,"rb");if(!f){free(buf);return 3;}fseek(f,0,SEEK_END);jlen=(size_t)ftell(f);fseek(f,0,SEEK_SET);text=malloc(jlen+1);if(!text||fread(text,1,jlen,f)!=jlen){fclose(f);free(buf);free(text);return 3;}fclose(f);text[jlen]=0;
size_t plen=40+jlen;app=calloc(1,plen);if(!app||plen+2>65533){free(buf);free(text);free(app);return 4;}memcpy(app,"Exif\0\0",6);app[6]='M';app[7]='M';be16(app+8,42);be32(app+10,8);be16(app+14,1);be16(app+16,0x9286);be16(app+18,7);be32(app+20,(unsigned)(8+jlen));be32(app+24,34);be32(app+28,0);memcpy(app+32,prefix,8);memcpy(app+40,text,jlen);
g=fopen(out,"wb");if(!g){free(buf);free(text);free(app);return 3;}if(buf[0]!=0xff||buf[1]!=0xd8){fclose(g);free(buf);free(text);free(app);return 4;}fwrite(buf,1,2,g);unsigned seg=(unsigned)plen+2;unsigned char h[4]={0xff,0xe1,seg>>8,seg};fwrite(h,1,4,g);fwrite(app,1,plen,g);fwrite(buf+2,1,(size_t)n-2,g);fclose(g);free(buf);free(text);free(app);return 0;}
