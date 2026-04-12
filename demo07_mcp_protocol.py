#!/usr/bin/env python3
"""UC7 – MCP protokol – praktické demo.

Ukázka Model Context Protocol:
  - Jednoduchý MCP server s nástroji (kalkulačka, DB dotaz, soubory)
  - Klient, který LLM nechá rozhodnout, který nástroj použít

Použití:
  uv run python demo07_mcp_protocol.py --server    # spustí MCP server
  uv run python demo07_mcp_protocol.py "Kolik je 15% z 84000?"
  uv run python demo07_mcp_protocol.py "Kolik dokumentů je v databázi?"
  uv run python demo07_mcp_protocol.py "Vypiš soubory v adresáři data/"
"""

import sys
import json
import argparse
from pathlib import Path

from common.config import MODEL_CHAT
from common.ollama_client import get_ollama_url, chat
from common.db_postgres import get_connection, get_document_stats


# ---------------------------------------------------------------------------
# Definice nástrojů (tools) – simulace MCP serveru
# ---------------------------------------------------------------------------

TOOLS = {
    "calculator": {
        "name": "calculator",
        "description": "Provede matematický výpočet. Vstup: matematický výraz jako řetězec.",
        "example": "calculator(\"15 * 84000 / 100\")",
    },
    "db_stats": {
        "name": "db_stats",
        "description": "Vrátí statistiky dokumentů uložených v vektorové databázi.",
        "example": "db_stats()",
    },
    "list_files": {
        "name": "list_files",
        "description": "Vypíše soubory v zadaném adresáři. Vstup: cesta k adresáři.",
        "example": "list_files(\"data/pdf\")",
    },
    "read_file_snippet": {
        "name": "read_file_snippet",
        "description": "Přečte prvních N znaků ze souboru. Vstup: cesta k souboru.",
        "example": "read_file_snippet(\"README.md\")",
    },
}


def tool_calculator(expression: str) -> str:
    """Bezpečný výpočet matematického výrazu."""
    allowed = set("0123456789+-*/.() %")
    if not all(c in allowed for c in expression.replace(" ", "")):
        return f"Chyba: nepovolené znaky ve výrazu '{expression}'"
    try:
        result = eval(expression)  # noqa: S307 – omezeno na numerické výrazy
        return f"Výsledek: {expression} = {result}"
    except Exception as e:
        return f"Chyba: {e}"


def tool_db_stats() -> str:
    """Vrátí statistiky z databáze."""
    try:
        conn = get_connection()
        stats = get_document_stats(conn)
        conn.close()
        if not stats:
            return "Databáze je prázdná (žádné dokumenty)."
        lines = ["Dokumenty v databázi:"]
        total = 0
        for s in stats:
            lines.append(f"  - {s['document_name']}: {s['chunk_count']} chunků")
            total += s["chunk_count"]
        lines.append(f"Celkem: {len(stats)} dokumentů, {total} chunků")
        return "\n".join(lines)
    except Exception as e:
        return f"Chyba připojení k DB: {e}"


def tool_list_files(directory: str) -> str:
    """Vypíše soubory v adresáři."""
    path = Path(directory)
    if not path.is_dir():
        return f"Adresář '{directory}' neexistuje."
    items = sorted(path.iterdir())
    if not items:
        return f"Adresář '{directory}' je prázdný."
    lines = [f"Obsah adresáře {directory}:"]
    for item in items:
        if item.is_dir():
            count = sum(1 for _ in item.rglob("*") if _.is_file())
            lines.append(f"  📁 {item.name}/ ({count} souborů)")
        else:
            size = item.stat().st_size
            lines.append(f"  📄 {item.name} ({size:,} B)")
    return "\n".join(lines)


def tool_read_file_snippet(filepath: str, max_chars: int = 500) -> str:
    """Přečte začátek souboru."""
    path = Path(filepath)
    if not path.is_file():
        return f"Soubor '{filepath}' neexistuje."
    try:
        text = path.read_text(encoding="utf-8")[:max_chars]
        return f"Obsah souboru {filepath} (prvních {min(len(text), max_chars)} znaků):\n{text}"
    except Exception as e:
        return f"Chyba čtení: {e}"


# Mapování názvů na funkce
TOOL_FUNCTIONS = {
    "calculator": tool_calculator,
    "db_stats": tool_db_stats,
    "list_files": tool_list_files,
    "read_file_snippet": tool_read_file_snippet,
}


