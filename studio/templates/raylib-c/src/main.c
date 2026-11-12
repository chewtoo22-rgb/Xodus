/* Move the square with the arrow keys or WASD; Escape quits. */
#include "raylib.h"

#define WIDTH 640
#define HEIGHT 360
#define SIZE 32.0f
#define SPEED 260.0f

static float clampf(float value, float low, float high) {
    return value < low ? low : (value > high ? high : value);
}

int main(void) {
    InitWindow(WIDTH, HEIGHT, "__XODUS_PROJECT_NAME__");
    SetTargetFPS(60);

    Vector2 player = {(WIDTH - SIZE) / 2.0f, (HEIGHT - SIZE) / 2.0f};

    while (!WindowShouldClose()) {
        float dt = GetFrameTime();
        float dx = (float)((IsKeyDown(KEY_RIGHT) || IsKeyDown(KEY_D)) - (IsKeyDown(KEY_LEFT) || IsKeyDown(KEY_A)));
        float dy = (float)((IsKeyDown(KEY_DOWN) || IsKeyDown(KEY_S)) - (IsKeyDown(KEY_UP) || IsKeyDown(KEY_W)));
        if (dx != 0.0f && dy != 0.0f) {
            dx *= 0.7071f;
            dy *= 0.7071f;
        }
        player.x = clampf(player.x + dx * SPEED * dt, 0.0f, WIDTH - SIZE);
        player.y = clampf(player.y + dy * SPEED * dt, 0.0f, HEIGHT - SIZE);

        BeginDrawing();
        ClearBackground((Color){20, 23, 31, 255});
        DrawRectangleV(player, (Vector2){SIZE, SIZE}, (Color){92, 199, 255, 255});
        DrawText("Arrow keys / WASD to move, Esc to quit", 12, 12, 20, RAYWHITE);
        EndDrawing();
    }

    CloseWindow();
    return 0;
}
