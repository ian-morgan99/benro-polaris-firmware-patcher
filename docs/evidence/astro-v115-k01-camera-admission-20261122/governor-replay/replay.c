#define main original_test_main
#include "test_stage2_backoff_isolation.c"
#undef main
int main(int argc, char **argv) {
    int cam=0, t, duration, busy=0, total=0;
    reset_fixture();
    fake_model_string="Pentax K-1 Mark II (PTP mode)";
    unsetenv("STAGE2_PENTAX_PREVIEW_BACKOFF");
    unsetenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS");
    if(argc==2)setenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS",argv[1],1);
    while(scanf("%d %d",&t,&duration)==2){
        clock_ms=60000+t;fake_preview_ms=duration;
        int rc=stage2_shim_gp_camera_capture_preview(&cam,NULL,NULL);
        if(rc==STAGE2_GP_ERROR_CAMERA_BUSY)busy++;else assert(rc==0);
        total++;
    }
    printf("requests=%d fetches=%d busy=%d\n",total,fake_preview_calls,busy);
}
