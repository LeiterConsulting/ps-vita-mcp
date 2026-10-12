/* Run a supplied script through the actual DevLoop core and Lua sandbox.
 * Controller, clock and rendering samples are deterministic host fixtures.
 * This executable opens no sockets and supplies no physical-device evidence. */
#include "core.h"
#include "sha256.h"
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern unsigned test_draw_calls;
static DevCore core;
static DevCommand command;
static char source[SCRIPT_MAX + 1];
static char error[256];

typedef struct {
    unsigned frame, buttons, lx, ly, rx, ry;
} Event;

static bool read_event(FILE *file, Event *event, bool *present) {
    char line[160], extra;
    if (!fgets(line, sizeof(line), file)) {
        *present = false;
        return !ferror(file);
    }
    if (sscanf(line, "%u %u %u %u %u %u %c", &event->frame, &event->buttons,
               &event->lx, &event->ly, &event->rx, &event->ry, &extra) != 6 ||
        event->buttons > 65535 || event->lx > 255 || event->ly > 255 ||
        event->rx > 255 || event->ry > 255) return false;
    *present = true;
    return true;
}

static bool read_source(const char *path) {
    FILE *file = fopen(path, "rb");
    if (!file) return false;
    size_t count = fread(source, 1, SCRIPT_MAX, file);
    int extra = fgetc(file);
    bool valid = !ferror(file) && count > 0 && extra == EOF;
    if (fclose(file)) valid = false;
    source[count] = 0;
    return valid && strlen(source) == count;
}

static int apply_action(const char *action) {
    memset(&command, 0, sizeof(command));
    command.expected_revision = core.revision;
    snprintf(command.action, sizeof(command.action), "%s", action);
    return dev_apply(&core, &command, error, sizeof(error));
}

int main(int argc, char **argv) {
    if (argc != 6) return 2;
    char *end = NULL;
    errno = 0;
    unsigned long requested = strtoul(argv[2], &end, 10);
    if (errno || !end || *end || requested < 1 || requested > 3600) return 2;
    errno = 0;
    double dt = strtod(argv[3], &end);
    if (errno || !end || *end || !isfinite(dt) || dt <= 0 || dt > .05) return 2;
    if (!read_source(argv[1])) return 2;
    FILE *trace = fopen(argv[4], "rb");
    if (!trace) return 2;
    Event event = {0};
    bool pending = false;
    if (!read_event(trace, &event, &pending)) { fclose(trace); return 2; }

    dev_init(&core);
    World original_world = core.world;
    PhysicsParams original_params = core.params;
    Input input = {0};
    input.lx = input.ly = input.rx = input.ry = 128;
    input.dt = (float)dt;
    input.fps = (float)(1 / dt);
    /* No sensors are simulated by the controller-only fixture. */
    input.motion_result = input.front.read_result = input.back.read_result = -1;
    core.input = input;
    memset(&command, 0, sizeof(command));
    command.script_upload = true;
    command.expected_revision = core.revision;
    memcpy(command.script_source, source, strlen(source) + 1);
    snprintf(command.script_name, sizeof(command.script_name), "host_candidate");
    char digest[65];
    dev_sha256(source, strlen(source), digest);
    memcpy(command.script_sha256, digest, sizeof(digest));
    int load_status = dev_apply(&core, &command, error, sizeof(error));
    char load_error[256];
    snprintf(load_error, sizeof(load_error), "%s", error);
    bool load_paused = load_status == 200 && core.paused;
    bool render_matches = true;
    unsigned frames = 0, max_commands = 0, rendered = 0, old_buttons = 0;
    const char *phase = "load";
    if (load_status == 200) {
        phase = "run";
        if (apply_action("resume") != 200) phase = "resume";
        else for (unsigned n = 0; n < requested; n++) {
            if (pending && event.frame < n) { fclose(trace); script_shutdown(); return 2; }
            if (pending && event.frame == n) {
                input.buttons = event.buttons;
                input.lx = (unsigned char)event.lx;
                input.ly = (unsigned char)event.ly;
                input.rx = (unsigned char)event.rx;
                input.ry = (unsigned char)event.ry;
                unsigned previous = event.frame;
                if (!read_event(trace, &event, &pending) ||
                    (pending && (event.frame <= previous || event.frame >= requested))) {
                    fclose(trace); script_shutdown(); return 2;
                }
            }
            input.pressed = input.buttons & ~old_buttons;
            old_buttons = input.buttons;
            dev_tick(&core, &input, (uint64_t)llround((n + 1) * dt * 1000));
            frames++;
            if (core.script.draw_commands > max_commands) max_commands = core.script.draw_commands;
            test_draw_calls = 0;
            script_render();
            unsigned expected = core.script.faulted ? 0 : core.script.draw_commands;
            if (test_draw_calls != expected) render_matches = false;
            rendered += test_draw_calls;
            if (core.script.faulted) { phase = "runtime_fault"; break; }
        }
    }
    bool trace_valid = !pending && !ferror(trace);
    if (fclose(trace)) trace_valid = false;
    bool world_unchanged = !memcmp(&core.world, &original_world, sizeof(original_world)) &&
                           !memcmp(&core.params, &original_params, sizeof(original_params));
    char runtime[DEV_JSON_MAX], load_json[512];
    dev_script_json(&core, runtime, sizeof(runtime));
    dev_error_json(load_json, sizeof(load_json), load_error);
    FILE *report = fopen(argv[5], "wb");
    if (!report) { script_shutdown(); return 2; }
    int written = fprintf(report,
        "{\"scope\":\"actual_shared_lua_runtime_with_host_fixtures\","
        "\"phase\":\"%s\",\"load_status\":%d,\"load_error\":%s,"
        "\"source_sha256\":\"%s\",\"requested_frames\":%lu,\"observed_frames\":%u,"
        "\"dt\":%.12g,\"draw_calls\":%u,\"max_draw_commands\":%u,"
        "\"invariants\":{\"successful_load_starts_paused\":%s,"
        "\"draw_calls_match_buffered_commands\":%s,\"native_world_unchanged\":%s,"
        "\"trace_consumed\":%s},\"runtime\":%s}\n",
        phase, load_status, load_json, digest, requested, frames, dt, rendered, max_commands,
        load_paused ? "true" : "false", render_matches ? "true" : "false",
        world_unchanged ? "true" : "false", trace_valid ? "true" : "false", runtime);
    bool ok = written > 0;
    if (fclose(report)) ok = false;
    script_shutdown();
    return ok ? 0 : 2;
}
