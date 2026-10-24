"""Rangering av middagsoppskrifter etter hva som er på tilbud akkurat nå."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import catalog

RECIPE_CACHE_SECONDS = 3600
_recipe_cache: dict[tuple[int, int], tuple[float, dict]] = {}


def estimated_saving(product: dict, packages: int) -> tuple[float, int]:
    """Beregnet besparelse i kroner, og hvor mange pakker tilbudet krever.

    Prisrabatt gir eksakt besparelse. For flerkjøp («2 for 64 kr», «3 for 2») er det
    besparelsen per pakke dersom man kjøper hele tilbudet.
    """
    price = product["price"]
    if product.get("original_price"):
        return (product["original_price"] - price) * packages, packages
    offer = (product.get("offer") or "").replace("\xa0", " ").lower()
    if m := re.match(r"(\d+) for (\d+(?:[.,]\d+)?) kr", offer):
        n, total = int(m[1]), float(m[2].replace(",", "."))
        return max(0.0, price - total / n) * max(packages, n), max(packages, n)
    if m := re.match(r"(\d+) for (\d+)$", offer):
        n, paid = int(m[1]), int(m[2])
        return price * (n - paid) / n * max(packages, n), max(packages, n)
    if m := re.search(r"kjøp (\d+), få (\d+)\s*%", offer):
        n, pct = int(m[1]), int(m[2])
        return price * pct / 100 * max(packages, n), max(packages, n)
    return 0.0, packages


def _recipe(recipe_id: int, portions: int) -> dict:
    key = (recipe_id, portions)
    cached = _recipe_cache.get(key)
    if cached and time.monotonic() - cached[0] < RECIPE_CACHE_SECONDS:
        return cached[1]
    recipe = catalog.get_recipe(recipe_id, portions)
    _recipe_cache[key] = (time.monotonic(), recipe)
    return recipe


def score_recipe(recipe: dict) -> dict | None:
    """Sammendrag av pris og tilbud for en oppskrift, eller None uten tilbud."""
    lines = [i for i in recipe["ingredients"] if i["product"] and not i["is_basic"]]
    if not lines:
        return None
    total = sum(i["product"]["price"] * i["packages"] for i in lines)
    portion_cost = sum(i["product"]["price"] * i["package_share"] for i in lines) / recipe["portions"]
    main = max(lines, key=lambda i: i["product"]["price"] * i["packages"])
    offered, direct, extra = [], 0.0, 0.0
    main_on_offer = False
    for i in lines:
        product = i["product"]
        if not product["on_offer"]:
            continue
        kr, needed = estimated_saving(product, i["packages"])
        if needed > i["packages"]:
            extra += kr
        else:
            direct += kr
            main_on_offer = main_on_offer or (i is main and kr > 0)
        offered.append({
            "ingredient": i["ingredient"],
            "product": product["name"],
            "offer": product["offer"],
            "price": product["price"],
            "saving": round(kr, 2),
            "packages_needed_for_offer": needed if needed > i["packages"] else None,
        })
    if not offered:
        return None
    return {
        "id": recipe["id"],
        "title": recipe["title"],
        "url": recipe["url"],
        "cooking_time": recipe["cooking_time"],
        "difficulty": recipe["difficulty"],
        "portions": recipe["portions"],
        "estimated_total": round(total, 2),
        "estimated_cost_per_portion": round(portion_cost, 2),
        "estimated_saving": round(direct, 2),
        "extra_saving_if_buying_full_offers": round(extra, 2),
        "main_ingredient": main["ingredient"],
        "main_ingredient_on_offer": main_on_offer,
        "offers": offered,
    }


def dinners_from_offers(query: str = "middag", portions: int = 4, pages: int = 4,
                        exclude: list[str] | None = None) -> list[dict]:
    """Finn oppskrifter og ranger dem etter beregnet besparelse fra dagens tilbud.

    Oppskrifter der hovedråvaren (den dyreste ingrediensen) er på tilbud uten at man
    må kjøpe ekstra, rangeres først. Deretter sorteres det etter besparelse, der
    besparelse som krever flerkjøp teller halvt.
    """
    ids: list[int] = []
    for page in range(1, pages + 1):
        has_more, recipes = catalog.search_recipes(query, page=page)
        ids += [r["id"] for r in recipes if r["id"] not in ids]
        if not has_more:
            break
    with ThreadPoolExecutor(max_workers=8) as pool:
        recipes = list(pool.map(lambda rid: _recipe(rid, portions), ids))

    banned = [w.lower() for w in exclude or []]
    results = []
    for recipe in recipes:
        text = " ".join([recipe["title"] or ""] + [i["ingredient"] or "" for i in recipe["ingredients"]]).lower()
        if any(word in text for word in banned):
            continue
        if scored := score_recipe(recipe):
            results.append(scored)
    results.sort(
        key=lambda r: (r["main_ingredient_on_offer"],
                       r["estimated_saving"] + 0.5 * r["extra_saving_if_buying_full_offers"]),
        reverse=True,
    )
    return results
