from fastapi import FastAPI

from app import settings as settings_module

app = FastAPI(title="nutribrain")


@app.get("/health")
def health() -> dict[str, str]:
    _ = settings_module.settings
    return {"status": "ok"}
