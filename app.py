from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai import Credentials
from PIL import Image
import base64
import io
import os
app = FastAPI()
# erlaubt Requests von LimeSurvey
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
API_KEY = os.getenv("WATSONX_API_KEY")
PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")
URL = os.getenv("WATSONX_URL")
model = ModelInference(
    model_id="meta-llama/llama-3-2-90b-vision-instruct",
    credentials=Credentials(
        api_key=API_KEY,
        url=URL
    ),
    project_id=PROJECT_ID,
)
@app.get("/")
def home():
    return {
        "status": "ok"
    }
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes))
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(
        buffered.getvalue()
    ).decode()
    prompt = """
Analyze this workplace image.
Create a complete workplace risk assessment according to the Nohl method.
Identify:
- visible hazards
- causes
- consequences
- mitigation measures
Return clean HTML only.
"""
    response = model.generate(
        prompt=prompt,
        images=[image_base64],
        params={
            "max_new_tokens": 1500,
            "temperature": 0.2
        }
    )
    result = response["results"][0]["generated_text"]
    return {
        "html": result
    }