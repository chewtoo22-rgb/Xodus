/* SDL3 window + event loop. Move the square with the arrow keys or WASD;
 * Escape or closing the window quits. SDL picks the render backend (Vulkan,
 * OpenGL or software) at runtime. */
#include <SDL3/SDL.h>
#include <stdbool.h>

#define WIDTH 640
#define HEIGHT 360
#define SIZE 32.0f
#define SPEED 260.0f

static float clampf(float value, float low, float high) {
    return value < low ? low : (value > high ? high : value);
}

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        SDL_Log("SDL_Init failed: %s", SDL_GetError());
        return 1;
    }
    SDL_Window *window = NULL;
    SDL_Renderer *renderer = NULL;
    if (!SDL_CreateWindowAndRenderer("__XODUS_PROJECT_NAME__", WIDTH, HEIGHT, 0, &window, &renderer)) {
        SDL_Log("window/renderer creation failed: %s", SDL_GetError());
        SDL_Quit();
        return 1;
    }
    SDL_SetRenderVSync(renderer, 1);
    SDL_Log("renderer: %s", SDL_GetRendererName(renderer));

    SDL_FRect player = {(WIDTH - SIZE) / 2.0f, (HEIGHT - SIZE) / 2.0f, SIZE, SIZE};
    Uint64 last = SDL_GetTicksNS();
    bool running = true;

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) {
                running = false;
            } else if (event.type == SDL_EVENT_KEY_DOWN && event.key.key == SDLK_ESCAPE) {
                running = false;
            }
        }

        Uint64 now = SDL_GetTicksNS();
        float dt = (float)(now - last) / 1e9f;
        last = now;

        const bool *keys = SDL_GetKeyboardState(NULL);
        float dx = (float)((keys[SDL_SCANCODE_RIGHT] || keys[SDL_SCANCODE_D]) -
                           (keys[SDL_SCANCODE_LEFT] || keys[SDL_SCANCODE_A]));
        float dy = (float)((keys[SDL_SCANCODE_DOWN] || keys[SDL_SCANCODE_S]) -
                           (keys[SDL_SCANCODE_UP] || keys[SDL_SCANCODE_W]));
        if (dx != 0.0f && dy != 0.0f) {
            dx *= 0.7071f;
            dy *= 0.7071f;
        }
        player.x = clampf(player.x + dx * SPEED * dt, 0.0f, WIDTH - SIZE);
        player.y = clampf(player.y + dy * SPEED * dt, 0.0f, HEIGHT - SIZE);

        SDL_SetRenderDrawColor(renderer, 20, 23, 31, 255);
        SDL_RenderClear(renderer);
        SDL_SetRenderDrawColor(renderer, 92, 199, 255, 255);
        SDL_RenderFillRect(renderer, &player);
        SDL_RenderPresent(renderer);
    }

    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
