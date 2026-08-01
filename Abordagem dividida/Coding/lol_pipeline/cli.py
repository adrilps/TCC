"""
cli.py - Interactive terminal interface for the LoL SHAP Pipeline.
Run with: py -m lol_pipeline.cli
"""

import os
import sys
from pathlib import Path


# -- Helpers -------------------------------------------------------------------

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header(title: str = "LoL SHAP Pipeline"):
    print(f"\n{'-' * 40}")
    print(f"  {title}")
    print(f"{'-' * 40}")


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    raw = input(f"  {prompt}{hint}: ").strip()
    return raw if raw else default


def select(prompt: str, options: list[tuple[str, str]], allow_multi=False) -> str | list[str]:
    """
    Numbered selection menu.
    options: list of (label, value) pairs.
    Returns value (or list of values if allow_multi).
    """
    print(f"\n  {prompt}")
    for i, (label, _) in enumerate(options, 1):
        print(f"    [{i}] {label}")
    if allow_multi:
        print("    (enter numbers separated by spaces, e.g. 1 2)")

    while True:
        raw = input("  > ").strip()
        if allow_multi:
            parts = raw.split()
            chosen = []
            valid = True
            for p in parts:
                if p.isdigit() and 1 <= int(p) <= len(options):
                    chosen.append(options[int(p) - 1][1])
                else:
                    valid = False
                    break
            if valid and chosen:
                return chosen
        else:
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1][1]
        print(f"  Invalid - enter a number between 1 and {len(options)}.")


def confirm(prompt: str) -> bool:
    raw = input(f"  {prompt} [y/N]: ").strip().lower()
    return raw in ("y", "yes")


# -- Menus ---------------------------------------------------------------------

def menu_run_analysis():
    clear()
    header("Run Analysis")

    # Data source
    source = select("Data source:", [
        ("Existing CSV data", "csv"),
        ("Synthetic data (for testing)", "synthetic"),
    ])

    patch_filter = None
    if source == "csv":
        from lol_pipeline.config import CACHE_DIR
        csv_path = Path(CACHE_DIR) / "matches.csv"
        if not csv_path.exists():
            print("\n  No matches.csv found. Collect data first.")
            input("  Press Enter to go back...")
            return

        import pandas as pd
        df = pd.read_csv(csv_path)
        total = len(df)

        if "patch" in df.columns:
            counts = df["patch"].value_counts().sort_index()
            patch_options = [("All patches", None)] + [
                (f"{p}  ({n} matches)", p) for p, n in counts.items()
            ]
            patch_filter = select(
                f"Filter by patch? ({total} matches total):",
                patch_options,
            )
        else:
            print(f"\n  Loaded {total} matches (no patch column).")

    # Run
    print()
    from lol_pipeline.main import main
    main(source=source, patch=patch_filter)
    print()
    input("  Press Enter to return to the main menu...")