def execute_tool(tool_name: str, args_str: str = "") -> str:
    """Spustí nástroj podle názvu."""
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return f"Neznámý nástroj: {tool_name}"
    if args_str:
        return func(args_str)
    return func()


# ---------------------------------------------------------------------------
# MCP-like orchestrátor
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM = """\
Jsi inteligentní asistent s přístupem k nástrojům. Na základě uživatelovy otázky rozhodni, \
který nástroj použít, a vrať odpověď ve formátu JSON.

Dostupné nástroje:
{tools_desc}

Odpověz POUZE ve formátu JSON:
{{
  "tool": "název_nástroje",
  "args": "argument pro nástroj (string)",
  "reasoning": "proč jsi zvolil tento nástroj"
}}

Pokud žádný nástroj není potřeba, vrať:
{{
  "tool": "none",
  "args": "",
  "reasoning": "důvod"
}}
"""


def run_mcp_query(question: str, *, model: str, base_url: str) -> None:
    """Zpracuje dotaz přes MCP-like orchestraci."""
    # 1. LLM rozhodne, který nástroj použít
    tools_desc = "\n".join(
        f"- {t['name']}: {t['description']} Příklad: {t['example']}"
        for t in TOOLS.values()
    )
    system = ORCHESTRATOR_SYSTEM.format(tools_desc=tools_desc)

    print(f"\n[1/3] LLM rozhoduje, který nástroj použít...")
    decision_raw = chat(question, system=system, model=model, base_url=base_url)

    # Parsování rozhodnutí
    try:
        start = decision_raw.find("{")
        end = decision_raw.rfind("}") + 1
        decision = json.loads(decision_raw[start:end])
    except (json.JSONDecodeError, ValueError):
        print(f"  ⚠️  LLM nevrátil validní JSON: {decision_raw[:200]}")
        return

    tool_name = decision.get("tool", "none")
    tool_args = decision.get("args", "")
    reasoning = decision.get("reasoning", "")

    print(f"  🔧 Nástroj:  {tool_name}")
    print(f"  📎 Argument: {tool_args}")
    print(f"  💭 Důvod:    {reasoning}")

    if tool_name == "none":
        print(f"\n💬 LLM nepotřebuje žádný nástroj – odpovídá přímo:")
        direct = chat(question, system="Odpovídej česky, stručně.", model=model, base_url=base_url)
        print(direct)
        return

    # 2. Spustíme nástroj
    print(f"\n[2/3] Spouštím nástroj '{tool_name}'...")
    tool_result = execute_tool(tool_name, tool_args)
    print(f"  📋 Výsledek:\n{tool_result}")

    # 3. LLM sestaví finální odpověď
    print(f"\n[3/3] LLM formuluje odpověď...")
    final_prompt = f"""Uživatel se zeptal: "{question}"

Použil jsi nástroj '{tool_name}' a dostal tento výsledek:
{tool_result}

Formuluj stručnou a srozumitelnou odpověď česky."""

    final_answer = chat(final_prompt, system="Jsi pomocný asistent. Odpovídej česky.", model=model, base_url=base_url)
    print(f"\n💬 Finální odpověď:\n{final_answer}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC7 – MCP protokol – praktické demo"
    )
    parser.add_argument("query", nargs="*", help="Dotaz pro MCP orchestrátor")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model (výchozí {MODEL_CHAT})")
    parser.add_argument("--list-tools", action="store_true", help="Zobrazit dostupné nástroje")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("UC7 – MCP protokol – praktické demo")
    print("=" * 60)

    if args.list_tools:
        print("\n🔧 Dostupné nástroje:")
        for t in TOOLS.values():
            print(f"  - {t['name']}: {t['description']}")
            print(f"    Příklad: {t['example']}")
        return

    if not args.query:
        print("\nChyba: zadejte dotaz nebo --list-tools", file=sys.stderr)
        sys.exit(1)

    question = " ".join(args.query)
    base_url = get_ollama_url()

    print(f"\n🤖 Model:  {args.model}")
    print(f"❓ Dotaz:  {question}")
    print(f"  ✓ Ollama: {base_url}")

    run_mcp_query(question, model=args.model, base_url=base_url)

    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
