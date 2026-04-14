# keep_alive.py
from flask import Flask
from threading import Thread

app = Flask("keep_alive")

@app.route("/")
def home():
    return "OK", 200

def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True)
    t.start()
