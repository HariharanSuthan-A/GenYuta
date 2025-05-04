from flask import Flask, request, jsonify, render_template, session
import os
import requests
from datetime import datetime
from flask_session import Session
from googlesearch import search
import re
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")
app.config["SESSION_TYPE"] = "filesystem"
app.config["PERMANENT_SESSION_LIFETIME"] = 3600
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
            "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free",
            "messages": messages,
            "temperature": 0.7
        }
    )

    reply = response.json()["choices"][0]["message"]["content"]

    uncertain_phrases = [
        "i'm not sure", "i do not know", "i cannot answer", "no information",
        "unable to determine", "as an ai", "i don't have access"
    ]

    if any(p in reply.lower() for p in uncertain_phrases):
        try:
            top_link = next(search(user_msg, num_results=1))
            page_text = fetch_web_content(top_link)
            # Use LLaMA to summarize the page content instead of replying "I don't know"
            web_summary = summarize_with_llama(user_msg, page_text)
            reply = f"I searched online and found this:\n\n{web_summary}\n\n(Source: {top_link})"
        except Exception as e:
            reply = f"I couldn't find a confident answer or fetch a source. ({str(e)})"

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

def fetch_web_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    res = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(res.content, "html.parser")
    for script in soup(["script", "style", "header", "footer", "nav", "aside"]):
        script.decompose()
    text = soup.get_text(separator=' ')
    clean_text = re.sub(r'\s+', ' ', text)
    return clean_text[:3000]  # limit to 3000 chars

def summarize_with_llama(user_msg, content):
    messages = [
        {"role": "system", "content": "You are GenYuta, a helpful assistant that summarizes external content in response to user queries."},
        {"role": "user", "content": f"User asked: {user_msg}\n\nHere is some relevant content:\n{content}\n\nPlease respond to the user's question based on the content."}
    ]
    response = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            "messages": messages,
            "temperature": 0.7
        }
    )
    return response.json()["choices"][0]["message"]["content"]

def format_response(text):
    if '\n\n' in text or '\n- ' in text or '\n1. ' in text:
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
