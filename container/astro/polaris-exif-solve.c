/* SPDX-License-Identifier: MIT */
/*
 * Add one private UserComment EXIF tag while leaving the original JPEG bytes
 * intact after SOI. The caller writes to a same-directory temporary file and
 * atomically renames it only after this program succeeds.
 */
#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

static void be16(unsigned char *p, unsigned v) {
    p[0] = (unsigned char)(v >> 8);
    p[1] = (unsigned char)v;
}

static void be32(unsigned char *p, unsigned v) {
    p[0] = (unsigned char)(v >> 24);
    p[1] = (unsigned char)(v >> 16);
    p[2] = (unsigned char)(v >> 8);
    p[3] = (unsigned char)v;
}

static int write_all(FILE *file, const void *data, size_t size) {
    return fwrite(data, 1, size, file) == size;
}

static int read_all(const char *path, unsigned char **data_out, size_t *size_out) {
    FILE *file;
    long length;
    unsigned char *data;

    file = fopen(path, "rb");
    if (!file) return 0;
    if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return 0; }
    length = ftell(file);
    if (length < 2 || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return 0;
    }
    data = (unsigned char *)malloc((size_t)length);
    if (!data || fread(data, 1, (size_t)length, file) != (size_t)length) {
        fclose(file);
        free(data);
        return 0;
    }
    if (fclose(file) != 0) { free(data); return 0; }
    *data_out = data;
    *size_out = (size_t)length;
    return 1;
}

static int read_text(const char *path, char **text_out, size_t *length_out) {
    FILE *file;
    long length;
    char *text;

    file = fopen(path, "rb");
    if (!file) return 0;
    if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return 0; }
    length = ftell(file);
    if (length < 0 || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return 0;
    }
    text = (char *)malloc((size_t)length + 1U);
    if (!text || fread(text, 1, (size_t)length, file) != (size_t)length) {
        fclose(file);
        free(text);
        return 0;
    }
    if (fclose(file) != 0) { free(text); return 0; }
    text[length] = '\0';
    *text_out = text;
    *length_out = (size_t)length;
    return 1;
}

int main(int argc, char **argv) {
    const char *input = NULL;
    const char *output = NULL;
    const char *json = NULL;
    const char prefix[] = "ASCII\0\0\0";
    unsigned char *input_data = NULL;
    unsigned char *app = NULL;
    char *json_text = NULL;
    size_t input_size = 0, json_size = 0, app_size, i;
    FILE *file = NULL;
    unsigned char header[4];
    unsigned segment_length;
    int ok = 0;

    for (i = 1; i < (size_t)argc; i++) {
        if (!strcmp(argv[i], "--in") && i + 1 < (size_t)argc) input = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < (size_t)argc) output = argv[++i];
        else if (!strcmp(argv[i], "--json") && i + 1 < (size_t)argc) json = argv[++i];
        else return 2;
    }
    if (!input || !output || !json || !strcmp(input, output)) return 2;
    if (!read_all(input, &input_data, &input_size) ||
        !read_text(json, &json_text, &json_size)) goto done;
    if (input_data[0] != 0xff || input_data[1] != 0xd8) goto done;

    /* JPEG APP1 length includes its two-byte length field. */
    if (json_size > 65533U - 40U) goto done;
    app_size = 40U + json_size;
    segment_length = (unsigned)app_size + 2U;
    if (segment_length > 65535U) goto done;

    app = (unsigned char *)calloc(1, app_size);
    if (!app) goto done;
    memcpy(app, "Exif\0\0", 6);
    app[6] = 'M'; app[7] = 'M';
    be16(app + 8, 42);
    be32(app + 10, 8);
    be16(app + 14, 1);
    be16(app + 16, 0x9286);             /* UserComment */
    be16(app + 18, 7);                  /* UNDEFINED */
    be32(app + 20, (unsigned)(8U + json_size));
    be32(app + 24, 34);                 /* TIFF-relative offset */
    be32(app + 28, 0);                  /* next IFD */
    memcpy(app + 32, prefix, sizeof(prefix) - 1U);
    memcpy(app + 40, json_text, json_size);

    file = fopen(output, "wb");
    if (!file) goto done;
    header[0] = 0xff; header[1] = 0xe1;
    header[2] = (unsigned char)(segment_length >> 8);
    header[3] = (unsigned char)segment_length;
    ok = write_all(file, input_data, 2) &&
         write_all(file, header, sizeof(header)) &&
         write_all(file, app, app_size) &&
         write_all(file, input_data + 2, input_size - 2U) &&
         fflush(file) == 0 &&
         fsync(fileno(file)) == 0;
    if (fclose(file) != 0) ok = 0;
    file = NULL;
    if (!ok) unlink(output);

done:
    if (file) fclose(file);
    free(input_data);
    free(json_text);
    free(app);
    return ok ? 0 : 3;
}
