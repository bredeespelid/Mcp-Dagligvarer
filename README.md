# oda-mcp

MCP-server for å planlegge måltider og handle varer hos [Oda](https://oda.com). Bruker Odas egne oppskrifter, der hver ingrediens er koblet til en vare, slik at *«jeg vil ha middag for tre dager»* blir en ferdig handlekurv.

## Planlegge måltider

Si for eksempel *«jeg vil ha middag for tre dager»*. Serveren har prompten `plan_meals`, og instruksjoner som får Claude til å:

1. spørre om antall personer, allergier, ønsker, tid, budsjett og basisvarer hjemme
2. foreslå oppskrifter fra Oda, som du kan bytte ut
3. legge alle ingrediensene i kurven med `add_recipes`. Mengdene slås sammen på tvers av rettene før de rundes opp til hele pakninger, og basisvarer som salt, pepper og olje hoppes over hvis du ikke ber om dem
4. vise kurven per rett, foreslå erstatninger for utsolgte varer og spørre om noe skal legges til
5. kjøre `checkout`, og eventuelt overføre kurven til Oda-kontoen din

I Claude Code kan prompten også startes direkte med `/mcp__oda__plan_meals`.

### Middager fra tilbud

*«Gi meg tre billige middager basert på det som er på tilbud»* bruker `dinners_from_offers`. Den går gjennom opptil 120 oppskrifter, og for hver ingrediens finner den den koblede Oda-varen med dagens pris og rabatt. Rettene rangeres slik:

1. retter der hovedråvaren (den dyreste ingrediensen) er på tilbud, først
2. deretter etter beregnet besparelse i kroner

Besparelse som krever flerkjøp («2 for 64 kr», «3 for 2») vises for seg, siden den forutsetter at du kjøper flere pakker. Allergier og ting dere ikke spiser kan utelukkes med `exclude`.

## Verktøy

| Verktøy | Beskrivelse |
|---|---|
| `search_products` | Søk etter varer (`query`, `page`, `only_offers`) |
| `find_offers` | Varer på tilbud ("-20 %", "3 for 2", "2 for 60 kr"), sortert etter rabatt, eventuelt avgrenset med søkeord |
| `get_product` | Detaljer og pris for én vare |
| `dinners_from_offers` | Middager som blir billige på grunn av dagens tilbud, rangert etter besparelse, med pris per porsjon og hvilke ingredienser som er på tilbud |
| `search_recipes` | Søk etter oppskrifter (`kylling`, `vegetar`, `taco` …) |
| `get_recipe` | Ingredienser, fremgangsmåte og varer for et gitt antall porsjoner |
| `add_recipes` | Legg varene til én eller flere oppskrifter i kurven |
| `add_to_cart` / `remove_from_cart` | Legg til eller fjern enkeltvarer |
| `view_cart` / `clear_cart` | Vis eller tøm kurven |
| `checkout` | Oppdaterer priser og lager oppsummering. Med `send_to_oda=true` overføres kurven til Oda-kontoen |

Kurven er lokal, i `~/.oda-mcp/cart.json`, til du kjører `checkout`. Levering og betaling velger du i Oda-appen eller på oda.com.

> **`send_to_oda` er eksperimentelt.** Oda har ikke et offisielt, åpent handlekurv-API. Overføringen logger inn med e-post og passord og bruker de samme kallene som oda.com, så den kan slutte å virke hvis Oda endrer nettsiden. Søk og oppskrifter bruker åpne lesekall og trenger ikke innlogging.

## Kom i gang

```bash
git clone https://github.com/bredeespelid/Mcp-Dagligvarer && cd Mcp-Dagligvarer
pip install -e .
oda-mcp             # starter serveren over stdio
```

### Claude Code

```bash
claude mcp add oda -- python -m oda_mcp
# med Oda-konto:
claude mcp add oda -e ODA_EMAIL=deg@example.com -e ODA_PASSWORD=... -- python -m oda_mcp
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "oda": {
      "command": "oda-mcp",
      "env": { "ODA_EMAIL": "deg@example.com", "ODA_PASSWORD": "..." }
    }
  }
}
```

## Kjøre på Render

`render.yaml` setter opp en gratis webtjeneste, med `oda-mcp-http` over streamable HTTP på `/mcp`.

- `MCP_AUTH_TOKEN` beskytter serveren. Klienter sender den som `Authorization: Bearer <token>`, eller som `?key=<token>` når klienten bare tar imot en URL, som en egendefinert connector på claude.ai.
- Med gratisplanen lagres kurven i `/tmp` og forsvinner når tjenesten sover eller startes på nytt. Overfør den til Oda med `checkout` når du er ferdig.

```bash
claude mcp add --transport http oda https://<tjeneste>.onrender.com/mcp \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

## Konfigurasjon

| Variabel | Standard | Beskrivelse |
|---|---|---|
| `ODA_EMAIL` / `ODA_PASSWORD` | – | Oda-innlogging, bare nødvendig for `send_to_oda` |
| `ODA_CART_FILE` | `~/.oda-mcp/cart.json` | Hvor den lokale kurven lagres |
| `MCP_AUTH_TOKEN` | – | Token som kreves for HTTP-tilgang (anbefales på Render) |
| `PORT` | `8000` | Port for HTTP-modus |
| `ODA_API_URL` | `https://oda.com/api/v1` | API-base |

## Tester

```bash
pip install pytest
python -m pytest tests
```
