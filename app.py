from flask import Flask, request, jsonify
import requests
import hmac
import hashlib
import base64
import os

app = Flask(__name__)

# ========== 設定値（環境変数で設定） ==========
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
AI_MODEL = os.environ.get("AI_MODEL", "gemini-2.5-flash").strip()

# ========== LINE webhook ==========
@app.route("/webhook", methods=["POST"])
def webhook():
    # 1. 署名検証
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    mac = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    )
    expected_b64 = base64.b64encode(mac.digest()).decode("utf-8")

    if not hmac.compare_digest(expected_b64, signature):
        return jsonify({"status": "error", "message": "Signature mismatch"}), 401

    # 2. メッセージを解析
    data = request.get_json(silent=True) or {}
    events = data.get("events", [])

    for event in events:
        if event.get("message") and event["message"].get("text"):
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            # 3. AIに送る
            try:
                ai_response = get_ai_response(user_message)
            except Exception as e:
                print(f"AI Error: {e}", flush=True)
                ai_response = f"AIエラーが発生しました:\n{e}"

            # 4. LINEに返す
            send_to_line(reply_token, ai_response)

    return jsonify({"status": "ok"})


def get_ai_response(message):
    """AIにメッセージを送って回答をもらう（Google AI Studio / Vertex AI 両対応）"""
    if not AI_API_KEY:
        raise ValueError("環境変数 AI_API_KEY が設定されていません。")

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
    headers = {"Content-Type": "application/json"}

    # AQ. で始まるキー（GCP/Vertex AI キー）と AIza で始まるキー（Google AI Studio）の両方、
    # および最新の gemini-2.5-flash モデルに自動対応するエンドポイント候補
    endpoints = [
        f"https://aiplatform.googleapis.com/v1/publishers/google/models/{AI_MODEL}:generateContent?key={AI_API_KEY}",
        f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent?key={AI_API_KEY}",
        f"https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.0-flash-001:generateContent?key={AI_API_KEY}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={AI_API_KEY}",
    ]

    last_error = ""
    for url in endpoints:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.ok:
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        last_error = f"[{response.status_code}] {response.text[:300]}"
        print(f"Endpoint failed ({url.split('?')[0]}): {last_error}", flush=True)

    raise RuntimeError(last_error)


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
            {"type": "text", "text": text[:4900]}
        ],
    }

    res = requests.post(url, headers=headers, json=payload, timeout=15)
    if not res.ok:
        print(f"LINE Reply Error: {res.status_code} {res.text}", flush=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
