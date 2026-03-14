import os
import logging
import threading
from flask import Flask, render_template, jsonify, request
from automation import run_automation_phase1, run_automation_phase2

# =========================
# Ensure logs directory exists
# =========================
base_dir = os.path.dirname(os.path.abspath(__file__))
logs_dir = os.path.join(base_dir, "logs")
os.makedirs(logs_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(logs_dir, 'app.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

# =========================
# Global State
# =========================
automation_result = {"status": "idle"}
automation_lock = threading.Lock()

# Holds the live WebDriver between phase 1 and phase 2
active_driver = None
active_start_time = None


# =========================
# Phase 1 Thread
# =========================
def phase1_thread(username, password):
    global automation_result, active_driver, active_start_time

    try:
        logging.info("Phase 1 thread started")
        result = run_automation_phase1(username, password)

        with automation_lock:
            if result["status"] == "waiting_for_otp":
                # Keep driver reference; strip it from the public result
                active_driver = result.pop("driver")
                active_start_time = result.pop("start_time")
            automation_result = result

        logging.info(f"Phase 1 thread finished with status: {result['status']}")

    except Exception as e:
        logging.exception("Unexpected error in phase 1 thread")
        with automation_lock:
            automation_result = {
                "status": "error",
                "message": str(e),
                "data": "",
                "execution_time": "0 seconds"
            }


# =========================
# Phase 2 Thread
# =========================
def phase2_thread(driver, otp_code, start_time):
    global automation_result, active_driver, active_start_time

    try:
        logging.info("Phase 2 thread started")
        result = run_automation_phase2(driver, otp_code, start_time)

        with automation_lock:
            active_driver = None
            active_start_time = None
            automation_result = result

        logging.info(f"Phase 2 thread finished with status: {result['status']}")

    except Exception as e:
        logging.exception("Unexpected error in phase 2 thread")
        with automation_lock:
            active_driver = None
            active_start_time = None
            automation_result = {
                "status": "error",
                "message": str(e),
                "data": "",
                "execution_time": "0 seconds"
            }


# =========================
# Routes
# =========================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/run', methods=['POST'])
def run_automation_endpoint():
    global automation_result, active_driver, active_start_time

    with automation_lock:
        current_status = automation_result.get("status")
        if current_status in ("running", "waiting_for_otp"):
            return jsonify({"status": current_status})

        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({
                "status": "error",
                "message": "Username and password are required",
                "data": "",
                "execution_time": "0 seconds"
            })

        # Clean up any leftover driver from a previous failed session
        if active_driver:
            try:
                active_driver.quit()
            except Exception:
                pass
            active_driver = None
            active_start_time = None

        automation_result = {"status": "running"}

    thread = threading.Thread(
        target=phase1_thread,
        args=(username, password),
        daemon=True
    )
    thread.start()

    logging.info("Phase 1 started via /run endpoint")
    return jsonify({"status": "running"})


@app.route('/submit-otp', methods=['POST'])
def submit_otp_endpoint():
    global automation_result, active_driver, active_start_time

    with automation_lock:
        if automation_result.get("status") != "waiting_for_otp":
            return jsonify({
                "status": "error",
                "message": "لا توجد جلسة OTP نشطة حالياً",
                "data": "",
                "execution_time": "0 seconds"
            })

        data = request.get_json()
        otp_code = (data.get("otp") or "").strip()

        if not otp_code:
            return jsonify({
                "status": "error",
                "message": "الرجاء إدخال كود OTP",
                "data": "",
                "execution_time": "0 seconds"
            })

        driver_ref = active_driver
        start_time_ref = active_start_time
        automation_result = {"status": "running"}

    thread = threading.Thread(
        target=phase2_thread,
        args=(driver_ref, otp_code, start_time_ref),
        daemon=True
    )
    thread.start()

    logging.info("Phase 2 started via /submit-otp endpoint")
    return jsonify({"status": "running"})


@app.route('/status')
def get_status():
    with automation_lock:
        # Never expose the driver object to the client
        safe = {k: v for k, v in automation_result.items() if k != "driver"}
        return jsonify(safe)


# =========================
# Run App
# =========================
if __name__ == '__main__':
    logging.info("Starting Flask server on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)