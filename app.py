from flask import Flask, request, jsonify, render_template, session
import os
import requests
from datetime import datetime
from flask_session import Session
import re

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")
app.config["SESSION_TYPE"] = "filesystem"
app.config["PERMANENT_SESSION_LIFETIME"] = 3600  # 1 hour session lifetime
Session(app)

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

@app.before_request
def initialize_chat():
    if 'chat_sessions' not in session:
        session['chat_sessions'] = {}
    
    if not session['chat_sessions']:
        new_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
        session['chat_sessions'][new_session_id] = {
            'created_at': datetime.now().isoformat(),
            'messages': [{
                "role": "system", 
                "content": "You are GenYuta, a helpful assistant. Always break your responses into clear, digestible points with proper spacing between ideas."
            }]
        }
        session['current_session'] = new_session_id

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.json.get("message", "")
    session_id = request.json.get("session_id", session.get('current_session'))
    
    session['chat_sessions'][session_id]['messages'].append({
        "role": "user",
        "content": user_msg
    })
    
    messages = session['chat_sessions'][session_id]['messages']
    
    response = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "meta-llama/Llama-Vision-Free",
            "messages": messages,
            "temperature": 0.7
        }
    )

    reply = response.json()["choices"][0]["message"]["content"]
    formatted_reply = format_response(reply)
    
    session['chat_sessions'][session_id]['messages'].append({
        "role": "assistant",
        "content": formatted_reply
    })
    
    session.modified = True
    
    return jsonify({
        "reply": formatted_reply,
        "session_id": session_id
    })

def format_response(text):
    if '\n\n' in text or '\n- ' in text or '\n* ' in text or '\n1. ' in text:
        return text
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    paragraphs = []
    current_para = []
    char_count = 0
    
    for sentence in sentences:
        current_para.append(sentence)
        char_count += len(sentence)
        if (len(current_para) >= 2 and char_count > 100) or len(current_para) >= 3:
            paragraphs.append(' '.join(current_para))
            current_para = []
            char_count = 0
    
    if current_para:
        paragraphs.append(' '.join(current_para))
    
    return '\n\n'.join(paragraphs) if len(paragraphs) > 1 else text

@app.route("/sessions", methods=["GET"])
def get_sessions():
    return jsonify({
        "sessions": session.get('chat_sessions', {}),
        "current_session": session.get('current_session')
    })

@app.route("/session/new", methods=["POST"])
def new_session():
    new_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    session['chat_sessions'][new_session_id] = {
        'created_at': datetime.now().isoformat(),
        'messages': [{
            "role": "system", 
            "content": "You are GenYuta, a helpful assistant. Provide responses in clear, organized points."
        }]
    }
    session['current_session'] = new_session_id
    session.modified = True
    return jsonify({
        "session_id": new_session_id,
        "created_at": session['chat_sessions'][new_session_id]['created_at']
    })

@app.route("/session/<session_id>", methods=["GET"])
def get_session(session_id):
    if session_id in session.get('chat_sessions', {}):
        session['current_session'] = session_id
        session.modified = True
        return jsonify(session['chat_sessions'][session_id])
    return jsonify({"error": "Session not found"}), 404

# ✅ This is important for Render to work correctly:
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT automatically
    app.run(host="0.0.0.0", port=port)
