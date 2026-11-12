# __XODUS_PROJECT_NAME__

A minimal raylib game in C: a square you move with the arrow keys or WASD.
Escape quits.

## Install the tools

```sh
scripts/xodus-studio-plan.py --profile engines --gpu-vendor intel
```

## Build and run

```sh
cmake -S . -B build -G Ninja
cmake --build build
./build/__XODUS_PROJECT_NAME__
```
