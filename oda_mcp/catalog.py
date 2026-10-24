"""Klient for Odas produkt- og oppskriftskatalog (oda.com/api/v1)."""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

BASE_URL = os.environ.get("ODA_API_URL", "https://oda.com/api/v1")
WEB_URL = "https://oda.com"
TIMEOUT = 15


@dataclass
class Product:
    id: int
    name: str
    details: str
    brand: str | None
    price: float
    unit_price: float | None
    unit: str | None
    on_offer: bool
    offer: str | None
    original_price: float | None
    available: bool
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    if params:
        url += f"?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "oda-mcp/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_product(p: dict) -> Product:
    availability = p.get("availability") or {}
    discount = p.get("discount") or {}
    on_offer = bool(discount.get("is_discounted"))
    price = _float(p.get("gross_price")) or 0.0
    original = _float(discount.get("undiscounted_gross_price"))
    return Product(
        id=int(p["id"]),
        name=p.get("full_name") or p.get("name") or "",
        details=p.get("name_extra") or "",
        brand=p.get("brand"),
        price=price,
        unit_price=_float(p.get("gross_unit_price")),
        unit=p.get("unit_price_quantity_abbreviation"),
        on_offer=on_offer,
        offer=(p.get("promotion") or {}).get("title") if on_offer else None,
        original_price=original if on_offer and original and original > price else None,
        available=bool(availability.get("is_available", True)),
        url=p.get("front_url") or f"{WEB_URL}{p.get('absolute_url', '')}",
    )


def search_products(query: str, page: int = 1) -> tuple[int, list[Product]]:
    """Søk etter varer. Returnerer (totalt antall treff, varer på siden)."""
    data = _get("/search/mixed/", {"q": query, "type": "product", "page": page})
    request_types = data.get("attributes", {}).get("request_types") or [{}]
    total = int(request_types[0].get("count") or 0)
    products = [parse_product(i["attributes"]) for i in data.get("items", []) if i.get("type") == "product"]
    return total, products


_offer_cache: tuple[float, list[Product]] | None = None
OFFER_CACHE_SECONDS = 3600
MAX_OFFER_PAGES = 30


def all_offers() -> list[Product]:
    """Hele Odas tilbudsliste, mellomlagret i en time."""
    global _offer_cache
    if _offer_cache and time.monotonic() - _offer_cache[0] < OFFER_CACHE_SECONDS:
        return _offer_cache[1]
    offers: dict[int, Product] = {}
    for page in range(1, MAX_OFFER_PAGES + 1):
        data = _get("/search/mixed/", {"q": "tilbud", "type": "product", "page": page})
        for item in data.get("items", []):
            if item.get("type") == "product":
                product = parse_product(item["attributes"])
                if product.on_offer and product.available:
                    offers[product.id] = product
        if not data.get("attributes", {}).get("has_more_items"):
            break
    _offer_cache = (time.monotonic(), list(offers.values()))
    return _offer_cache[1]


def find_offers(query: str | None = None) -> list[Product]:
    """Varer på tilbud, eventuelt bare de der navnet inneholder ett av søkeordene."""
    offers = all_offers()
    words = [w for w in re.split(r"[\s,]+", (query or "").lower()) if w]
    if not words:
        return list(offers)
    return [p for p in offers if any(w in f"{p.name} {p.details}".lower() for w in words)]


def get_product(product_id: int) -> Product:
    return parse_product(_get(f"/products/{product_id}/"))


def search_recipes(query: str, page: int = 1) -> tuple[bool, list[dict]]:
    """Søk etter oppskrifter. Returnerer (flere sider finnes, oppskrifter)."""
    data = _get("/search/mixed/", {"q": query, "type": "recipe", "page": page})
    recipes = []
    for item in data.get("items", []):
        if item.get("type") != "recipe":
            continue
        a = item["attributes"]
        recipes.append({
            "id": a["id"],
            "title": a.get("title"),
            "difficulty": a.get("difficulty_string"),
            "cooking_time": a.get("cooking_duration_string"),
            "likes": a.get("like_count"),
            "url": f"{WEB_URL}{a.get('front_url', '')}",
        })
    return bool(data.get("attributes", {}).get("has_more_items")), recipes


def get_recipe(recipe_id: int, portions: int | None = None) -> dict:
    """Hent en oppskrift med ingredienser og hvilke Oda-varer som trengs for antall porsjoner.

    Oda oppgir for hver ingrediens hvor stor andel av varens pakning én porsjon bruker
    (portion_quantity), så antall pakninger er andel × porsjoner rundet opp.
    """
    r = _get(f"/recipes/{recipe_id}/")
    portions = portions or int(r.get("default_num_portions") or 4)
    ingredients = []
    for ing in r.get("ingredients", []):
        share = _float(ing.get("portion_quantity")) or 0.0
        product = ing.get("product")
        ingredients.append({
            "ingredient": (ing.get("ingredient") or {}).get("title"),
            "is_basic": bool(ing.get("is_basic")),
            "package_share": round(share * portions, 3),
            "packages": max(1, math.ceil(share * portions - 1e-9)) if product else 0,
            "product": parse_product(product).to_dict() if product else None,
        })
    display = {
        d["id"]: f"{_float(d.get('display_quantity')) or ''} {d.get('display_unit') or ''}".strip()
        for d in r.get("ingredients_display_list", [])
    }
    for ing, raw in zip(ingredients, r.get("ingredients", [])):
        ing["amount_for_default_portions"] = display.get(raw.get("id"))
    return {
        "id": r["id"],
        "title": r.get("title"),
        "lead": r.get("lead"),
        "portions": portions,
        "default_portions": r.get("default_num_portions"),
        "cooking_time": r.get("cooking_duration_string"),
        "difficulty": r.get("difficulty_string"),
        "tags": [t.get("title") for t in r.get("tags", [])],
        "url": f"{WEB_URL}{r.get('front_url', '')}",
        "ingredients": ingredients,
        "instructions": [s.get("text") for s in (r.get("instructions") or {}).get("instructions", [])],
    }
