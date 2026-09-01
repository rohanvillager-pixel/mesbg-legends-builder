#!/usr/bin/env python3
"""Merge Legends of Middle-earth factions into the latest Now For Wrath data."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOM_PATH = ROOT / "custom" / "legends.json"
WATCHFUL_PEACE_PATH = ROOT / "custom" / "watchful-peace.json"
DEFAULT_OUTPUT = ROOT / "data2024-legends.json"
DEFAULT_MANIFEST_OUTPUT = ROOT / "data2024-legends.update.json"
UPSTREAM_DATA_URL = "https://nowforwrath.github.io/data2024.json"
UPSTREAM_MANIFEST_URL = "https://nowforwrath.github.io/data2024.update.json"
DEFAULT_PUBLIC_DATA_URL = (
    "https://raw.githubusercontent.com/rohanvillager-pixel/"
    "mesbg-legends-builder/main/data2024-legends.json"
)
DEFAULT_PUBLIC_MANIFEST_URL = (
    "https://raw.githubusercontent.com/rohanvillager-pixel/"
    "mesbg-legends-builder/main/data2024-legends.update.json"
)


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "mesbg-legends-builder/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def unit_by_name(data: dict, collection: str, name: str) -> dict:
    matches = [unit for unit in data["data"][collection] if unit.get("name") == name]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one {collection} entry named {name!r}, found {len(matches)}"
        )
    return matches[0]


def add_hero_faction(hero: dict, faction_name: str, tier: str) -> None:
    affiliations = hero.setdefault("factions", [])
    if any(
        entry == faction_name or (isinstance(entry, dict) and entry.get("name") == faction_name)
        for entry in affiliations
    ):
        return
    entry = {"name": faction_name, "heroicTier": tier}
    if hero.get("name") == "Elrohir":
        entry["unlockedBy"] = "Elladan"
    affiliations.append(entry)


def add_warrior_faction(warrior: dict, faction_name: str) -> None:
    affiliations = warrior.setdefault("factions", [])
    if faction_name not in affiliations:
        affiliations.append(faction_name)


def add_bonus(data: dict, name: str, definition: str) -> str:
    existing = next(
        (bonus for bonus in data["data"]["armyBonuses"] if bonus.get("name") == name),
        None,
    )
    if existing is None:
        data["data"]["armyBonuses"].append({"name": name, "definition": definition})
        return name
    if existing.get("definition") == definition:
        return name

    legends_name = f"{name} (Legends of Middle-earth)"
    collision = next(
        (
            bonus
            for bonus in data["data"]["armyBonuses"]
            if bonus.get("name") == legends_name
        ),
        None,
    )
    if collision is None:
        data["data"]["armyBonuses"].append(
            {"name": legends_name, "definition": definition}
        )
    elif collision.get("definition") != definition:
        raise ValueError(f"Conflicting army bonus definitions for {name!r}")
    return legends_name


def required_child(data: dict, item: dict) -> dict:
    hero = unit_by_name(data, "heroes", item["name"])
    child = {
        "name": item["name"],
        "points": hero["points"],
        "elementPropertyName": "heroes",
    }
    if item.get("general"):
        child["mustBeLeader"] = True
    return child


def merge(upstream: dict, custom: dict, public_manifest_url: str) -> dict:
    data = copy.deepcopy(upstream)
    toggle = custom["toggle"]

    data["toggles"] = [
        item for item in data.get("toggles", []) if item.get("property") != toggle["property"]
    ]
    data["toggles"].append(toggle)

    custom_names = {faction["name"] for faction in custom["factions"]}
    data["data"]["factions"] = [
        faction
        for faction in data["data"]["factions"]
        if faction.get("name") not in custom_names
        and not faction.get(toggle["property"], False)
    ]

    for faction_spec in custom["factions"]:
        faction_name = faction_spec["name"]
        bonus_names = [
            add_bonus(data, bonus["name"], bonus["definition"])
            for bonus in faction_spec["armyBonuses"]
        ]

        faction = {
            "name": faction_name,
            "alignment": faction_spec["alignment"],
            toggle["property"]: True,
            "badge": "LOM",
            "additionalRules": faction_spec["additionalRules"],
            "armyBonuses": bonus_names,
        }
        if faction_spec.get("required"):
            faction["requiredChildren"] = [
                required_child(data, item) for item in faction_spec["required"]
            ]
        if faction_spec.get("requireOne"):
            faction["requireOne"] = [faction_spec["requireOne"]]

        data["data"]["factions"].append(faction)

        for hero_name, tier in faction_spec["heroes"]:
            add_hero_faction(unit_by_name(data, "heroes", hero_name), faction_name, tier)
        for warrior_name in faction_spec["warriors"]:
            add_warrior_faction(
                unit_by_name(data, "warriors", warrior_name), faction_name
            )

    credit = data.setdefault("credit", [])
    credit.append(
        {
            "type": "text",
            "text": (
                "Custom army lists from Legends of Middle-earth 1.2 by Antonio Andrino. "
            ),
        }
    )

    version = str(data.get("update", {}).get("contentVersion", "upstream"))
    custom_version = custom.get("version", "custom")
    data["update"] = {
        "manifestUrl": public_manifest_url,
        "contentVersion": f"{version}-legends-{custom_version}",
    }
    return data


def validate(data: dict, custom: dict) -> None:
    property_name = custom["toggle"]["property"]
    expected_names = {faction["name"] for faction in custom["factions"]}
    custom_factions = [
        faction
        for faction in data["data"]["factions"]
        if faction.get(property_name) is True
    ]
    actual_names = {faction["name"] for faction in custom_factions}
    if actual_names != expected_names:
        raise ValueError(
            f"Custom faction mismatch: missing={expected_names-actual_names}, "
            f"unexpected={actual_names-expected_names}"
        )
    if len(actual_names) != len(custom_factions):
        raise ValueError("Duplicate custom faction names")

    toggles = [item for item in data["toggles"] if item.get("property") == property_name]
    if toggles != [custom["toggle"]]:
        raise ValueError("Legends toggle missing or duplicated")

    for spec in custom["factions"]:
        faction_name = spec["name"]
        for hero_name, _tier in spec["heroes"]:
            hero = unit_by_name(data, "heroes", hero_name)
            if not any(
                isinstance(entry, dict) and entry.get("name") == faction_name
                for entry in hero.get("factions", [])
            ):
                raise ValueError(f"{hero_name} is not available to {faction_name}")
        for warrior_name in spec["warriors"]:
            warrior = unit_by_name(data, "warriors", warrior_name)
            if faction_name not in warrior.get("factions", []):
                raise ValueError(f"{warrior_name} is not available to {faction_name}")


def merge_watchful_peace(data: dict, custom: dict, public_manifest_url: str) -> dict:
    """Add The Watchful Peace profiles and factions after the Legends layer."""
    data = copy.deepcopy(data)
    toggle = custom["toggle"]
    property_name = toggle["property"]

    data["toggles"] = [
        item for item in data.get("toggles", [])
        if item.get("property") != property_name
    ]
    data["toggles"].append(toggle)

    keyword_names = {item["name"] for item in custom.get("keywords", [])}
    data["data"]["keywords"] = [
        item for item in data["data"]["keywords"]
        if item.get("name") not in keyword_names
    ]
    data["data"]["keywords"].extend(copy.deepcopy(custom.get("keywords", [])))

    magical_power_names = {
        item["name"] for item in custom.get("magicalPowers", [])
    }
    data["data"]["magicalPowers"] = [
        item for item in data["data"]["magicalPowers"]
        if item.get("name") not in magical_power_names
    ]
    data["data"]["magicalPowers"].extend(
        copy.deepcopy(custom.get("magicalPowers", []))
    )

    replacement_names = {
        collection: {item["name"] for item in custom["profiles"].get(collection, [])}
        for collection in ("heroes", "warriors")
    }
    for clone in custom.get("clones", []):
        replacement_names[clone["collection"]].add(clone["name"])

    for collection in ("heroes", "warriors"):
        data["data"][collection] = [
            item for item in data["data"][collection]
            if item.get("name") not in replacement_names[collection]
        ]
        for profile in custom["profiles"].get(collection, []):
            profile = copy.deepcopy(profile)
            profile.setdefault("factions", [])
            data["data"][collection].append(profile)

    for clone_spec in custom.get("clones", []):
        collection = clone_spec["collection"]
        source = copy.deepcopy(
            unit_by_name(data, collection, clone_spec["source"])
        )
        source["name"] = clone_spec["name"]
        source["factions"] = []
        source.update(copy.deepcopy(clone_spec.get("overrides", {})))
        data["data"][collection].append(source)

    for patch in custom.get("patches", []):
        unit = unit_by_name(data, patch["collection"], patch["name"])
        unit.update(copy.deepcopy(patch.get("set", {})))
        unit.setdefault("options", []).extend(copy.deepcopy(patch.get("appendOptions", [])))

    custom_names = {faction["name"] for faction in custom["factions"]}
    data["data"]["factions"] = [
        faction for faction in data["data"]["factions"]
        if faction.get("name") not in custom_names
        and not faction.get(property_name, False)
    ]

    for faction_spec in custom["factions"]:
        faction_name = faction_spec["name"]
        bonus_names = [
            add_bonus(data, bonus["name"], bonus["definition"])
            for bonus in faction_spec["armyBonuses"]
        ]
        faction = {
            "name": faction_name,
            "alignment": faction_spec["alignment"],
            property_name: True,
            "badge": custom["badge"],
            "additionalRules": faction_spec.get("additionalRules", []),
            "armyBonuses": bonus_names,
        }
        if faction_spec.get("required"):
            faction["requiredChildren"] = [
                required_child(data, item) for item in faction_spec["required"]
            ]
        if faction_spec.get("requireOne"):
            faction["requireOne"] = [faction_spec["requireOne"]]
        data["data"]["factions"].append(faction)

        for hero_name, tier in faction_spec["heroes"]:
            add_hero_faction(unit_by_name(data, "heroes", hero_name), faction_name, tier)
        for warrior_name in faction_spec["warriors"]:
            add_warrior_faction(
                unit_by_name(data, "warriors", warrior_name), faction_name
            )

    data.setdefault("credit", []).append(
        {
            "type": "text",
            "text": "Custom profiles and army lists from The Watchful Peace fan-made sourcebook (2025). ",
        }
    )
    prior_version = str(data.get("update", {}).get("contentVersion", "upstream"))
    data["update"] = {
        "manifestUrl": public_manifest_url,
        "contentVersion": f"{prior_version}-twp-{custom.get('version', 'custom')}",
    }
    return data


def validate_watchful_peace(data: dict, custom: dict) -> None:
    property_name = custom["toggle"]["property"]
    expected = {item["name"] for item in custom["factions"]}
    actual = {
        item["name"] for item in data["data"]["factions"]
        if item.get(property_name) is True
    }
    if actual != expected:
        raise ValueError(
            f"Watchful Peace faction mismatch: missing={expected-actual}, "
            f"unexpected={actual-expected}"
        )
    toggles = [
        item for item in data["toggles"]
        if item.get("property") == property_name
    ]
    if toggles != [custom["toggle"]]:
        raise ValueError("Watchful Peace toggle missing or duplicated")
    for spec in custom["factions"]:
        faction_name = spec["name"]
        for hero_name, _tier in spec["heroes"]:
            hero = unit_by_name(data, "heroes", hero_name)
            if not any(
                isinstance(item, dict) and item.get("name") == faction_name
                for item in hero.get("factions", [])
            ):
                raise ValueError(f"{hero_name} is not available to {faction_name}")
        for warrior_name in spec["warriors"]:
            warrior = unit_by_name(data, "warriors", warrior_name)
            if faction_name not in warrior.get("factions", []):
                raise ValueError(f"{warrior_name} is not available to {faction_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    args = parser.parse_args()

    custom = load_json(CUSTOM_PATH)
    watchful_peace = load_json(WATCHFUL_PEACE_PATH)
    upstream = load_json(args.upstream) if args.upstream else fetch_json(UPSTREAM_DATA_URL)
    upstream_manifest = fetch_json(UPSTREAM_MANIFEST_URL)
    public_data_url = os.environ.get("PUBLIC_DATA_URL", DEFAULT_PUBLIC_DATA_URL)
    public_manifest_url = os.environ.get(
        "PUBLIC_MANIFEST_URL", DEFAULT_PUBLIC_MANIFEST_URL
    )

    merged = merge(upstream, custom, public_manifest_url)
    validate(merged, custom)
    merged = merge_watchful_peace(merged, watchful_peace, public_manifest_url)
    validate_watchful_peace(merged, watchful_peace)

    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "contentVersion": merged["update"]["contentVersion"],
        "fileUrl": public_data_url,
        "releasedAt": upstream_manifest.get("releasedAt"),
    }
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Built {args.output.name}: {len(custom['factions'])} Legends factions, "
        f"{len(watchful_peace['factions'])} Watchful Peace factions, "
        f"version {manifest['contentVersion']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Build failed: {error}", file=sys.stderr)
        raise
