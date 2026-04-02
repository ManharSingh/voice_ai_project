from flask import Flask, render_template, request, jsonify
import whisper
from TTS.api import TTS
import uuid
import os
import requests
import re

app = Flask(__name__)

# -------------------------------
# Setup
# -------------------------------
os.makedirs("static", exist_ok=True)
os.makedirs("temp", exist_ok=True)

VOICE_SAMPLE = "voice_sample.wav"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "tinyllama"

# -------------------------------
# Load Models
# -------------------------------
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")

print("Loading TTS model...")
tts = TTS(
    model_name="tts_models/multilingual/multi-dataset/your_tts",
    progress_bar=False
)

# -------------------------------
# Manual factual answers (important)
# -------------------------------
FACTS = {
    "who is the prime minister of india": "Narendra Modi.",
    "who is the current prime minister of india": "Narendra Modi.",
    "prime minister of india": "Narendra Modi.",

    "who is the president of india": "Droupadi Murmu.",
    "who is the current president of india": "Droupadi Murmu.",
    "president of india": "Droupadi Murmu.",

    "what is the capital of india": "New Delhi.",
    "capital of india": "New Delhi.",

    "who is the prime minister of france": "François Bayrou.",
    "who is the current prime minister of france": "François Bayrou.",
    "prime minister of france": "François Bayrou.",

    "who is the president of france": "Emmanuel Macron.",
    "who is the current president of france": "Emmanuel Macron.",
    "president of france": "Emmanuel Macron.",

    "what is the capital of france": "Paris.",
    "capital of france": "Paris.",

    "what is the capital of japan": "Tokyo.",
    "capital of japan": "Tokyo.",

    "what is the capital of usa": "Washington, D.C.",
    "capital of usa": "Washington, D.C.",
    "what is the capital of united states": "Washington, D.C.",
    "capital of united states": "Washington, D.C.",

    "who is the president of usa": "Donald Trump.",
    "who is the current president of usa": "Donald Trump.",
    "president of usa": "Donald Trump.",
    "who is the president of united states": "Donald Trump.",
    "who is the current president of united states": "Donald Trump.",
    "president of united states": "Donald Trump.",

    "who invented the telephone": "Alexander Graham Bell.",
    "who invented telephone": "Alexander Graham Bell.",
    "who invented the light bulb": "Thomas Edison.",
    "who invented light bulb": "Thomas Edison.",
    "who discovered gravity": "Isaac Newton.",
    "who discovered penicillin": "Alexander Fleming.",
}

# -------------------------------
# Helpers
# -------------------------------
def clean_text(text):
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text

def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text

def is_factual_question(text):
    q = normalize(text)
    triggers = [
        "who is", "what is", "capital of", "prime minister",
        "president", "who invented", "who discovered",
        "who was", "where is", "when did"
    ]
    return any(t in q for t in triggers)

def manual_answer(text):
    q = normalize(text)

    if q in FACTS:
        return FACTS[q]

    for key, value in FACTS.items():
        if key in q:
            return value

    return None

def clean_ai_output(text):
    if not text:
        return "I am not sure."

    text = clean_text(text)

    # unwanted junk remove
    junk = [
        "as an ai",
        "i am an ai",
        "i'm an ai",
        "i do not have internet",
        "i don't have internet",
        "i cannot browse",
        "i can't browse",
        "ask me the latest",
        "exact accuracy",
        "real-time information",
        "this may change",
        "this changes often"
    ]

    lower = text.lower()
    for j in junk:
        if j in lower:
            return "I am not sure."

    # only first 2 sentences
    parts = re.split(r'(?<=[.!?])\s+', text)
    text = " ".join(parts[:2]).strip()

    # max length control
    words = text.split()
    if len(words) > 45:
        text = " ".join(words[:45])

    if text and text[-1] not in ".!?":
        text += "."

    return text

# -------------------------------
# Ollama call
# -------------------------------
def ask_ollama(user_text):
    prompt = f"""
You are a helpful AI assistant.

IMPORTANT RULES:
1. Answer accurately.
2. If the question asks for a person, give the correct person's name first.
3. If the question asks for a capital, give the city name first.
4. Do not say "As an AI".
5. Do not mention internet or browsing.
6. Keep answers useful and natural.
7. If unsure, say: I am not sure.

User: {user_text}
Assistant:
""".strip()

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.7,
                "num_predict": 120,
                "repeat_penalty": 1.15
            }
        },
        timeout=90
    )

    response.raise_for_status()
    data = response.json()
    ai_text = data.get("response", "").strip()
    return clean_ai_output(ai_text)

# -------------------------------
# Final Answer Logic
# -------------------------------
def get_best_answer(user_text):
    user_text = clean_text(user_text)

    # 1) Manual factual answers first
    ans = manual_answer(user_text)
    if ans:
        return ans

    # 2) If factual but not in DB, ask tinyllama carefully
    if is_factual_question(user_text):
        return ask_ollama(user_text)

    # 3) Normal question
    return ask_ollama(user_text)

# -------------------------------
# TTS
# -------------------------------
def generate_voice(text):
    output_filename = f"output_{uuid.uuid4().hex}.wav"
    output_path = os.path.join("static", output_filename)

    tts.tts_to_file(
        text=text,
        speaker_wav=VOICE_SAMPLE,
        language="en",
        file_path=output_path
    )

    return f"/static/{output_filename}"

# -------------------------------
# Routes
# -------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process_audio", methods=["POST"])
def process_audio():
    try:
        print("Audio received")

        if "audio" not in request.files:
            return jsonify({"response": "No audio file received"}), 400

        audio_file = request.files["audio"]
        input_path = os.path.join("temp", f"user_input_{uuid.uuid4().hex}.wav")
        audio_file.save(input_path)

        print("Transcribing...")
        result = whisper_model.transcribe(input_path)
        user_text = clean_text(result["text"])

        print("User said:", user_text)

        if not user_text:
            return jsonify({"response": "No speech detected"}), 400

        print("Getting answer...")
        ai_text = get_best_answer(user_text)
        print("AI response:", ai_text)

        print("Generating voice...")
        audio_url = generate_voice(ai_text)

        try:
            os.remove(input_path)
        except:
            pass

        return jsonify({
            "user_text": user_text,
            "response": ai_text,
            "audio_url": audio_url
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "response": "Ollama is not running. Start Ollama first."
        }), 500

    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        return jsonify({
            "response": "Backend error occurred",
            "error": str(e)
        }), 500

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_text = clean_text(data.get("message", ""))

        if not user_text:
            return jsonify({"response": "Empty message"}), 400

        print("Text input:", user_text)

        print("Getting answer...")
        ai_text = get_best_answer(user_text)
        print("AI response:", ai_text)

        print("Generating voice...")
        audio_url = generate_voice(ai_text)

        return jsonify({
            "response": ai_text,
            "audio_url": audio_url
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "response": "Ollama is not running. Start Ollama first."
        }), 500

    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        return jsonify({
            "response": "Backend error occurred",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True)