def menu_collect_data():
    clear()
    header("Collect New Data")

    from lol_pipeline.config import (
        SEED_RIOT_ID, REGION, TARGET_TIERS, MAX_MATCHES, MAX_PLAYERS_VISITED
    )

    print()

    # Seed player
    seed = ask("Seed player (gameName#tagLine)", default=SEED_RIOT_ID)
    if "#" not in seed:
        print("  Invalid format - must be gameName#tagLine.")
        input("  Press Enter to go back...")
        return

    # Region
    region_choice = select("Region:", [
        ("Brazil (br1 / americas)", ("br1", "americas")),
        ("North America (na1 / americas)", ("na1", "americas")),
        ("EU West (euw1 / europe)", ("euw1", "europe")),
        ("Korea (kr / asia)", ("kr", "asia")),
    ])
    region, region_routing = region_choice

    # Target tiers
    tier_choices = select(
        "Target rank tier(s):",
        [
            ("Gold", ["GOLD"]),
            ("Platinum", ["PLATINUM"]),
            ("Diamond", ["DIAMOND"]),
            ("Gold + Platinum", ["GOLD", "PLATINUM"]),
        ],
    )
    tiers = set(tier_choices)

    # Max matches
    max_matches_raw = ask("Max matches to collect", default=str(MAX_MATCHES))
    try:
        max_matches = int(max_matches_raw)
    except ValueError:
        print("  Invalid number - using default.")
        max_matches = MAX_MATCHES

    max_players_raw = ask("Max players to visit", default=str(MAX_PLAYERS_VISITED))
    try:
        max_players = int(max_players_raw)
    except ValueError:
        max_players = MAX_PLAYERS_VISITED

    # Target patch
    target_patch = ask("Target patch (e.g. 16.12, blank = any)")

    # API key — prompt then validate with a live request
    api_key = os.getenv("RIOT_API_KEY", "")
    while True:
        if not api_key:
            api_key = ask("RIOT_API_KEY (not saved to disk)")
        if not api_key:
            print("  API key required. Aborting.")
            input("  Press Enter to go back...")
            return

        print("  Validating key...", end=" ", flush=True)
        import requests as _req
        test_url = f"https://{region}.api.riotgames.com/lol/status/v4/platform-data"
        resp = _req.get(test_url, headers={"X-Riot-Token": api_key}, timeout=5)
        if resp.status_code == 200:
            print("OK")
            break
        elif resp.status_code == 401:
            print(f"INVALID (401) - key: {api_key[:12]}...")
            print("  The key was rejected. Paste a fresh one from developer.riotgames.com")
            api_key = ""
        else:
            print(f"unexpected {resp.status_code} - continuing anyway")
            break

    # Summary
    print()
    print("  -- Summary --------------------------")
    print(f"  Seed:        {seed}")
    print(f"  Region:      {region} / {region_routing}")
    print(f"  Tiers:       {', '.join(sorted(tiers))}")
    print(f"  Patch:       {target_patch or 'any'}")
    print(f"  Max matches: {max_matches}")
    print(f"  Max players: {max_players}")
    print()

    if not confirm("Start collecting?"):
        return

    from lol_pipeline.data.spider import run_spider
    try:
        df = run_spider(
            seed=seed,
            region=region,
            region_routing=region_routing,
            tiers=tiers,
            max_matches=max_matches,
            max_players=max_players,
            target_patch=target_patch or None,
            api_key=api_key,
        )
        print(f"\n  Collected {len(df)} matches.")
    except Exception as e:
        print(f"\n  Error: {e}")

    input("  Press Enter to return to the main menu...")


def menu_dataset_info():
    clear()
    header("Dataset Info")

    from lol_pipeline.config import CACHE_DIR
    csv_path = Path(CACHE_DIR) / "matches.csv"

    if not csv_path.exists():
        print("\n  No matches.csv found.")
        input("  Press Enter to go back...")
        return

    import pandas as pd
    df = pd.read_csv(csv_path)

    print(f"\n  File:    {csv_path}")
    print(f"  Matches: {len(df)}")
    print(f"  Wins:    {df['win'].sum()} ({df['win'].mean()*100:.1f}%)")

    if "patch" in df.columns:
        print(f"\n  Patch breakdown:")
        for patch, count in df["patch"].value_counts().sort_index().items():
            print(f"    {patch}: {count} matches")

    if "early_vision_per_min" in df.columns:
        print(f"\n  Vision wards/min (early / mid / late):")
        for phase in ("early", "mid", "late"):
            col = f"{phase}_vision_per_min"
            if col in df.columns:
                m = df[col].mean()
                print(f"    {phase:5}: {m:.3f} avg")

    print()
    input("  Press Enter to go back...")


# -- Main loop -----------------------------------------------------------------

def run():
    while True:
        clear()
        header()
        print()

        choice = select("What would you like to do?", [
            ("Run analysis", "analysis"),
            ("Collect new data (requires Riot API key)", "collect"),
            ("Dataset info", "info"),
            ("Quit", "quit"),
        ])

        if choice == "analysis":
            menu_run_analysis()
        elif choice == "collect":
            menu_collect_data()
        elif choice == "info":
            menu_dataset_info()
        elif choice == "quit":
            print("\n  Bye.\n")
            sys.exit(0)


if __name__ == "__main__":
    run()
