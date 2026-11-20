/* Exercise the theme with Plymouth's actual script parser, event callbacks,
 * Math/String libraries and PNG/text image decoder. Window/Sprite methods
 * record layout without requiring a DRM device or changing the host theme.
 * This is an optional Linux maintainer check against the installed script.so;
 * these plugin-private exported entry points are intentionally loaded at run
 * time, so an incompatible interpreter fails instead of silently skipping.
 *
 * cc -O2 -Wall -Wextra qa/plymouth-script-contract.c -ldl -lm -o /tmp/boot-check
 * /tmp/boot-check /usr/lib/plymouth/script.so overlay/identity/boot
 */
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { void *user_data, *global, *local, *this_object; } State;
typedef struct { int type; void *object; } Result;
static void *(*parse_string)(const char *, const char *);
static void *(*parse_file)(const char *);
static Result (*execute)(State *, void *);
static double (*number)(void *, const char *);
static void *(*element)(void *, const char *);
static void (*unref)(void *);

static void *symbol(void *library, const char *name) {
    void *value = dlsym(library, name);
    if (!value) { fprintf(stderr, "missing Plymouth interpreter API: %s\n", name); exit(1); }
    return value;
}

static void run(State *state, const char *source) {
    void *op = parse_string(source, "Xodus layout contract");
    if (!op) { fprintf(stderr, "Plymouth could not parse layout contract\n"); exit(1); }
    Result result = execute(state, op);
    if (result.type == 2) { fprintf(stderr, "Plymouth layout contract execution failed\n"); exit(1); }
    if (result.object) unref(result.object);
}

static void expect(State *state, const char *name, double expected) {
    double value = number(state->global, name);
    if (!isfinite(value) || fabs(value - expected) > 0.01) {
        fprintf(stderr, "%s: wanted %.2f, got %.2f\n", name, expected, value);
        exit(1);
    }
}

static const char *viewport =
    "mock_width=640; mock_height=480; Window.GetWidth=fun(){return mock_width;};"
    "Window.GetHeight=fun(){return mock_height;}; Window.GetX=fun(){return 0;};"
    "Window.GetY=fun(){return 0;}; Window.SetBackgroundTopColor=fun(r,g,b){};"
    "Window.SetBackgroundBottomColor=fun(r,g,b){};"
    "Sprite=fun(){local.sprite; sprite.opacity=1; sprite.x=0; sprite.y=0; sprite.z=0;"
    "sprite.SetImage=fun(image){this.image=image;};"
    "sprite.SetPosition=fun(x,y,z){this.x=x;this.y=y;this.z=z;};"
    "sprite.SetZ=fun(z){this.z=z;};sprite.SetOpacity=fun(opacity){this.opacity=opacity;};"
    "return sprite;};";

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: %s <Plymouth script.so> <boot source directory>\n", argv[0]); return 64; }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_GLOBAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    State *(*new_state)(void *) = symbol(library, "script_state_new");
    void *(*image_setup)(State *, char *) = symbol(library, "script_lib_image_setup");
    void *(*math_setup)(State *) = symbol(library, "script_lib_math_setup");
    void *(*string_setup)(State *) = symbol(library, "script_lib_string_setup");
    void *(*plymouth_setup)(State *, int, int, void *) = symbol(library, "script_lib_plymouth_setup");
    void (*refresh)(State *, void *) = symbol(library, "script_lib_plymouth_on_refresh");
    void (*password)(State *, void *, const char *, int) = symbol(library, "script_lib_plymouth_on_display_password");
    void (*question)(State *, void *, const char *, const char *) = symbol(library, "script_lib_plymouth_on_display_question");
    void (*normal)(State *, void *) = symbol(library, "script_lib_plymouth_on_display_normal");
    void (*message)(State *, void *, const char *) = symbol(library, "script_lib_plymouth_on_display_message");
    void (*hide_message)(State *, void *, const char *) = symbol(library, "script_lib_plymouth_on_hide_message");
    parse_string = symbol(library, "script_parse_string");
    parse_file = symbol(library, "script_parse_file");
    execute = symbol(library, "script_execute");
    number = symbol(library, "script_obj_hash_get_number");
    element = symbol(library, "script_obj_hash_get_element");
    unref = symbol(library, "script_obj_unref");
    State *state = new_state(NULL);
    char images[4096], filename[4096];
    snprintf(images, sizeof(images), "%s/assets/plymouth", argv[2]);
    snprintf(filename, sizeof(filename), "%s/xodus.script", argv[2]);
    image_setup(state, images);
    math_setup(state);
    string_setup(state);
    void *plymouth = plymouth_setup(state, 0, 50, NULL);
    run(state, viewport);
    void *op = parse_file(filename);
    if (!op) { fprintf(stderr, "Plymouth could not parse Xodus theme\n"); return 1; }
    Result result = execute(state, op);
    if (result.type == 2) { fprintf(stderr, "Plymouth theme execution failed\n"); return 1; }
    if (result.object) unref(result.object);
    run(state, "observed_width=film.image.GetWidth(); observed_height=film.image.GetHeight(); observed_y=film.y;");
    expect(state, "observed_width", 640);
    expect(state, "observed_height", 360);
    expect(state, "observed_y", 60);
    for (int i = 0; i < 300; i++) refresh(state, plymouth);
    expect(state, "frame_index", 240);
    expect(state, "last_index", 240);
    run(state, "mock_width=1024; mock_height=768;");
    refresh(state, plymouth);
    run(state, "observed_width=film.image.GetWidth(); observed_height=film.image.GetHeight(); observed_y=film.y;");
    expect(state, "observed_width", 1024);
    expect(state, "observed_height", 576);
    expect(state, "observed_y", 96);
    password(state, plymouth, "Unlock Xodus disk", 4);
    void *film = element(state->global, "film");
    expect(state, "frame_index", 240);
    if (number(film, "opacity") != 0) { fprintf(stderr, "film hides password prompt\n"); return 1; }
    question(state, plymouth, "Enter Xodus recovery response", "");
    run(state, "entry_width=entry_sprite.image.GetWidth(); entry_height=entry_sprite.image.GetHeight();");
    if (number(state->global, "entry_width") < 1 || number(state->global, "entry_height") < 1) {
        fprintf(stderr, "empty question response did not produce a visible input marker\n"); return 1;
    }
    normal(state, plymouth);
    if (number(film, "opacity") != 1) { fprintf(stderr, "film did not resume after prompt\n"); return 1; }
    message(state, plymouth, "Xodus startup message");
    void *notification = element(state->global, "message_sprite");
    if (number(notification, "opacity") != 1) { fprintf(stderr, "message did not display\n"); return 1; }
    hide_message(state, plymouth, "Xodus startup message");
    if (number(notification, "opacity") != 0) { fprintf(stderr, "message did not clear\n"); return 1; }
    puts("PASS: native Plymouth parser, 241 PNG frames, aspect/resize/final hold, password/question/message callbacks");
    return 0;
}
