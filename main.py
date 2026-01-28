from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright
import threading
import time
import random
import gc
import os

app = Flask(__name__)
app.secret_key = "sujal_hawk_playwright_nc_2026"

state = {"running": False, "changed": 0, "logs": [], "start_time": None}
cfg = {
    "sessionid": "",
    "thread_ids": [],
    "names": [],
    "nc_delay": 60,
}

# Device rotation (mobile emulation)
DEVICES = [
    {"name": "Pixel 9 Pro", "width": 1080, "height": 2400, "scale": 3.0,
     "ua": "Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"},
    {"name": "Galaxy S24 Ultra", "width": 1080, "height": 2340, "scale": 3.0,
     "ua": "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"},
    {"name": "OnePlus 12", "width": 1080, "height": 2400, "scale": 3.0,
     "ua": "Mozilla/5.0 (Linux; Android 15; CPH2653) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"},
]

def log(msg, important=False):
    entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
    if important:
        entry = f"★★★ {entry} ★★★"
    state["logs"].append(entry)
    print(entry)
    gc.collect()

def change_group_name(page, thread_id, new_name):
    try:
        page.goto(f"https://www.instagram.com/direct/t/{thread_id}/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(random.randint(3000, 6000))

        # Open info button
        page.click("svg[aria-label='Conversation information']", timeout=20000)
        page.wait_for_timeout(2000)

        # Click 'Change'
        page.click("xpath=//div[contains(text(),'Change')]", timeout=15000)
        page.wait_for_timeout(2000)

        # Input field
        page.fill("xpath=//input[@aria-label='Group name']", new_name)
        page.wait_for_timeout(1000)

        # Save
        page.click("xpath=//div[contains(text(),'Save')]", timeout=15000)
        page.wait_for_timeout(3000)

        log(f"NC SUCCESS → {new_name} for thread {thread_id}", important=True)
        state["changed"] += 1
        return True

    except Exception as e:
        log(f"NC FAILED for {thread_id}: {str(e)[:100]}")
        return False

def nc_loop():
    with sync_playwright() as p:
        while state["running"]:
            log("New NC cycle started")

            # Pick random device
            device = random.choice(DEVICES)
            log(f"Using device: {device['name']}")

            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-infobars",
                "--window-size=1080,2400"
            ])

            context = browser.new_context(
                user_agent=device["ua"],
                viewport={"width": device["width"], "height": device["height"]},
                device_scale_factor=device["scale"],
                is_mobile=True,
                has_touch=True,
                locale="en-US",
                timezone_id="Asia/Kolkata",
                permissions=["geolocation"],
                geolocation={"latitude": 25.5941, "longitude": 85.1376},  # Patna approx
                ignore_https_errors=True
            )

            page = context.new_page()

            # Set sessionid cookie
            context.add_cookies([{
                "name": "sessionid",
                "value": cfg["sessionid"],
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "None"
            }])

            page.goto("https://www.instagram.com/direct/inbox/", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(6000)

            # Login check
            if "login" in page.url or "accounts/login" in page.url or "log in" in page.content().lower():
                log("LOGIN FAILED - Redirected or login form detected", important=True)
            else:
                log("LOGIN SUCCESS - Inbox loaded", important=True)

            # Rotate name
            name_idx = 0  # or use cycle % len if needed
            new_name = cfg["names"][name_idx]

            for thread_id in cfg["thread_ids"]:
                success = change_group_name(page, thread_id, new_name)
                if not success:
                    log("Retrying same thread...")
                    page.reload()
                    time.sleep(5)
                    change_group_name(page, thread_id, new_name)

                time.sleep(5)

            cycle += 1  # optional if you want cycle count

            # Clean up
            context.close()
            browser.close()
            gc.collect()
            log("Browser closed, memory cleaned")
            time.sleep(cfg["nc_delay"])

    log("NC LOOP STOPPED")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    global state, cfg
    state["running"] = False
    time.sleep(1)

    state = {"running": True, "changed": 0, "logs": ["STARTED"], "start_time": time.time()}

    accounts_raw = request.form["accounts"].strip().split("\n")
    cfg["sessionid"] = accounts_raw[0].split(":")[0].strip()
    cfg["thread_ids"] = [line.split(":")[1].strip() for line in accounts_raw if line.strip()]

    cfg["names"] = [n.strip() for n in request.form["names"].split("\n") if n.strip()]
    cfg["nc_delay"] = float(request.form.get("nc_delay", "60"))

    threading.Thread(target=nc_loop, daemon=True).start()
    log(f"STARTED NC LOOP WITH {len(cfg['thread_ids'])} GROUPS")

    return jsonify({"ok": True})

@app.route("/stop")
def stop():
    state["running"] = False
    log("STOPPED BY USER")
    return jsonify({"ok": True})

@app.route("/status")
def status():
    uptime = "00:00:00"
    if state.get("start_time"):
        t = int(time.time() - state["start_time"])
        h, r = divmod(t, 3600)
        m, s = divmod(r, 60)
        uptime = f"{h:02d}:{m:02d}:{s:02d}"
    return jsonify({
        "running": state["running"],
        "changed": state["changed"],
        "uptime": uptime,
        "logs": state["logs"][-100:]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
