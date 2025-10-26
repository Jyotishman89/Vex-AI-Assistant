import os
import sys
import traceback
import importlib
from flask import Flask, request, jsonify, send_from_directory

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="",
)

process_command_return = None
try:
    ai = importlib.import_module("ai_assistant")
    process_command_return = getattr(ai, "process_command_return", None)
    print("ai_assistant imported:", bool(process_command_return))
except Exception as e:
    print("Failed to import ai_assistant:", e, file=sys.stderr)
    traceback.print_exc()

@app.route("/health")
def health():
    return jsonify({"ok": True, "ai_available": bool(process_command_return)})

@app.route("/", methods=["GET"])
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    file_path = os.path.join(STATIC_DIR, filename)
    if os.path.isfile(file_path):
        return send_from_directory(STATIC_DIR, filename)
    return send_from_directory(STATIC_DIR, "index.html")

@app.route("/api/command", methods=["POST"])
def api_command():
    try:
        data = request.get_json() or {}
        cmd = data.get("command", "").strip()
        if not cmd:
            return jsonify({"reply": "Please provide a command."}), 400

        if not process_command_return:
            return jsonify({"reply": "Assistant module not available on server (check logs)."}), 500

        try:
            reply = process_command_return(cmd)
            return jsonify({"reply": reply}), 200
        except Exception as e:
            tb = traceback.format_exc()
            print("Assistant error:\n", tb, file=sys.stderr)
            return jsonify({"reply": f"Server error while processing command: {e}"}), 500

    except Exception as ex:
        traceback.print_exc()
        return jsonify({"reply": "Unexpected server error handling request."}), 500

@app.route("/api/launch", methods=["POST"])
def api_launch():
    assistant_path = os.path.join(os.getcwd(), "ai_assistant.py")
    if not os.path.exists(assistant_path):
        return jsonify({"status": "ai_assistant.py not found"}), 404
    try:
        if os.name == "nt":
            import subprocess
            subprocess.Popen([sys.executable, assistant_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            import subprocess, signal
            subprocess.Popen([sys.executable, assistant_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
        return jsonify({"status": "Launched ai_assistant.py (dev)"}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": f"Launch failed: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
