from fastapi import FastAPI

app = FastAPI(title="TK101 AI Backend", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
