# __XODUS_PROJECT_NAME__

A tiny terminal guessing game in Rust. It uses only the standard library, so it
builds offline with no crates.io dependencies.

## Install the tools

```sh
scripts/xodus-studio-plan.py --profile toolchain
```

## Build, test and run

```sh
cargo build --offline
cargo test --offline
cargo run --offline -- --seed 42
```
