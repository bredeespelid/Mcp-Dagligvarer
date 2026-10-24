"""Lokal handlekurv, lagret som JSON slik at den overlever omstart av serveren."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .catalog import Product

DEFAULT_PATH = Path(os.environ.get("ODA_CART_FILE", Path.home() / ".oda-mcp" / "cart.json"))


class Cart:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self.items: dict[str, dict] = {}
        if self.path.exists():
            self.items = json.loads(self.path.read_text(encoding="utf-8")).get("items", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"items": self.items}, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, product: Product, quantity: int, used_for: list[str] | None = None) -> dict:
        key = str(product.id)
        line = self.items.get(key)
        if line:
            line["quantity"] += quantity
            line["price"] = product.price  # oppdater til gjeldende pris
        else:
            line = {
                "product_id": product.id,
                "name": product.name,
                "details": product.details,
                "price": product.price,
                "quantity": quantity,
                "url": product.url,
                "for": [],
            }
            self.items[key] = line
        line["for"] += [title for title in used_for or [] if title not in line["for"]]
        self._save()
        return line

    def remove(self, product_id: int, quantity: int | None = None) -> dict | None:
        key = str(product_id)
        line = self.items.get(key)
        if not line:
            return None
        if quantity is None or quantity >= line["quantity"]:
            del self.items[key]
            line = {**line, "quantity": 0}
        else:
            line["quantity"] -= quantity
        self._save()
        return line

    def set_price(self, product_id: int, price: float) -> None:
        self.items[str(product_id)]["price"] = price
        self._save()

    def clear(self) -> None:
        self.items = {}
        self._save()

    def summary(self) -> dict:
        lines = [
            {**line, "line_total": round(line["price"] * line["quantity"], 2)}
            for line in self.items.values()
        ]
        return {
            "lines": lines,
            "item_count": sum(line["quantity"] for line in lines),
            "total": round(sum(line["line_total"] for line in lines), 2),
            "currency": "NOK",
        }
