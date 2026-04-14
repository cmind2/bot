from flask import Flask

app = Flask("keep_alive")

@app.route("/")
def home():
    return "OK", 200

def keep_alive():
    """Lance Flask directement dans le thread appelant (daemon thread géré par bot.py)."""
    app.run(host="0.0.0.0", port=8080)
