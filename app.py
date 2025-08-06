from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import time
import os

app = Flask(__name__)
app.secret_key = "supersecretkey123"  # keep sessions secure
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")  # allow connections from frontend

# ----------------------------
# in-memory storage
# ----------------------------
ACTIVE_KEYS = {"MYSECRETKEY"}  # unlimited-use keys
USERS = {}  # username -> {"sid": socket_id, "role": "user"}
CHANNELS = {"general": []}  # channel_name -> list of messages

# ----------------------------
# utility functions
# ----------------------------
def clear_all_channels():
    """Clears messages in all channels every 30 minutes."""
    while True:
        time.sleep(1800)  # 30 minutes
        for channel in CHANNELS:
            CHANNELS[channel] = []
        print("[*] All channels cleared.")

threading.Thread(target=clear_all_channels, daemon=True).start()

def username_taken(username):
    return username in USERS

def validate_key(key):
    return key in ACTIVE_KEYS

# ----------------------------
# routes
# ----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        key = request.form.get("key")
        username = request.form.get("username", "").strip()

        if not validate_key(key):
            return "Invalid key!", 403
        if username_taken(username):
            return "Username already taken!", 403

        session["username"] = username
        USERS[username] = {"sid": None, "role": "user"}
        return redirect(url_for("chat"))

    return render_template("login.html")  # frontend will have login form

@app.route("/chat")
def chat():
    username = session.get("username")
    if not username or username not in USERS:
        return redirect(url_for("index"))
    return render_template("chat.html", username=username, channels=list(CHANNELS.keys()))

# ----------------------------
# socket events
# ----------------------------
@socketio.on("join")
def handle_join(data):
    username = session.get("username")
    channel = data.get("channel", "general")

    if username not in USERS:
        return

    USERS[username]["sid"] = request.sid
    join_room(channel)

    emit("chat_history", CHANNELS.get(channel, []))
    emit("user_list", [{"username": u, "role": USERS[u]["role"]} for u in USERS], broadcast=True)

@socketio.on("send_message")
def handle_message(data):
    username = session.get("username")
    channel = data.get("channel", "general")
    message = data.get("message", "").strip()

    if not message or username not in USERS:
        return

    msg_data = {"user": username, "msg": message, "role": USERS[username]["role"]}
    CHANNELS.setdefault(channel, []).append(msg_data)
    emit("receive_message", msg_data, room=channel)

@socketio.on("private_message")
def handle_private_message(data):
    sender = session.get("username")
    target = data.get("target")
    message = data.get("msg", "").strip()

    if target in USERS and USERS[target]["sid"]:
        emit("receive_private", {"from": sender, "msg": message}, room=USERS[target]["sid"])

@socketio.on("disconnect")
def handle_disconnect():
    username = None
    for user, info in USERS.items():
        if info.get("sid") == request.sid:
            username = user
            break
    if username:
        USERS.pop(username)
        emit("user_list", [{"username": u, "role": USERS[u]["role"]} for u in USERS], broadcast=True)

# ----------------------------
# run app
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # railway sets PORT automatically
    print(f"[*] Starting chat server on port {port}...")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
