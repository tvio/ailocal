#!/usr/bin/env python3
"""Dva agenti si povídají mezi sebou přes lokální Ollama model."""

import sys
import json
import requests

from ollama_health import get_working_url

MODEL = "gpt-oss:20b"
MAX_TURNS = 10

SYSTEM_KLIENT = (
    "Jsi zvídavý člověk, který se chce dozvědět co nejvíc o zadaném tématu. "
    "Kladeš stručné, ale zajímavé otázky. Odpovídáš česky. "
    "Nikdy neopakuj to, co už bylo řečeno – posouvej konverzaci dál."
    
)

SYSTEM_ODBORNIK = (
    "Jsi odborník a rád vysvětluješ věci srozumitelně a stručně. "
    "Odpovídáš česky. Maximálně 10 vět na odpověď. Pokud nemáš co dodat, řekni to."
    "Vrat kazdou větu také jako json, kde bude take atribut přesné datum vygenreování prvního tokenu věty a nějaký typ jako třeba  podstata nebo doplnění nebo poznámka"
    )


def chat(messages: list[dict], *, base_url: str) -> str:
    resp = requests.post(
        base_url,
        json={"model": MODEL, "messages": messages, "stream": True},
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()

    full = []
    # iter.lines je iterator na http streamem posílaných dat
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        token = chunk.get("message", {}).get("content", "")
        if token:
            print(token, end="", flush=True)
            full.append(token)
    print()
    # slepení seznamu řetězců do jednoho ("" = žádný oddělovač mezi prvky)
    return "".join(full)


def main():
    if len(sys.argv) < 2:
        print(f"Použití: python {sys.argv[0]} \"téma konverzace\"")
        sys.exit(1)

    base = get_working_url()
    if base is None:
        sys.exit(1)
    chat_url = base.rstrip("/") + "/api/chat"

    topic = " ".join(sys.argv[1:])
    turns = MAX_TURNS
    if "--turns" in sys.argv:
        idx = sys.argv.index("--turns")
        turns = int(sys.argv[idx + 1])
        topic = " ".join(a for a in sys.argv[1:] if a not in ("--turns", sys.argv[idx + 1]))

    print(f"=== Téma: {topic} | Model: {MODEL} | Kol: {turns} | Ollama: {base} ===\n")

    history_klient: list[dict] = [{"role": "system", "content": SYSTEM_KLIENT}]
    history_odbornik: list[dict] = [{"role": "system", "content": SYSTEM_ODBORNIK}]

    opening = f"Zajímá mě téma: {topic}. Můžeš mi o tom něco říct?"

    print(f"[Klient]: {opening}\n")
    history_odbornik.append({"role": "user", "content": opening})

    for turn in range(turns):
        # Odborník odpovídá
        print("[Odborník]: ", end="", flush=True)
        answer = chat(history_odbornik, base_url=chat_url)
        history_odbornik.append({"role": "assistant", "content": answer})
        history_klient.append({"role": "user", "content": answer})
        print()

        if turn == turns - 1:
            break

        # Klient reaguje / klade další otázku
        history_klient.append(
            {"role": "user", "content": "Polož další zajímavou otázku nebo reaguj na to, co jsi slyšel."}
        )
        print("[Klient]: ", end="", flush=True)
        question = chat(history_klient, base_url=chat_url)
        history_klient.pop()  # odstraníme instrukční prompt
        history_klient.append({"role": "assistant", "content": question})
        history_odbornik.append({"role": "user", "content": question})
        print()

    print("=== Konec konverzace ===")


if __name__ == "__main__":
    main()
