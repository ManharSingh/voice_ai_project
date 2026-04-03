from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import whisper
from TTS.api import TTS
import uuid
import os
import requests
import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "your_super_secret_key_change_this"

# -------------------------------
# Folders
# -------------------------------
os.makedirs("static/outputs", exist_ok=True)
os.makedirs("temp", exist_ok=True)

# -------------------------------
# DATABASE
# -------------------------------
def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

# -------------------------------
# LOGIN REQUIRED DECORATOR
# -------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------
# EMAIL CONFIG (APNI EMAIL DAALNI HAI)
# -------------------------------
EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"

# IMPORTANT:
# Gmail ka normal password mat daalna
# Gmail App Password use karna

def send_otp_email(to_email, otp):
    try:
        subject = "Your Voice AI OTP Code"
        body = f"Your OTP for Voice AI login is: {otp}\n\nThis OTP is valid for a short time."

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False

# -------------------------------
# LOAD MODELS (Startup pe load honge)
# -------------------------------
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")

print("Loading TTS model...")
tts = TTS(
    model_name="tts_models/multilingual/multi-dataset/your_tts",
    progress_bar=False
)

# -------------------------------
# OLLAMA HELPER
# -------------------------------
def ask_ollama(user_text):
    """
    TinyLlama ko thoda better prompt deke answer nikalenge
    """
    system_prompt = """
You are a helpful AI assistant.

Rules:
1. Always answer the user's actual question directly.
2. Keep answers natural and useful.
3. Do NOT say things like "ask me about India only".
4. If user asks factual question, answer it normally.
5. Prefer short answers, but if needed use 1-3 sentences.
6. If asked "who is X", return the direct name first.
7. Never refuse normal general knowledge questions.
8. Do not add unnecessary extra details unless useful.
9. If user asks current affairs, answer as best as possible.
10. If unsure, say "I'm not fully sure, but..." and still try to answer.

Examples:
User: Who is the Prime Minister of India?
Assistant: Narendra Modi is the Prime Minister of India.

User: Who is the current Prime Minister of France?
Assistant: The Prime Minister of France is François Bayrou.

User: What is Python?
Assistant: Python is a popular programming language used for web development, AI, automation, and more.

Now answer the user's question properly.
"""

    payload = {
        "model": "tinyllama",
        "prompt": f"{system_prompt}\n\nUser: {user_text}\nAssistant:",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 120
        }
    }

    response = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=120
    )

    response.raise_for_status()
    data = response.json()

    ai_text = data.get("response", "").strip()

    if not ai_text:
        ai_text = "Sorry, I couldn't generate a proper response."

    # extra cleanup
    bad_lines = [
        "Ask question like",
        "Ask me the latest",
        "I can only answer",
        "only India",
        "internet for exact accuracy"
    ]

    for bad in bad_lines:
        if bad.lower() in ai_text.lower():
            ai_text = "Sorry, I couldn't answer that properly. Please try asking again."

    return ai_text

# -------------------------------
# TTS HELPER
# -------------------------------
def generate_voice(ai_text):
    output_filename = f"output_{uuid.uuid4().hex}.wav"
    output_path = os.path.join("static", "outputs", output_filename)

    tts.tts_to_file(
        text=ai_text,
        speaker_wav="voice_sample.wav",
        language="en",
        file_path=output_path
    )

    return f"/static/outputs/{output_filename}"

# -------------------------------
# AUTH ROUTES
# -------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))

        hashed_password = generate_password_hash(password)

        try:
            conn = sqlite3.connect("users.db")
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                        (username, email, hashed_password))
            conn.commit()
            conn.close()

            flash("Signup successful! Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already exists.", "error")
            return redirect(url_for("signup"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("SELECT id, username, password FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["email"] = email
            return redirect(url_for("index"))
        else:
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/send_otp", methods=["POST"])
def send_otp():
    email = request.form.get("email", "").strip().lower()

    if not email:
        flash("Please enter your email first.", "error")
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT id, username FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()

    if not user:
        flash("No account found with this email.", "error")
        return redirect(url_for("login"))

    otp = str(random.randint(100000, 999999))
    session["otp"] = otp
    session["otp_email"] = email
    session["otp_user_id"] = user[0]
    session["otp_username"] = user[1]

    sent = send_otp_email(email, otp)

    if sent:
        flash("OTP sent to your email.", "success")
    else:
        flash("Failed to send OTP. Check email settings in app.py", "error")

    return redirect(url_for("login"))

@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    entered_otp = request.form.get("otp", "").strip()

    if "otp" not in session:
        flash("Please request OTP first.", "error")
        return redirect(url_for("login"))

    if entered_otp == session.get("otp"):
        session["user_id"] = session.get("otp_user_id")
        session["username"] = session.get("otp_username")
        session["email"] = session.get("otp_email")

        session.pop("otp", None)
        session.pop("otp_email", None)
        session.pop("otp_user_id", None)
        session.pop("otp_username", None)

        flash("Logged in successfully with OTP.", "success")
        return redirect(url_for("index"))
    else:
        flash("Invalid OTP.", "error")
        return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

# -------------------------------
# MAIN PAGE
# -------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session.get("username", "User"))

# -------------------------------
# TEXT CHAT ROUTE
# -------------------------------
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    try:
        data = request.get_json()
        user_text = data.get("message", "").strip()

        if not user_text:
            return jsonify({"response": "Please type something."}), 400

        print("User typed:", user_text)

        ai_text = ask_ollama(user_text)
        audio_url = generate_voice(ai_text)

        return jsonify({
            "response": ai_text,
            "audio_url": audio_url
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "response": "Ollama is not running. Start it first."
        }), 500

    except Exception as e:
        print("TEXT CHAT ERROR:", str(e))
        return jsonify({
            "response": "Backend error occurred",
            "error": str(e)
        }), 500

# -------------------------------
# VOICE ROUTE
# -------------------------------
@app.route("/process_audio", methods=["POST"])
@login_required
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
        user_text = result["text"].strip()

        print("User said:", user_text)

        if not user_text:
            return jsonify({"response": "No speech detected"}), 400

        ai_text = ask_ollama(user_text)
        audio_url = generate_voice(ai_text)

        # cleanup
        if os.path.exists(input_path):
            os.remove(input_path)

        return jsonify({
            "user_text": user_text,
            "response": ai_text,
            "audio_url": audio_url
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "response": "Ollama is not running. Start it first."
        }), 500

    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        return jsonify({
            "response": "Backend error occurred",
            "error": str(e)
        }), 500

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)