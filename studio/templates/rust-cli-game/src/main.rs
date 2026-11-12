//! A tiny terminal guessing game using only the Rust standard library, so it
//! builds offline with no crates.io dependencies.

use std::cmp::Ordering;
use std::io::{self, BufRead, Write};
use std::time::{SystemTime, UNIX_EPOCH};

const MAX: u32 = 100;

/// Small xorshift generator; good enough for a game, not for security.
struct Rng(u64);

impl Rng {
    fn new(seed: u64) -> Self {
        Rng(seed | 1)
    }

    fn next_u32(&mut self) -> u32 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        (x >> 32) as u32
    }

    fn range(&mut self, low: u32, high: u32) -> u32 {
        low + self.next_u32() % (high - low + 1)
    }
}

fn judge(guess: u32, secret: u32) -> &'static str {
    match guess.cmp(&secret) {
        Ordering::Less => "higher",
        Ordering::Greater => "lower",
        Ordering::Equal => "correct",
    }
}

fn seed_from_args() -> u64 {
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--seed" {
            if let Some(value) = args.next().and_then(|v| v.parse().ok()) {
                return value;
            }
        }
    }
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0x5eed)
}

fn main() {
    let secret = Rng::new(seed_from_args()).range(1, MAX);
    println!("__XODUS_PROJECT_NAME__: guess a number from 1 to {MAX} (q quits).");
    let stdin = io::stdin();
    let mut tries = 0u32;
    loop {
        print!("> ");
        io::stdout().flush().ok();
        let mut line = String::new();
        if stdin.lock().read_line(&mut line).unwrap_or(0) == 0 {
            break;
        }
        let line = line.trim();
        if line == "q" {
            break;
        }
        let Ok(guess) = line.parse::<u32>() else {
            println!("enter a whole number");
            continue;
        };
        tries += 1;
        match judge(guess, secret) {
            "correct" => {
                println!("correct in {tries} tries!");
                break;
            }
            hint => println!("{hint}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn range_stays_in_bounds() {
        let mut rng = Rng::new(42);
        for _ in 0..1000 {
            let n = rng.range(1, MAX);
            assert!((1..=MAX).contains(&n));
        }
    }

    #[test]
    fn same_seed_same_secret() {
        assert_eq!(Rng::new(7).range(1, MAX), Rng::new(7).range(1, MAX));
    }

    #[test]
    fn judge_gives_direction() {
        assert_eq!(judge(10, 50), "higher");
        assert_eq!(judge(90, 50), "lower");
        assert_eq!(judge(50, 50), "correct");
    }
}
