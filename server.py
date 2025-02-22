from flask import Flask, request, jsonify
import subprocess
import threading
import uuid
import os

app = Flask(__name__)

def start_agent(phone_number):
    """Starts a new agent session without opening a new terminal"""
    try:
        # ✅ Create a unique room ID
        room_id = f"room-{uuid.uuid4().hex[:8]}"

        # ✅ Create a new dispatch
        dispatch_command = [
            "lk", "dispatch", "create", "--new-room",
            "--room", room_id, "--agent-name", "outbound-caller", "--metadata", phone_number
        ]
        subprocess.run(dispatch_command, check=True)

        # ✅ Set environment variable for room ID
        env = os.environ.copy()
        env["ROOM_ID"] = room_id  

        # ✅ Run the agent **in the same process**, without opening a new terminal
        agent_command = ["python", "agent.py", "dev"]
        subprocess.Popen(agent_command, env=env)

        print(f"✅ Agent triggered for {phone_number} in room {room_id}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Error starting agent: {e}")

@app.route("/trigger_agent", methods=["POST"])
def trigger_agent():
    data = request.get_json()
    phone_number = data.get("phone_number")

    if not phone_number:
        return jsonify({"error": "Missing phone_number"}), 400

    threading.Thread(target=start_agent, args=(phone_number,)).start()
    return jsonify({"status": "Agent started", "phone_number": phone_number})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
