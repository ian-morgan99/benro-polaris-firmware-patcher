/* SPDX-License-Identifier: MIT */
/* Native Gaia/POLCAT01 sky renderer.  Host and Polaris build target. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <jpeglib.h>

typedef struct { uint64_t id; double ra, dec, mag; } star_t;
static uint64_t rng=1;
static double frand01(void){rng=rng*6364136223846793005ULL+1442695040888963407ULL;return (double)((rng>>33)&0x7fffffff)/2147483648.0;}
static double gauss(void){double a=frand01();double b=frand01();if(a<1e-12)a=1e-12;return sqrt(-2*log(a))*cos(6.283185307179586*b);}
static void usage(const char *p){fprintf(stderr,"usage: %s --catalog FILE --ra D --dec D --out FILE.jpg [--roll D] [--focal-mm F] [--sensor-mm S] [--width W] [--height H] [--background N] [--noise N] [--flux N] [--seed N]\n",p);}
static int load(const char *fn,star_t **out){FILE*f=fopen(fn,"rb");char magic[8];uint32_t ver,n,i;star_t*s;if(!f)return 0;if(fread(magic,1,8,f)!=8||memcmp(magic,"POLCAT01",8)){fclose(f);return 0;}if(fread(&ver,4,1,f)!=1||fread(&n,4,1,f)!=1||ver!=1){fclose(f);return 0;}s=calloc(n,sizeof(*s));if(!s){fclose(f);return 0;}for(i=0;i<n;i++){if(fread(&s[i].id,8,1,f)!=1||fread(&s[i].ra,8,1,f)!=1||fread(&s[i].dec,8,1,f)!=1||fread(&s[i].mag,8,1,f)!=1){free(s);fclose(f);return 0;}}fclose(f);*out=s;return (int)n;}
int main(int ac,char**av){const char*catfn=0,*outfn=0;double ra=0,dec=0,roll=0,focal=100,sensor=36,bg=12,noise=1,flux=230;int W=1920,H=1280,i,j,n=0;star_t*s;unsigned char*im;struct jpeg_compress_struct c;struct jpeg_error_mgr e;FILE*f;
 for(i=1;i<ac;i++){if(!strcmp(av[i],"--catalog"))catfn=av[++i];else if(!strcmp(av[i],"--ra"))ra=atof(av[++i]);else if(!strcmp(av[i],"--dec"))dec=atof(av[++i]);else if(!strcmp(av[i],"--roll"))roll=atof(av[++i]);else if(!strcmp(av[i],"--focal-mm"))focal=atof(av[++i]);else if(!strcmp(av[i],"--sensor-mm"))sensor=atof(av[++i]);else if(!strcmp(av[i],"--width"))W=atoi(av[++i]);else if(!strcmp(av[i],"--height"))H=atoi(av[++i]);else if(!strcmp(av[i],"--background"))bg=atof(av[++i]);else if(!strcmp(av[i],"--noise"))noise=atof(av[++i]);else if(!strcmp(av[i],"--flux"))flux=atof(av[++i]);else if(!strcmp(av[i],"--seed"))rng=strtoull(av[++i],0,10);else if(!strcmp(av[i],"--out"))outfn=av[++i];else{usage(av[0]);return 2;}}
 if(!catfn||!outfn||W<1||H<1){usage(av[0]);return 2;}n=load(catfn,&s);if(n<=0){fprintf(stderr,"invalid POLCAT01 catalogue\n");return 1;}im=malloc((size_t)W*H);if(!im){free(s);return 1;}for(i=0;i<W*H;i++)im[i]=(unsigned char)fmax(0,fmin(255,bg));
 double cra=ra*M_PI/180,cdec=dec*M_PI/180,rr=roll*M_PI/180,scale=206264.806*atan((sensor/W)/focal);int drawn=0;
 for(i=0;i<n;i++){double r=s[i].ra*M_PI/180,d=s[i].dec*M_PI/180,dr=r-cra,den=sin(d)*sin(cdec)+cos(d)*cos(cdec)*cos(dr);if(den<=0)continue;double x=cos(d)*sin(dr)/den,y=(sin(d)*cos(cdec)-cos(d)*sin(cdec)*cos(dr))/den;double xx=(x*cos(rr)+y*sin(rr))*180/M_PI*3600/scale+W/2,yy=(-x*sin(rr)+y*cos(rr))*180/M_PI*3600/scale+H/2;double amp=flux*fmax(.15,fmin(1, pow(10,-.4*(s[i].mag-5)))),sig=3/2.355;if(xx<2||yy<2||xx>=W-2||yy>=H-2)continue;for(j=-12;j<=12;j++){int xj=(int)xx+j;if(xj<0||xj>=W)continue;for(int k=-12;k<=12;k++){int yk=(int)yy+k;if(yk<0||yk>=H)continue;double q=(j+xx-(int)xx)*(j+xx-(int)xx)+(k+yy-(int)yy)*(k+yy-(int)yy);int v=im[yk*W+xj]+(int)(amp*exp(-q/(2*sig*sig)));im[yk*W+xj]=(unsigned char)(v>255?255:v);}}drawn++;}
 for(i=0;i<W*H;i++){int v=im[i]+(int)(noise*gauss());im[i]=(unsigned char)(v<0?0:v>255?255:v);}f=fopen(outfn,"wb");if(!f){free(im);free(s);return 1;}c.err=jpeg_std_error(&e);jpeg_create_compress(&c);jpeg_stdio_dest(&c,f);c.image_width=W;c.image_height=H;c.input_components=1;c.in_color_space=JCS_GRAYSCALE;jpeg_set_defaults(&c);jpeg_set_quality(&c,92,1);jpeg_start_compress(&c,1);while(c.next_scanline<(unsigned)H){JSAMPROW row=im+c.next_scanline*W;jpeg_write_scanlines(&c,&row,1);}jpeg_finish_compress(&c);jpeg_destroy_compress(&c);fclose(f);free(im);free(s);fprintf(stderr,"[ind-skysim] %dx%d scale %.6f stars %d -> %s\n",W,H,scale,drawn,outfn);return 0;}
