from fastapi import FastAPI

app = FastAPI(title="Fake Identity & Document Screening System")

@app.get("/health")
def health():
    return {"status": "ok"}
