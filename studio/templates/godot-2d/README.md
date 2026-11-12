# __XODUS_PROJECT_NAME__

A minimal Godot 4 2D project: a rectangle you move with the arrow keys (or a
gamepad stick). Escape quits.

## Install the tools

```sh
scripts/xodus-studio-plan.py --profile engines --gpu-vendor intel
```

## Run

```sh
godot --path .            # run the main scene
godot --editor --path .   # open the editor
```

## Headless check (what CI runs)

```sh
godot --headless --path . --import
godot --headless --path . --check-only --script res://main.gd
```
