# __XODUS_PROJECT_NAME__

A minimal LÖVE 11 game: a square you move with the arrow keys or WASD.
Escape quits.

## Install the tools

```sh
scripts/xodus-studio-plan.py --profile engines --gpu-vendor intel
```

## Run

```sh
love .
```

## Syntax check (what CI runs)

LÖVE runs on LuaJIT, which Arch installs as a dependency of `love`:

```sh
luajit -bl conf.lua >/dev/null
luajit -bl main.lua >/dev/null
```
