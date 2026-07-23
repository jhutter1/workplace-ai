from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx
import base64
import os

load_dotenv()

app = FastAPI()

# CORS erlauben (erlaubt lokale Browser-Aufrufe)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# IBM Consulting Advantage – OpenAI-kompatibler Endpunkt
CA_API_KEY   = os.getenv("CA_API_KEY")
CA_API_URL   = os.getenv("CA_API_URL", "https://api.ibm.com/consulting/run/v1/chat/completions")
CA_MODEL     = os.getenv("CA_MODEL", "ibm/granite-3-2-8b-instruct")

if not CA_API_KEY:
    raise ValueError("CA_API_KEY is missing – please set it in your .env file")


@app.get("/")
def home():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = """WICHTIG:
Antworte ausschließlich auf Deutsch.
Verwende keine englischen Begriffe.
Die komplette Antwort muss in deutscher Sprache sein.
Analysiere dieses Arbeitsplatzbild.
Erstelle eine vollständige Gefährdungsbeurteilung nach der Nohl-Methode.
Berücksichtige:
- sichtbare Gefahren
- Ursachen
- mögliche Folgen
- Maßnahmen zur Risikominimierung
Ordne die Risiken passenden Gefährdungskategorien zu.
Die Ausgabe soll professionell und strukturiert sein.
Verwende:
- HTML Überschriften
- HTML Tabellen
- HTML Listen
Gib ausschließlich sauberes HTML zurück.
Verwende KEIN Markdown."""

        payload = {
            "model": CA_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{file.content_type};base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {CA_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(CA_API_URL, json=payload, headers=headers)
            response.raise_for_status()

        html = response.json()["choices"][0]["message"]["content"]
        return {"html": html}

    except Exception as e:
        return {
            "html": f"""
            <h2>ERROR</h2>
            <pre>{str(e)}</pre>
            """
        }
