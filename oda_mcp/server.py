"""MCP-server for å planlegge måltider og handle varer hos Oda."""

from __future__ import annotations

import math

from mcp.server.mcpserver import MCPServer

from . import catalog, offers
from .account import OdaAccount, OdaAccountError
from .cart import Cart

mcp = MCPServer(
    name="oda",
    instructions=(
        "Varer, priser, tilbud og oppskrifter fra Oda (oda.com). Bruk dinners_from_offers "
        "for middager basert på tilbud, find_offers for tilbud på varer, og search_products og "
        "add_to_cart for enkeltvarer, og search_recipes, get_recipe og add_recipes for "
        "måltider. Handlekurven er lokal til checkout kalles. Med send_to_oda=true "
        "overføres den til brukerens egen Oda-kurv, der levering og betaling velges i "
        "Oda-appen. Oppgi alltid priser i kroner.\n\n"
        "Når brukeren ber om noe åpent som 'middag for tre dager', 'frokost til helgen' "
        "eller 'handle til taco', følg arbeidsflyten i prompten plan_meals: still "
        "oppfølgingsspørsmål, foreslå oppskrifter, få dem godkjent, og legg så alt i "
        "kurven med add_recipes."
    ),
)
cart = Cart()
account = OdaAccount()


@mcp.tool()
def search_products(query: str, page: int = 1, only_offers: bool = False) -> dict:
    """Søk etter varer hos Oda (f.eks. 'helmelk', 'kjøttdeig', 'laks').

    Args:
        query: Søkeord.
        page: Sidenummer, starter på 1.
        only_offers: Vis bare varer som er på tilbud.
    """
    if only_offers:
        products = catalog.find_offers(query)
        return {"total": len(products), "products": [p.to_dict() for p in products]}
    total, products = catalog.search_products(query, page=max(1, page))
    return {"total": total, "page": page, "products": [p.to_dict() for p in products]}


@mcp.tool()
def find_offers(query: str | None = None, limit: int = 40) -> dict:
    """Finn varer på tilbud hos Oda, sortert etter størst prosentvis rabatt.

    Args:
        query: Ett eller flere ord som må finnes i varenavnet, f.eks. 'kylling',
            'laks torsk' eller 'kjøttdeig svin biff'. Bruk konkrete ord, siden et
            samlebegrep som 'kjøtt' ikke treffer 'kyllingfilet'. Uten søkeord
            vises alle tilbud.
        limit: Maks antall tilbud i svaret.
    """
    offers = catalog.find_offers(query)

    def saving(p: catalog.Product) -> float:
        return 1 - p.price / p.original_price if p.original_price else 0.0

    offers.sort(key=saving, reverse=True)
    return {
        "count": len(offers),
        "offers": [
            {**p.to_dict(), "saving_percent": round(saving(p) * 100) if p.original_price else None}
            for p in offers[: max(1, limit)]
        ],
    }


@mcp.tool()
def get_product(product_id: int) -> dict:
    """Hent detaljer og pris for én vare."""
    return catalog.get_product(product_id).to_dict()


@mcp.tool()
def dinners_from_offers(query: str = "middag", portions: int = 4, count: int = 8,
                        exclude: list[str] | None = None) -> dict:
    """Foreslå middager som blir billige på grunn av det som er på tilbud hos Oda nå.

    Går gjennom opptil 120 oppskrifter og rangerer dem etter beregnet besparelse.
    Retter der hovedråvaren (den dyreste ingrediensen) er på tilbud kommer først.
    estimated_saving er det man sparer på mengdene oppskriften trenger.
    extra_saving_if_buying_full_offers er det man i tillegg sparer ved å kjøpe hele
    flerkjøpstilbud («2 for 64 kr», «3 for 2»). Antall pakker står i
    packages_needed_for_offer. Oppgi begge tydelig til brukeren.

    Args:
        query: Type oppskrifter, f.eks. 'middag', 'kylling', 'fisk', 'vegetar', 'pasta'.
        portions: Porsjoner per middag.
        count: Antall forslag.
        exclude: Ord som utelukker en rett, f.eks. allergier eller ting de ikke
            spiser: ['nøtter', 'sopp', 'svin'].
    """
    ideas = offers.dinners_from_offers(query, portions=max(1, portions), exclude=exclude)
    return {"count": len(ideas), "dinners": ideas[: max(1, count)]}


