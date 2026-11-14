
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
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing")

GEMINI_MODEL = "gemini-2.5-flash"

# Maximale Dateigroesse: 1 MB
# LimeSurvey komprimiert bereits auf ca. 0,5 MB.
MAX_UPLOAD_BYTES = 1024 * 1024

# Maximale Wartezeit auf Gemini
AI_TIMEOUT = 110

# Maximal eine gleichzeitige KI-Analyse
analysis_lock = asyncio.Semaphore(1)

# Aktueller Google Gemini Client
client = genai.Client(api_key=API_KEY)


# ==========================================
# STARTSEITE / HEALTH CHECK
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
# BILDTYP PRUEFEN
# ==========================================

def detect_image_type(data: bytes) -> str:

    # JPEG
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # PNG
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
# PROMPT FUER GEFAEHRDUNGSBEURTEILUNG
# ==========================================

PROMPT = """
WICHTIG:
Antworte ausschliesslich auf Deutsch.

Analysiere dieses Arbeitsplatzbild.

Erstelle eine vollstaendige Gefaehrdungsbeurteilung
nach der Nohl-Methode auf Grundlage der
sichtbaren Bildinformationen.

Beruecksichtige:

- sichtbare Gefahren
- Ursachen
- moegliche Folgen
- Massnahmen zur Risikominimierung

Ordne die Risiken passenden
Gefaehrdungskategorien zu.

Unterscheide dabei zwischen:

1. Im Bild erkennbaren Gefaehrdungen
2. Vermuteten Gefaehrdungen
3. Sachverhalten, die vor Ort geprueft
   werden muessen

Erfinde keine nicht erkennbaren
technischen oder organisatorischen Fakten.

Erstelle eine professionelle und
strukturierte Darstellung mit:

- HTML-Ueberschriften
- HTML-Tabellen
- HTML-Aufzaehlungen

Gib ausschliesslich sauberes HTML zurueck.

Verwende kein Markdown.
Verwende keine HTML-Codebloecke.
"""


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
    # PHASE 1: DATEI LADEN
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
            "[%s] Datei zu gross: %d Bytes",
            request_id,
            len(image_bytes)
        )

        raise HTTPException(
            status_code=413,
            detail=(
                "Bild zu gross. "
                "Bitte maximal 1 MB hochladen."
            )
        )

    # --------------------------------------
    # PHASE 2: BILD PRUEFEN
    # --------------------------------------

    mime_type = detect_image_type(image_bytes)

    logger.info(
        "[%s] Bild empfangen: %.1f KB, %s",
        request_id,
        len(image_bytes) / 1024,
        mime_type
    )

    # Keine Bilddekodierung mit Pillow.
    # Die komprimierten Daten gehen
    # direkt an Gemini.

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type
    )

    del image_bytes

    # --------------------------------------
    # PHASE 3: GEMINI ANALYSE
    # --------------------------------------

    # Wenn bereits eine Analyse laeuft,
    # maximal 10 Sekunden warten.

    try:
        await asyncio.wait_for(
            analysis_lock.acquire(),
            timeout=10
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Der KI-Server ist beschaeftigt. "
                "Bitte erneut versuchen."
            )
        )

    try:
        logger.info(
            "[%s] Gemini-Analyse startet",
            request_id
        )

        ai_start = time.monotonic()

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
                        max_output_tokens=4096
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
                    "Die KI-Analyse hat zu lange "
                    "gedauert. Bitte erneut versuchen."
                )
            )

        ai_duration = time.monotonic() - ai_start

        logger.info(
            "[%s] Gemini fertig nach %.1f Sekunden",
            request_id,
            ai_duration
        )

        # ----------------------------------
        # PHASE 4: ERGEBNIS
        # ----------------------------------

        html = response.text

        if not html or not html.strip():
            raise HTTPException(
                status_code=502,
                detail=(
                    "Gemini hat kein auswertbares "
                    "Ergebnis geliefert."
                )
            )

        total_duration = (
            time.monotonic() - start_time
        )

        logger.info(
            "[%s] Analyse erfolgreich: %.1f Sekunden",
            request_id,
            total_duration
        )

        # Kompatibel zum LimeSurvey Frontend
        return {
            "html": html
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "[%s] Fehler bei Gemini",
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
