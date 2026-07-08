from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image
import io
import os
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
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
    image_bytes = await file.read()
    image = Image.open(
        io.BytesIO(image_bytes)
    )
    prompt = """
Analyze this workplace image.
Create a detailed workplace hazard assessment according to the Nohl method.
Identify:
- visible hazards
- causes
- consequences
- mitigation measures
Return clean HTML only.
"""
    response = model.generate_content(
        [prompt, image]
    )
    html = response.text
    return {
        "html": html
    }