@mcp.tool()
def search_recipes(query: str, page: int = 1) -> dict:
    """Søk etter oppskrifter hos Oda (f.eks. 'middag', 'kylling', 'vegetar', 'taco')."""
    has_more, recipes = catalog.search_recipes(query, page=max(1, page))
    return {"page": page, "has_more": has_more, "recipes": recipes}


@mcp.tool()
def get_recipe(recipe_id: int, portions: int | None = None) -> dict:
    """Hent en oppskrift med ingredienser, fremgangsmåte og varene som trengs.

    Args:
        recipe_id: ID fra search_recipes.
        portions: Antall porsjoner. Standard er oppskriftens eget antall.
    """
    return catalog.get_recipe(recipe_id, portions)


@mcp.tool()
def add_recipes(recipes: list[dict], include_basics: bool = False) -> dict:
    """Legg alle varene til én eller flere oppskrifter i kurven, f.eks. middager for flere dager.

    Mengdene slås sammen på tvers av oppskriftene før de rundes opp til hele pakninger,
    så to retter som bruker en halv pakke rømme hver gir én pakke, ikke to.

    Args:
        recipes: Liste med {"recipe_id": 2674, "portions": 4}.
        include_basics: Ta med basisvarer som salt, pepper og olje. Standard er nei.
    """
    shares: dict[int, float] = {}
    products: dict[int, catalog.Product] = {}
    used_for: dict[int, list[str]] = {}
    skipped_basics: set[str] = set()
    titles = []
    for entry in recipes:
        recipe = catalog.get_recipe(int(entry["recipe_id"]), entry.get("portions"))
        titles.append(f"{recipe['title']} ({recipe['portions']} porsjoner)")
        for ing in recipe["ingredients"]:
            if not ing["product"]:
                continue
            if ing["is_basic"] and not include_basics:
                skipped_basics.add(ing["ingredient"])
                continue
            pid = ing["product"]["id"]
            shares[pid] = shares.get(pid, 0.0) + ing["package_share"]
            products[pid] = catalog.Product(**ing["product"])
            used_for.setdefault(pid, []).append(recipe["title"])

    added, unavailable = [], []
    for pid, share in shares.items():
        product = products[pid]
        if not product.available:
            unavailable.append({"product": product.name, "for": used_for[pid]})
            continue
        quantity = max(1, math.ceil(share - 1e-9))
        cart.add(product, quantity, used_for=used_for[pid])
        added.append({"product_id": pid, "name": product.name, "details": product.details,
                      "price": product.price, "quantity": quantity, "for": used_for[pid],
                      "offer": product.offer})
    return {
        "recipes": titles,
        "added": added,
        "unavailable": unavailable,
        "skipped_basics": sorted(skipped_basics),
        "cart": cart.summary(),
    }


@mcp.tool()
def add_to_cart(product_id: int, quantity: int = 1) -> dict:
    """Legg en vare i handlekurven. Bruk product_id fra search_products."""
    if quantity < 1:
        return {"error": "Antall må være minst 1"}
    product = catalog.get_product(product_id)
    if not product.available:
        return {"error": f"{product.name} er ikke tilgjengelig"}
    line = cart.add(product, quantity)
    return {"added": line, "cart": cart.summary()}


@mcp.tool()
def remove_from_cart(product_id: int, quantity: int | None = None) -> dict:
    """Fjern en vare fra kurven. Uten antall fjernes hele linjen."""
    line = cart.remove(product_id, quantity)
    if line is None:
        return {"error": f"Vare {product_id} ligger ikke i kurven"}
    return {"removed": line, "cart": cart.summary()}


