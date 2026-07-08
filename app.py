from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()
# erlaubt Aufrufe von LimeSurvey
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def home():
    return {
        "status": "ok"
    }
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    filename = file.filename
    content_type = file.content_type
    return {
        "html": f"""
        <h2>Image successfully uploaded</h2>
        <p><strong>Filename:</strong> {filename}</p>
        <p><strong>Content-Type:</strong> {content_type}</p>
        <p>Next step: AI image analysis.</p>
        """
    }