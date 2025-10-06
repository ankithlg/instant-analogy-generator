from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import json
from openai import OpenAI
from datetime import datetime
from bson import ObjectId

from auth import create_user, authenticate_user
from models import UserCreate, UserLogin
from utils import create_access_token, decode_access_token
from database import history_collection

# Load .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 1️⃣ Create FastAPI app
app = FastAPI(title="Instant Analogy Generator - Backend")

# 2️⃣ Enable CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3️⃣ OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
You are an expert teacher. For any technical concept provided, output ONLY a valid JSON object
with these exact keys:
- tagline: (string) a 1-line analogy
- analogy: (string) 2-5 sentence explanation
- mapping: (array of objects) each object MUST have:
    - technical: (string) the technical term
    - real-world: (string) the corresponding real-world analogy
- limitations: (array of strings) caveats or limitations of the analogy
Return ONLY valid JSON. Do NOT include explanations, markdown, or code fences.
"""

# ------------------------
# Pydantic models
# ------------------------
class GenerateRequest(BaseModel):
    concept: str
    level: str

class QuizRequest(BaseModel):
    concept: str
    result: dict 

# ------------------------
# Health check
# ------------------------
@app.get("/")
async def root():
    return {"status": "ok", "message": "Instant Analogy Generator backend running"}

# ------------------------
# Authentication routes
# ------------------------
@app.post("/signup")
async def signup(user: UserCreate):
    return await create_user(user)

@app.post("/login")
async def login(user: UserLogin):
    auth_user = await authenticate_user(user.email, user.password)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"email": auth_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# ------------------------
# Dependency: get current user
# ------------------------
async def get_current_user(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if payload is None or "email" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload  # e.g., {"email": "user@example.com"}

# ------------------------
# Generate analogy + quiz (protected)
# ------------------------
@app.post("/generate")
async def generate(req: GenerateRequest, current_user: dict = Depends(get_current_user)):
    try:
        concept = req.concept.strip()
        level = req.level

        if not concept:
            raise HTTPException(status_code=400, detail="Concept must not be empty")

        # --- Analogy prompt ---
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Concept: {concept}\nLevel: {level}"}
        ]

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        ai_text = resp.choices[0].message.content.strip()
        if ai_text.startswith("```"):
            lines = ai_text.split("\n")
            if len(lines) >= 3:
                ai_text = "\n".join(lines[1:-1])

        try:
            ai_json = json.loads(ai_text)
            ai_json.setdefault("tagline", "")
            ai_json.setdefault("analogy", "")
            ai_json.setdefault("mapping", [])
            ai_json.setdefault("limitations", [])
        except Exception:
            ai_json = {
                "tagline": "",
                "analogy": ai_text,
                "mapping": [],
                "limitations": []
            }

        # --- Quiz generation based on analogy ---
        quiz_prompt = f"""
        You are an expert teacher. Based on this concept and analogy, generate 5 multiple-choice questions.
        Each question must have exactly 4 options and 1 correct answer.
        Return ONLY JSON in this format:
        {{
          "concept": "{concept}",
          "questions": [
            {{
              "question": "Question text",
              "options": ["Option1", "Option2", "Option3", "Option4"],
              "answer": "CorrectOption"
            }}
          ]
        }}
        Analogy Data: {json.dumps(ai_json)}
        """

        quiz_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": quiz_prompt}],
            temperature=0.7,
            max_tokens=600
        )

        quiz_text = quiz_resp.choices[0].message.content.strip()
        if quiz_text.startswith("```"):
            lines = quiz_text.split("\n")
            if len(lines) >= 3:
                quiz_text = "\n".join(lines[1:-1])

        try:
            quiz_json = json.loads(quiz_text)
        except Exception:
            quiz_json = {"concept": concept, "questions": []}

        # --- Save both analogy + quiz in history ---
        history_doc = {
            "user_email": current_user["email"],
            "concept": concept,
            "level": level,
            "result": ai_json,
            "quiz": quiz_json,
            "timestamp": datetime.utcnow()
        }
        await history_collection.insert_one(history_doc)

        return {
            "concept_received": concept,
            "level": level,
            "user": current_user.get("email"),
            "result": ai_json,
            "quiz": quiz_json
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------
# Get user history
# ------------------------
@app.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    cursor = history_collection.find({"user_email": current_user["email"]}).sort("timestamp", -1)
    history = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        history.append(doc)
    return {"history": history}

# ------------------------
# Delete a history entry
# ------------------------
@app.delete("/history/{entry_id}")
async def delete_history(entry_id: str, current_user: dict = Depends(get_current_user)):
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entry ID")

    result = await history_collection.delete_one({
        "_id": obj_id,
        "user_email": current_user["email"]
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found or unauthorized")

    return {"status": "success", "message": "History entry deleted"}

# ------------------------
# Optional: Regenerate quiz manually
# ------------------------
@app.post("/quiz")
async def generate_quiz(req: QuizRequest, current_user: dict = Depends(get_current_user)):
    try:
        concept = req.concept.strip()
        analogy_data = req.result

        if not concept or not analogy_data:
            raise HTTPException(status_code=400, detail="Concept and analogy result are required")

        quiz_prompt = f"""
        You are an expert teacher. Based on this concept and the analogy provided, generate 5 multiple-choice questions.
        Each question must have exactly 4 options and 1 correct answer.
        Return ONLY JSON in this format:
        {{
          "concept": "{concept}",
          "questions": [
            {{
              "question": "Question text",
              "options": ["Option1", "Option2", "Option3", "Option4"],
              "answer": "CorrectOption"
            }}
          ]
        }}
        Analogy Data: {json.dumps(analogy_data)}
        """

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": quiz_prompt}],
            temperature=0.7,
            max_tokens=600
        )

        quiz_text = resp.choices[0].message.content.strip()
        if quiz_text.startswith("```"):
            lines = quiz_text.split("\n")
            if len(lines) >= 3:
                quiz_text = "\n".join(lines[1:-1])

        quiz_json = json.loads(quiz_text)
        return quiz_json

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",                  # required for server deployment
        port=int(os.environ.get("PORT", 8000)),  # use dynamic port or fallback to 8000 locally
        reload=True                        # optional, auto-reload for local dev
    ) 
