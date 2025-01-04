import google.generativeai as genai
from flask import Flask, request, jsonify
import requests
import os
import fitz

# متغيرات البيئة
wa_token = os.environ.get("WA_TOKEN")
genai.configure(api_key=os.environ.get("GEN_API"))
phone_id = os.environ.get("PHONE_ID")
name = "Your name or nickname"
bot_name = "Give a name to your bot"
model_name = "gemini-1.5-flash-latest"

app = Flask(__name__)

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 0,
    "max_output_tokens": 8192,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

model = genai.GenerativeModel(model_name=model_name,
                              generation_config=generation_config,
                              safety_settings=safety_settings)

conversations = {}  # تخزين المحادثات بناءً على الرقم

def send(answer, recipient_phone):
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {
        'Authorization': f'Bearer {wa_token}',
        'Content-Type': 'application/json'
    }
    data = {
        "messaging_product": "whatsapp",
        "to": f"{recipient_phone}",
        "type": "text",
        "text": {"body": f"{answer}"},
        "context": {
            "externalAdReply": {
                "title": "My Instagram Profile",
                "body": "Visit my profile",
                "thumbnailUrl": "https://via.placeholder.com/150",  # صورة مصغرة (اختيارية)
                "sourceUrl": "https://instagram.com/nvm2p",  # رابط مخفي
                "mediaType": 1,
                "renderLargerThumbnail": False
            }
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response

def remove(*file_paths):
    for file in file_paths:
        if os.path.exists(file):
            os.remove(file)

@app.route("/", methods=["GET", "POST"])
def index():
    return "Bot"

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == "BOT":
            return challenge, 200
        else:
            return "Failed", 403
    elif request.method == "POST":
        try:
            data = request.get_json()["entry"][0]["changes"][0]["value"]["messages"][0]
            phone = data["from"]  # استخراج الرقم

            if phone not in conversations:
                conversations[phone] = model.start_chat(history=[])

            convo = conversations[phone]

            if data["type"] == "text":
                prompt = data["text"]["body"]
                convo.send_message(prompt)
                send(convo.last.text, phone)
            else:
                media_url_endpoint = f'https://graph.facebook.com/v18.0/{data[data["type"]]["id"]}/'
                headers = {'Authorization': f'Bearer {wa_token}'}
                media_response = requests.get(media_url_endpoint, headers=headers)
                media_url = media_response.json()["url"]
                media_download_response = requests.get(media_url, headers=headers)

                if data["type"] == "document":
                    doc = fitz.open(stream=media_download_response.content, filetype="pdf")
                    for _, page in enumerate(doc):
                        destination = "/tmp/temp_image.jpg"
                        pix = page.get_pixmap()
                        pix.save(destination)
                        file = genai.upload_file(path=destination, display_name="tempfile")
                        response = model.generate_content(["What is this", file])
                        answer = response._result.candidates[0].content.parts[0].text
                        convo.send_message(f"This message is created by an llm model based on the image prompt of user, reply to the user based on this: {answer}")
                        send(convo.last.text, phone)
                        remove(destination)
                else:
                    filename = f"/tmp/temp_{data['type']}.tmp"
                    with open(filename, "wb") as temp_media:
                        temp_media.write(media_download_response.content)
                    file = genai.upload_file(path=filename, display_name="tempfile")
                    response = model.generate_content(["What is this", file])
                    answer = response._result.candidates[0].content.parts[0].text
                    convo.send_message(f"This is a {data['type']} message transcribed by an LLM model: {answer}")
                    send(convo.last.text, phone)
                    remove(filename)

        except Exception as e:
            print(f"Error: {e}")
        return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=True, port=8000)
