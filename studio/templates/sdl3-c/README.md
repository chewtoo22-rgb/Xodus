# __XODUS_PROJECT_NAME__

A minimal SDL3 program in C: a window, an event loop, and a square you move
with the arrow keys or WASD. Escape or closing the window quits. SDL's
renderer chooses Vulkan, OpenGL or software at runtime; the program logs which
one it picked.

## Install the tools

```sh
scripts/xodus-studio-plan.py --profile graphics --gpu-vendor intel
```

## Build and run

```sh
cmake -S . -B build -G Ninja
cmake --build build
./build/__XODUS_PROJECT_NAME__
```

Force the Vulkan backend to test the GPU path:

```sh
SDL_RENDER_DRIVER=vulkan ./build/__XODUS_PROJECT_NAME__
```
