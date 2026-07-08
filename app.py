from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image
import io
import os
app = FastAPI()
# CORS erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Gemini API Key laden
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")
# Gemini konfigurieren
genai.configure(api_key=API_KEY)
# Modell laden
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
        # Bild lesen
        image_bytes = await file.read()
        # Bild öffnen
        image = Image.open(
            io.BytesIO(image_bytes)
        )
        prompt = """
Analyze this workplace image.
Create a complete workplace risk assessment according to the Nohl method.
Tasks:
- Identify visible hazards
- Explain causes
- Describe consequences
- Recommend mitigation measures
Return ONLY clean HTML.
"""
        # Gemini Vision aufrufen
        response = model.generate_content(
            [prompt, image]
        )
        html = response.text
        return {
            "html": html
        }
    except Exception as e:
        return {
            "html": f"""
            <h2>ERROR</h2>
            <pre>{str(e)}</pre>
            """
        }