import json

import anthropic

from models import TRIVIA_CATEGORIES

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def reconstruct_question(category, fragment, answer):
    """Vervollständigt Frage, Antwort und Kategorie aus einem knappen Pub-Quiz-Stichwort.

    `category` und `answer` dürfen leer/None sein — die KI ergänzt was fehlt.
    Bereits angegebene Werte werden als gesicherte Fakten behandelt, nicht geraten.

    Gibt (question_text, answer, category, confidence) zurück, wobei confidence
    'high' | 'medium' | 'low' | 'unknown' ist. `category` ist garantiert einer der
    Werte aus TRIVIA_CATEGORIES.
    Wirft anthropic.APIError-Subklassen (oder RuntimeError bei Refusal) bei Fehlern —
    Aufrufer sollten das abfangen und dem Nutzer anzeigen.
    """
    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=400,
        output_config={
            "effort": "low",
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "frage": {"type": "string"},
                        "antwort": {"type": "string"},
                        "kategorie": {"type": "string", "enum": list(TRIVIA_CATEGORIES)},
                        "konfidenz": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
                    },
                    "required": ["frage", "antwort", "kategorie", "konfidenz"],
                    "additionalProperties": False,
                },
            },
        },
        messages=[{
            "role": "user",
            "content": (
                "Das hier ist eine knapp und schlecht aufgeschriebene Notiz zu einer Pub-Quiz-Frage — "
                "oft nur ein Stichwort, manchmal ohne separat vermerkte Antwort oder Kategorie. "
                "Rekonstruiere alle drei: die vollständige Frage, die wahrscheinlich gestellt wurde, "
                "die richtige Antwort, und die passende Kategorie aus der vorgegebenen Liste. "
                "Antworte ausschließlich auf Deutsch. Behandle als 'bekannt' markierte Werte als "
                "gesicherte Fakten, die NICHT verändert werden dürfen — ergänze nur, was als "
                "'(unbekannt)' markiert ist. Wenn das Stichwort vom genauen Datum/Zeitpunkt des Quiz "
                "abhängt (z.B. aktuelle Tabellenstände, aktuelle Kalenderwoche, Börsenkurse) und nicht "
                "aus Allgemeinwissen beantwortet werden kann, setze konfidenz auf \"unknown\" und gib "
                "trotzdem deine beste wörtliche Rekonstruktion der Frage an.\n\n"
                f"Stichwort: {fragment}\n"
                f"Bekannte Kategorie: {category or '(unbekannt)'}\n"
                f"Bekannte Antwort: {answer or '(unbekannt)'}\n\n"
                f"Erlaubte Kategorien: {', '.join(TRIVIA_CATEGORIES)}"
            ),
        }],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Modell hat die Anfrage abgelehnt (refusal).")

    text_block = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text_block)
    return data["frage"], data["antwort"], data["kategorie"], data["konfidenz"]
