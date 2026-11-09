from flask import Flask, request, jsonify
import requests
import hmac
import hashlib
import os

app = Flask(__name__)

# ========== 設定値（環境変数で設定） ==========
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
AI_API_KEY = os.environ.get("AI_API_KEY")
AI_MODEL = "gemini-2.0-flash"

# ========== LINE webhook ==========
@app.route("/webhook", methods=["POST"])
def webhook():
    # 1. 署名検証
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    hash = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(hash, signature):
        return jsonify({"status": "error", "message": "Signature mismatch"}), 401

    # 2. メッセージを解析
    data = request.get_json()
    events = data.get("events", [])

    for event in events:
        if event.get("message") and event["message"].get("text"):
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            # 3. AIに送る
            ai_response = get_ai_response(user_message)

            # 4. LINEに返す
            send_to_line(reply_token, ai_response)

    return jsonify({"status": "ok"})


def get_ai_response(message):
    """AIにメッセージを送って回答をもらう"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}",
    }

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": message}
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    return result["candidates"][0]["content"]["parts"][0]["text"]


def send_to_line(reply_token, text):
    """LINEにメッセージを送る"""
    url = "https://api.line.me/v2/bot/message/reply"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    payload = {
        "replyToken": reply_token,
        "messages": [
            {"type": "text", "text": text}
        ],
    }

    requests.post(url, headers=headers, json=payload)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
