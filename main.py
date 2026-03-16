"""Entry point: load the mission file and print a summary."""

from pathlib import Path

from loader import MissionLoader
from models import KillEvent, HitEvent, VehicleEntity


DATA_FILE = Path(__file__).parent / "2026_03_08__21_33_RandomPatrolGenerator.json.gz"


def main() -> None:
    print(f"Loading {DATA_FILE.name} ...")
    mission = MissionLoader.load(DATA_FILE)
    print()

    # --- Mission overview ---
    print(mission)
    print()

    # --- Time span ---
    if mission.times:
        t0 = mission.times[0]
        t1 = mission.times[-1]
        print(f"Game time : {t0.date}  ->  {t1.date}")
        print(f"Real time : {t0.system_time_utc}  ->  {t1.system_time_utc}")
        print(f"Duration  : {mission.duration_seconds:.0f}s in-game")
        print()

    # --- Players ---
    print("=== Players ===")
    for p in mission.players:
        kills = mission.kills_by(p.id)
        deaths = mission.deaths_of(p.id)
        hits_dealt = [h for h in mission.hits if h.attacker_id == p.id]
        death_str = f"frame {deaths[0].frame}" if deaths else "survived"
        print(
            f"  {p.name:<25} role={p.role or 'N/A':<20} "
            f"kills={len(kills):>3}  hits_dealt={len(hits_dealt):>3}  "
            f"shots={p.total_shots:>4}  death={death_str}"
        )
    print()

    # --- Kill feed (first 20) ---
    print("=== Kill Feed (first 20) ===")
    for k in mission.kills[:20]:
        attacker = mission.get_entity(k.attacker_id)
        victim = mission.get_entity(k.victim_id)
        a_name = attacker.name if attacker else f"#{k.attacker_id}"
        v_name = victim.name if victim else f"#{k.victim_id}"
        print(f"  frame {k.frame:>4}: {a_name} -> {v_name}  [{k.weapon}] ({k.distance:.0f}m)")
    print()

    # --- Vehicles ---
    vehicles = [e for e in mission.entities.values() if isinstance(e, VehicleEntity)]
    print(f"=== Vehicles ({len(vehicles)}) ===")
    for v in vehicles:
        print(f"  {v}")
    print()

    # --- Weapon breakdown (top 10) ---
    weapon_kills: dict[str, int] = {}
    for k in mission.kills:
        w = k.weapon or "Unknown"
        weapon_kills[w] = weapon_kills.get(w, 0) + 1
    print("=== Top Weapons by Kills ===")
    for weapon, count in sorted(weapon_kills.items(), key=lambda x: -x[1])[:10]:
        print(f"  {count:>3}x  {weapon}")


if __name__ == "__main__":
    main()
