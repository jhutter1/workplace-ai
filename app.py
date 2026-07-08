from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image
import io
import os
app = FastAPI()
# CORS erlauben für LimeSurvey
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Gemini API Key aus Render Environment
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")
# Gemini konfigurieren
genai.configure(api_key=API_KEY)
# Modell auswählen
model = genai.GenerativeModel(
    "gemini-1.5-flash"
 ValueError("GEMINI_API_KEY is missing")
# Gemini konfigurieren
genai.configure(api_key=API_KEY)
# Modell auswählen
model = genai.GenerativeModel(
    "gemini-1.5-flash"
)
@app.get("/")
def home():
    return {
        "status": "ok"
    }
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        # Bild empfangen
        image_bytes = await file.read()
        # Bild öffnen
        image = Image.open(
            io.BytesIO(image_bytes)
        )
        # Prompt
        prompt = """
Analyze this workplace image.
Create a complete workplace risk assessment according to the Nohl method.
Tasks:
- Identify all visible hazards
- Categorize the hazards
- Explain causes and consequences
- Recommend mitigation measures
- Summarize the main risks
Return ONLY clean HTML.
Use:
- headings
- bullet points
- tables where appropriate
Do not use Markdown.
"""
        # Gemini Vision Request
        response = model.generate_content(
            [prompt, image]
        )
        html = response.text
        return {
            "html": html
        }
    except Exception as e:
        # Fehler direkt an LimeSurvey zurückgeben
        return {
            "html": f"""
            <h2>ERROR</h2>
            <pre>{str(e)}</pre>
            """
        }