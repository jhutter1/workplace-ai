
import os
import time
import asyncio
import logging
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

# ==========================================
# KONFIGURATION
# ==========================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("outpredict")

app = FastAPI(title="outpredict KI-Risikoanalyse")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing")

# Gemini-Modell
GEMINI_MODEL = "gemini-2.5-flash"

# Maximale Bildgroesse: 1 MB
MAX_UPLOAD_BYTES = 1024 * 1024

# Maximale Dauer der KI-Anfrage
AI_TIMEOUT = 110

# Nur eine Analyse gleichzeitig pro Serverprozess
analysis_lock = asyncio.Semaphore(1)

# Google Gemini Client
client = genai.Client(api_key=API_KEY)


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/")
async def home():
    return {
        "status": "ok",
        "service": "outpredict",
        "model": GEMINI_MODEL
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ==========================================
# BILDFORMAT PRUEFEN
# ==========================================

def detect_image_type(data: bytes) -> str:

    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    raise HTTPException(
        status_code=415,
        detail=(
            "Nicht unterstuetztes Bildformat. "
            "Bitte JPEG oder PNG verwenden."
        )
    )


# ==========================================
# ORIGINALER ANALYSEAUFTRAG
# ==========================================

PROMPT = """
WICHTIG:
Antworte ausschließlich auf Deutsch.

Analysiere dieses Arbeitsplatzbild.

Erstelle eine vollständige Gefährdungsbeurteilung
nach der Nohl-Methode.

Berücksichtige dabei:
- sichtbare Gefahren
- Ursachen
- mögliche Folgen
- Maßnahmen zur Risikominimierung

Ordne die Risiken passenden
Gefährdungskategorien zu.

Erstelle:
- Überschriften
- Tabellen
- Aufzählungen

Die Ausgabe soll professionell,
ausführlich und strukturiert sein.

Gib ausschließlich sauberes HTML zurück.
Verwende kein Markdown.
"""


# ==========================================
# GEMINI-ANTWORT PRUEFEN
# ==========================================

def check_finish_reason(response):

    if not response.candidates:
        raise HTTPException(
            status_code=502,
            detail="Gemini hat keine Antwort geliefert."
        )

    candidate = response.candidates[0]
    reason = candidate.finish_reason

    if reason is None:
        return

    reason_name = getattr(reason, "name", str(reason))

    logger.info(
        "Gemini Finish Reason: %s",
        reason_name
    )

    if reason_name == "MAX_TOKENS":
        raise HTTPException(
            status_code=502,
            detail=(
                "Die Gefaehrdungsbeurteilung wurde "
                "wegen des Tokenlimits abgeschnitten."
            )
        )

    if reason_name != "STOP":
        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini konnte die Antwort nicht "
                "vollstaendig abschliessen."
            )
        )


# ==========================================
# KI-ANALYSE
# ==========================================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    request_id = uuid.uuid4().hex[:8]
    start_time = time.monotonic()

    logger.info(
        "[%s] Analyse angefordert",
        request_id
    )

    # --------------------------------------
    # PHASE 1: DATEI LESEN
    # --------------------------------------

    try:
        image_bytes = await file.read(
            MAX_UPLOAD_BYTES + 1
        )
    finally:
        await file.close()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Keine Bilddaten empfangen."
        )

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        logger.warning(
            "[%s] Bild zu gross: %d Bytes",
            request_id,
            len(image_bytes)
        )

        raise HTTPException(
            status_code=413,
            detail=(
                "Bild zu gross. "
                "Maximal 1 MB erlaubt."
            )
        )

    # --------------------------------------
    # PHASE 2: BILDTYP PRUEFEN
    # --------------------------------------

    mime_type = detect_image_type(image_bytes)

    logger.info(
        "[%s] Bild empfangen: %.1f KB, %s",
        request_id,
        len(image_bytes) / 1024,
        mime_type
    )

    # Keine Bildverarbeitung mit Pillow
    # Komprimiertes Bild direkt an Gemini

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type
    )

    del image_bytes

    # --------------------------------------
    # PHASE 3: ANALYSEPLATZ RESERVIEREN
    # --------------------------------------

    try:
        await asyncio.wait_for(
            analysis_lock.acquire(),
            timeout=10
        )

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Der KI-Server ist derzeit beschaeftigt. "
                "Bitte erneut versuchen."
            )
        )

    try:

        logger.info(
            "[%s] Gemini-Analyse startet",
            request_id
        )

        ai_start = time.monotonic()

        # ----------------------------------
        # PHASE 4: GEMINI AUFRUFEN
        # ----------------------------------

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        PROMPT,
                        image_part
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                        thinking_config=types.ThinkingConfig(
                            thinking_budget=1024
                        )
                    )
                ),
                timeout=AI_TIMEOUT
            )

        except asyncio.TimeoutError:

            logger.error(
                "[%s] Gemini Timeout",
                request_id
            )

            raise HTTPException(
                status_code=504,
                detail=(
                    "Die KI-Analyse hat zu lange gedauert. "
                    "Bitte erneut versuchen."
                )
            )

        ai_duration = time.monotonic() - ai_start

        logger.info(
            "[%s] Gemini fertig nach %.1f Sekunden",
            request_id,
            ai_duration
        )

        # ----------------------------------
        # PHASE 5: ANTWORT PRUEFEN
        # ----------------------------------

        check_finish_reason(response)

        html = response.text

        if not html or not html.strip():
            raise HTTPException(
                status_code=502,
                detail=(
                    "Gemini hat kein auswertbares "
                    "Ergebnis geliefert."
                )
            )

        # Falls Gemini trotzdem Markdown-Fences
        # zurueckgibt, diese entfernen.
        html = html.strip()

        if html.startswith("```html"):
            html = html[7:].strip()
        elif html.startswith("```"):
            html = html[3:].strip()

        if html.endswith("```"):
            html = html[:-3].strip()

        # ----------------------------------
        # PHASE 6: ERGEBNIS ZURUECKGEBEN
        # ----------------------------------

        total_duration = (
            time.monotonic() - start_time
        )

        logger.info(
            "[%s] Analyse erfolgreich: %.1f Sekunden",
            request_id,
            total_duration
        )

        logger.info(
            "[%s] HTML-Laenge: %d Zeichen",
            request_id,
            len(html)
        )

        return {
            "html": html
        }

    except HTTPException:
        raise

    except Exception:

        logger.exception(
            "[%s] Fehler bei der KI-Analyse",
            request_id
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Die KI-Analyse konnte nicht "
                "abgeschlossen werden."
            )
        )

    finally:
        analysis_lock.release()
