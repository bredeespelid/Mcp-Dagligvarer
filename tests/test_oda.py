from unittest.mock import patch

from oda_mcp import catalog
from oda_mcp.cart import Cart

PRODUCT = {
    "id": 63590,
    "full_name": "Vår Laveste Pris Kjøttdeig av storfe 14%",
    "name_extra": "14%, 400 g",
    "gross_price": "72.90",
    "gross_unit_price": "182.25",
    "unit_price_quantity_abbreviation": "kg",
    "availability": {"is_available": True},
    "front_url": "https://oda.com/no/products/63590-kjottdeig/",
}


def test_parse_product():
    p = catalog.parse_product(PRODUCT)
    assert p.id == 63590
    assert p.price == 72.9
    assert p.available


def test_parse_discount():
    p = catalog.parse_product({
        **PRODUCT,
        "gross_price": "34.00",
        "discount": {"is_discounted": True, "undiscounted_gross_price": "42.50"},
        "promotion": {"title": "-20%"},
    })
    assert p.on_offer and p.offer == "-20%" and p.original_price == 42.5

    bargain = catalog.parse_product({**PRODUCT, "promotion": {"title": "Godt kjøp"}})
    assert not bargain.on_offer and bargain.offer is None


def test_cart_add_remove_persist(tmp_path):
    path = tmp_path / "cart.json"
    cart = Cart(path)
    product = catalog.parse_product(PRODUCT)
    cart.add(product, 2, used_for=["Taco"])
    cart.add(product, 1, used_for=["Taco", "Lasagne"])
    assert cart.summary()["item_count"] == 3
    assert cart.summary()["total"] == 218.7
    assert Cart(path).items["63590"]["for"] == ["Taco", "Lasagne"]

    cart.remove(product.id, 1)
    assert cart.summary()["item_count"] == 2
    cart.remove(product.id)
    assert cart.summary()["lines"] == []


def test_recipe_packages_round_up():
    recipe = {
        "id": 1,
        "title": "Taco",
        "default_num_portions": 4,
        "ingredients": [
            {"id": 10, "ingredient": {"title": "Kjøttdeig"}, "is_basic": False,
             "portion_quantity": "0.300", "product": PRODUCT},
            {"id": 11, "ingredient": {"title": "Salt"}, "is_basic": True,
             "portion_quantity": "0.010", "product": PRODUCT},
        ],
        "ingredients_display_list": [],
    }
    with patch.object(catalog, "_get", return_value=recipe):
        r = catalog.get_recipe(1, portions=4)
    assert r["ingredients"][0]["packages"] == 2  # 0.3 × 4 = 1.2 → 2 pakker
    assert r["ingredients"][1]["packages"] == 1
