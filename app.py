# app.py
from flask import Flask, request, jsonify
import importlib
import sys
import traceback

app = Flask(__name__, static_folder="static", static_url_path="")

# Try to import process_command_return from ai_assistant
AI_AVAILABLE = False
process_command_return = None

try:
    m = importlib.import_module("ai_assistant")
    process_command_return = getattr(m, "process_command_return", None)
    if process_command_return is None:
        raise AttributeError("ai_assistant.process_command_return not found")
    AI_AVAILABLE = True
    print("Imported ai_assistant.process_command_return successfully")
except Exception:
    print("Failed to import process_command_return from ai_assistant:", file=sys.stderr)
    traceback.print_exc()
    # keep process_command_return as None; API will return descriptive error

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/command", methods=["POST"])
def api_command():
    data = request.get_json() or {}
    cmd = data.get("command", "").strip()
    if not cmd:
        return jsonify({"reply": "Please provide a command."}), 400

    if not process_command_return:
        return jsonify({"reply": "Error processing command: process_command_return is not defined (check server logs)."}), 500

    try:
        reply = process_command_return(cmd)
        return jsonify({"reply": reply}), 200
    except Exception as e:
        # return the error text so frontend shows useful info
        return jsonify({"reply": f"Error processing command: {e}"}), 500

if __name__ == "__main__":
    print("Starting Flask app. AI_AVAILABLE =", AI_AVAILABLE)
    app.run(debug=True, port=5000)
