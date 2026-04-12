from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Admin Mind Cash est en ligne !"

@app.route("/health")
def health():
    return {"status": "ok", "bot": "Mind Cash Admin"}, 200

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