@mcp.tool()
def view_cart() -> dict:
    """Vis innholdet i handlekurven med linjesummer og totalsum."""
    return cart.summary()


@mcp.tool()
def clear_cart() -> dict:
    """Tøm handlekurven."""
    cart.clear()
    return cart.summary()


@mcp.tool()
def checkout(send_to_oda: bool = False) -> dict:
    """Oppdater prisene og lag en ordreoppsummering.

    Args:
        send_to_oda: Overfør kurven til brukerens Oda-konto (krever ODA_EMAIL og
            ODA_PASSWORD). Spør alltid brukeren før dette settes. Levering og
            betaling velges deretter i Oda-appen eller på oda.com.
    """
    summary = cart.summary()
    if not summary["lines"]:
        return {"error": "Handlekurven er tom"}
    changed = []
    for line in summary["lines"]:
        product = catalog.get_product(line["product_id"])
        if product.price != line["price"]:
            changed.append({"product_id": product.id, "name": product.name, "old": line["price"], "new": product.price})
            cart.set_price(product.id, product.price)
    result = {**cart.summary(), "price_changes": changed}

    if not send_to_oda:
        result["next_step"] = (
            "Bruk lenkene for å legge varene i kurven på oda.com, eller kall checkout med "
            "send_to_oda=true for å overføre kurven til Oda-kontoen."
        )
        return result
    try:
        oda_cart = account.add_items([(line["product_id"], line["quantity"]) for line in cart.summary()["lines"]])
    except (OdaAccountError, OSError) as e:
        result["error"] = f"Klarte ikke å overføre til Oda: {e}"
        return result
    result["oda_cart"] = {
        "item_count": oda_cart.get("product_quantity_count"),
        "total": oda_cart.get("total_gross_amount"),
    }
    result["next_step"] = "Kurven ligger nå i Oda-kontoen. Velg levering og betal på oda.com eller i appen."
    return result


@mcp.prompt()
def plan_meals(request: str = "middag for tre dager") -> str:
    """Planlegg måltider sammen med brukeren og handle ingrediensene hos Oda."""
    return f"""Brukeren vil handle: «{request}».

Hjelp brukeren med å planlegge og handle, i denne rekkefølgen:

1. Still korte oppfølgingsspørsmål, få av gangen, om det som ikke er gitt:
   - hvor mange som skal spise, og om det er barn
   - allergier, ting de ikke spiser, eller vegetar
   - ønsker eller retter de har lyst på, og hvor mye tid de har til matlaging
   - budsjett, og om de vil at rettene skal bygge på det som er på tilbud
   - om de har basisvarer som salt, pepper, olje og krydder hjemme
2. Vil brukeren spare penger, bruk dinners_from_offers. Den gir middager som er
   billige på grunn av dagens tilbud, med pris per porsjon og beregnet besparelse.
   Bruk exclude for allergier og ting de ikke spiser, og query for type mat. Finn
   ellers passende oppskrifter med search_recipes. Bruk gjerne flere søk, som
   «kylling», «fisk» og «vegetar», for variasjon. Foreslå én rett per måltid med
   tilberedningstid og en kort begrunnelse. La brukeren bytte ut retter, og hent nye
   forslag til de sier at menyen er god.
3. Kall add_recipes med alle de godkjente oppskriftene og riktig antall porsjoner.
   Sett include_basics bare hvis brukeren mangler basisvarer.
4. Vis hva som ble lagt i kurven, gruppert per rett, med pris og totalsum. Nevn
   utilgjengelige varer og foreslå erstatninger med search_products. Spør om noe skal
   byttes eller legges til, som frokost, drikke eller snacks. Pek ut varer på
   tilbud, særlig «3 for 2» og «2 for X kr», der det lønner seg å kjøpe flere.
5. Når brukeren er fornøyd, kall checkout. Spør før du setter send_to_oda=true, og
   forklar at levering og betaling velges i Oda-appen.

Svar på norsk."""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
