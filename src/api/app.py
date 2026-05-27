"""FastAPI 入口 — CORS + 路由注册"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import chat, documents, graph, ingest, status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title="Flamme", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "Flamme", "status": "ok"}


app.include_router(chat.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(status.router, prefix="/api")


def main():
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8765, reload=False)


if __name__ == "__main__":
    main()
