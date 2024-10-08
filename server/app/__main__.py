from contextlib import asynccontextmanager
import json

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.internal.ai import AI, get_ai
from app.internal.data import DOCUMENT_1, DOCUMENT_2
from app.internal.db import Base, SessionLocal, engine, get_db

import app.models as models
import app.schemas as schemas


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create the database tables
    Base.metadata.create_all(bind=engine)
    # Insert seed data
    with SessionLocal() as db:
        db.execute(insert(models.Document).values(id=1, version=1, content=DOCUMENT_1))
        db.execute(insert(models.Document).values(id=2, version=1, content=DOCUMENT_2))
        db.execute(insert(models.Document).values(id=2, version=2, content=DOCUMENT_2))
        db.execute(insert(models.Document).values(id=2, version=3, content=DOCUMENT_2))
        db.commit()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/document")
def get_document(
    document_id: int, document_version: int, db: Session = Depends(get_db)
) -> schemas.DocumentRead:
    """Get a document from the database"""
    return db.scalar(select(models.Document).where(models.Document.id == document_id).where(models.Document.version == document_version))


@app.post("/save")
def save(
    document_id: int, document_version: int, document: schemas.DocumentBase, db: Session = Depends(get_db)
):
    """Save the document to the database"""
    db.execute(
        update(models.Document)
        .where(models.Document.id == document_id)
        .where(models.Document.version == document_version)
        .values(content=document.content)
    )
    db.commit()
    return {"document_id": document_id, "content": document.content}

@app.get("/versions")
def get_versions(
    db: Session = Depends(get_db)
):
    """Get all versions of all documents from the database"""
    results = db.execute(select(models.Document.id, models.Document.version)
    )
    # Initialize an empty dictionary to store versions
    all_versions = {}

    # Loop through each row and build the nested dictionary
    for row in results:
        document_id, version = row
        if document_id not in all_versions:
            all_versions[document_id] = []
        all_versions[document_id].append(version)

    return all_versions

@app.post("/create_version")
def create_version(
    document_id: int, document_version: int, document: schemas.DocumentBase, db: Session = Depends(get_db)
):
    """Save the new document to the database"""
    db_document = models.Document(id = document_id, version = document_version, content=document.content)
    db.add(db_document)
    db.commit()
    return {"document_id": document_id, "content": document.content}

@app.websocket("/ws")
async def websocket(websocket: WebSocket, ai: AI = Depends(get_ai)):
    await websocket.accept()
    while True:
        try:
            """
            The AI doesn't expect to receive any HTML.
            You can call ai.review_document to receive suggestions from the LLM.
            Remember, the output from the LLM will not be deterministic, so you may want to validate the output before sending it to the client.
            """
            document = await websocket.receive_text()
            print("Received data via websocket")

            paragraph = document.strip()  # Remove leading and trailing whitespace

            # Process the paragraph using the AI model
            suggestions = ai.review_document(paragraph)
            print("Received suggestions")
            response=''
            # Send the suggestions back to the client
            async for suggestion in suggestions:
                if suggestion:
                    response+=suggestion
            await websocket.send_json(response)

        except WebSocketDisconnect:
            break
        except Exception as e:
            print(f"Error occurred: {e}")
            continue


@app.websocket("/ws_ai_sugg")
async def websocket_ai_sugg(websocket: WebSocket, ai: AI = Depends(get_ai)):
    await websocket.accept()
    while True:
        try:

            json_data = await websocket.receive_text()
            python_dict = json.loads(json_data)
            document, paragraph, suggestion = python_dict["document"], python_dict["paragraph"], python_dict["suggestion"]
            print("Received data via websocket")

            paragraph = document.strip()  # Remove leading and trailing whitespace

            # Process the paragraph using the AI model
            suggestions = ai.incorporate_suggestions(document, paragraph, suggestion)
            print("Received suggestions")
            response=''
            # Send the suggestions back to the client
            async for suggestion in suggestions:
                if suggestion:

                    response+=suggestion
            await websocket.send_json(response)

        except WebSocketDisconnect:
            break
        except Exception as e:
            print(f"Error occurred: {e}")
            continue