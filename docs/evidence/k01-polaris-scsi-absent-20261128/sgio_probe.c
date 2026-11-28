/* bsg_sgio_probe.c - read-only SG_IO feasibility probe for the Polaris K-01.
 *
 * Issues a SCSI INQUIRY (read-only, no state change) against a device node and
 * prints the result. Used to decide whether libgphoto2's usbscsi port driver
 * could use /dev/bsg/<H:T:L> on a kernel that has no SCSI generic (sg) layer.
 *
 * Build: arm-linux-gnueabi-gcc -static -o bsg_sgio_probe bsg_sgio_probe.c
 * Run:   ./bsg_sgio_probe /dev/bsg/0:0:0:0
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

#ifndef SG_IO
#define SG_IO 0x2285
#endif

/* Use the canonical kernel layout for sg_io_hdr_t rather than a hand-rolled one,
 * so field names (dxfer_p, sense_p) and ordering match what SG_IO expects. */
#include <scsi/sg.h>

int main(int argc, char **argv)
{
    const char *path = (argc > 1) ? argv[1] : "/dev/bsg/0:0:0:0";
    int fd;
    unsigned char inq[96];
    unsigned char sense[32];
    sg_io_hdr_t io;

    memset(inq, 0, sizeof(inq));
    memset(sense, 0, sizeof(sense));

    /* INQUIRY: opcode 0x12, no flags, page code 0, alloc length 96. */
    unsigned char cmd[6] = { 0x12, 0x00, 0x00, 0x00, 96, 0x00 };

    fd = open(path, O_RDWR);
    if (fd < 0) {
        perror("open");
        return 2;
    }

    memset(&io, 0, sizeof(io));
    io.interface_id    = 'S';
    io.dxfer_direction = SG_DXFER_FROM_DEV;
    io.cmd_len         = sizeof(cmd);
    io.mx_sb_len       = sizeof(sense);
    io.dxfer_len       = sizeof(inq);
    io.dxferp          = inq;
    io.cmdp            = cmd;
    io.sbp             = sense;
    io.timeout         = 5000;

    if (ioctl(fd, SG_IO, &io) < 0) {
        perror("ioctl SG_IO");
        close(fd);
        return 3;
    }

    printf("path=%s status=%u masked=%u resid=%d host=%u driver=%u\n",
           path, io.status, io.masked_status, io.resid,
           io.host_status, io.driver_status);
    if (io.status == 0) {
        inq[sizeof(inq) - 1] = '\0';
        sense[sizeof(sense) - 1] = '\0';
        printf("INQUIRY OK vendor=[%.8s] model=[%.16s] rev=[%.4s]\n",
               inq + 8, inq + 16, inq + 32);
        printf("VERDICT=SGIO_OK\n");
    } else {
        printf("sense key=%u asc=%02x ascq=%02x\n",
               sense[2] & 0x0f, sense[12], sense[13]);
        printf("VERDICT=SGIO_CMD_FAILED\n");
    }
    close(fd);
    return 0;
}
