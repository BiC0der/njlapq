import os
import re
import sys
import time
import queue
import subprocess
import threading
import shutil
import telebot
from telebot import types
import requests

IS_WINDOWS = sys.platform == "win32"

try:
    import ctypes
    from ctypes import wintypes
except Exception:
    ctypes = None
    wintypes = None



# ----------------------------------------------------
# 1. Configuration & Settings Loader
# ----------------------------------------------------
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.txt")
PROXIES_FILE = os.path.join(SCRIPT_DIR, "Proxies.txt")

BANNER = " Coded by : T.me/B_6_5  and  T.me/joubory "


def load_settings():
    settings = {}
    if not os.path.exists(SETTINGS_FILE):
        # Create a default settings file if it doesn't exist
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("# Configuration for GetVoids Telegram Bot Runner\n")
            f.write("BOT_TOKEN=your_telegram_bot_token_here\n")
            f.write("MEMBER_IDS=12345678,987654321\n")
            f.write("TOOL_NAME=C-ram void hunter\n")
            f.write("OUTPUT_FILE=14day.txt\n")
        print(f"Created default config file: {SETTINGS_FILE}. Please edit it and set your token.")
        
    # Read existing settings
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                settings[key.strip()] = val.strip()
                
    # Automatically append missing settings keys with defaults
    updated = False
    with open(SETTINGS_FILE, "a", encoding="utf-8") as f:
        if "TOOL_NAME" not in settings:
            f.write("\n# Name of the tool displayed in Telegram starting message\n")
            f.write("TOOL_NAME=C-ram void hunter\n")
            settings["TOOL_NAME"] = "C-ram void hunter"
            updated = True
        if "OUTPUT_FILE" not in settings:
            f.write("\n# Output file to send when stopped\n")
            f.write("OUTPUT_FILE=14day.txt\n")
            settings["OUTPUT_FILE"] = "14day.txt"
            updated = True
        if "DISCORD_WEBHOOK" not in settings:
            f.write("\n# Discord Webhook URL for live counter updates\n")
            f.write("DISCORD_WEBHOOK=your_discord_webhook_url_here\n")
            settings["DISCORD_WEBHOOK"] = "your_discord_webhook_url_here"
            updated = True
        if "DISCORD_PROXY" not in settings:
            f.write("\n# Optional Discord Proxy (e.g. http://127.0.0.1:1080 or leave empty for direct connection)\n")
            f.write("DISCORD_PROXY=\n")
            settings["DISCORD_PROXY"] = ""
            updated = True
        if "TARGET_CMD" not in settings:
            f.write("\n# Optional Target Command (e.g. python3 GetVoids.py or leave blank to auto-detect)\n")
            f.write("TARGET_CMD=\n")
            settings["TARGET_CMD"] = ""
            updated = True
            
    if updated:
        print("Updated settings.txt with default values for missing configuration keys.")
        
    return settings

settings = load_settings()
BOT_TOKEN = settings.get("BOT_TOKEN", "")
MEMBER_IDS_STR = settings.get("MEMBER_IDS", "")
TOOL_NAME = settings.get("TOOL_NAME", "C-ram void hunter")
OUTPUT_FILE = settings.get("OUTPUT_FILE", "14day.txt")
DISCORD_WEBHOOK = settings.get("DISCORD_WEBHOOK", "")
DISCORD_PROXY = settings.get("DISCORD_PROXY", "")
TARGET_CMD = settings.get("TARGET_CMD", "")
AUTHORIZED_USERS = set()


if MEMBER_IDS_STR:
    for x in MEMBER_IDS_STR.split(","):
        x = x.strip()
        if x.isdigit():
            AUTHORIZED_USERS.add(int(x))

if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
    print("CRITICAL: BOT_TOKEN is not configured in settings.txt. Please update the configuration.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ----------------------------------------------------
# Win32 HWND / Console Title Utility Functions
# ----------------------------------------------------
def find_console_hwnd(keyword):
    if not IS_WINDOWS:
        return None
    hwnd_found = None
    keyword_lower = keyword.lower()
    
    def enum_windows_callback(hwnd, extra):
        nonlocal hwnd_found
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 1024)
        title = buf.value
        if title and keyword_lower in title.lower():
            # Verify class name is ConsoleWindowClass
            class_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 256)
            if class_buf.value == "ConsoleWindowClass":
                hwnd_found = hwnd
                return False
        return True

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
    return hwnd_found

def get_window_text(hwnd):
    if not IS_WINDOWS or not hwnd:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 1024)
        return buf.value.strip()
    except Exception:
        return ""

def get_console_title():
    if not IS_WINDOWS:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetConsoleTitleW(buf, 1024)
        return buf.value.strip()
    except Exception:
        return ""


# ----------------------------------------------------
# 2. Keyboards (ReplyMarkup)
# ----------------------------------------------------
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_start = types.KeyboardButton("Start")
    btn_stop = types.KeyboardButton("Stop")
    btn_settings = types.KeyboardButton("Settings")
    markup.add(btn_start, btn_stop)
    markup.add(btn_settings)
    return markup

def get_settings_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_add = types.KeyboardButton("Add proxies")
    btn_show = types.KeyboardButton("Show proxies")
    btn_back = types.KeyboardButton("Back")
    markup.add(btn_add, btn_show)
    markup.add(btn_back)
    return markup

def get_back_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    btn_back = types.KeyboardButton("Back")
    markup.add(btn_back)
    return markup

# ----------------------------------------------------
# 3. Active Session Manager
# ----------------------------------------------------
class GetVoidsSession:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.proc = None
        self.state = "IDLE"  # "IDLE", "STARTING", "WAITING_FOR_LENGTH", "WAITING_FOR_THREADS", "RUNNING"
        self.reader_thread = None
        self.send_queue = queue.Queue()
        self.sender_thread = None
        self.monitor_thread = None
        self.lock = threading.Lock()
        self.stop_sender = False
        self.sent_file = False
        self.status_msg = None
        self.hwnd = None
        self.discord_msg_id = None
        self.last_discord_error_time = 0
        
        # Synchronization Events for inputs
        self.length_event = threading.Event()
        self.length_input = ""
        self.threads_event = threading.Event()
        self.threads_input = ""

    def start(self):
        with self.lock:
            if self.proc is not None:
                bot.send_message(self.chat_id, f"{TOOL_NAME} is already running!")
                return
            
            # Setup path to GetVoids.exe
            script_dir = SCRIPT_DIR
            exe_path = os.path.join(script_dir, "GetVoids.exe")
            if not os.path.exists(exe_path):
                exe_path = os.path.join(script_dir, "GetVoids")
            
            if not os.path.exists(exe_path):
                bot.send_message(self.chat_id, f"Error: GetVoids.exe not found at path: {exe_path}")
                return
                
            bot.send_message(self.chat_id, f"Starting {TOOL_NAME}...", reply_markup=get_main_keyboard())
                        # Start process with environment variables to disable stdout buffering & Wine debug noise
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["WINEDEBUG"] = "-all"
            
            popen_kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 0,
                "universal_newlines": True,
                "env": env
            }
            
            if IS_WINDOWS and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            
            try:
                if not IS_WINDOWS and shutil.which("wine"):
                    wine_cmd = ["wine", exe_path]
                    if shutil.which("xvfb-run"):
                        wine_cmd = ["xvfb-run", "-a"] + wine_cmd
                    self.proc = subprocess.Popen(wine_cmd, **popen_kwargs)
                else:
                    self.proc = subprocess.Popen([exe_path], **popen_kwargs)
            except Exception as e:
                bot.send_message(self.chat_id, f"Failed to start: {e}")
                self.proc = None
                return




            
            self.state = "STARTING"
            self.stop_sender = False
            self.sent_file = False
            self.status_msg = None
            self.hwnd = None
            self.discord_msg_id = None
            self.length_event.clear()
            self.threads_event.clear()
            
            # Wait a moment, then find the console window HWND
            time.sleep(1.0)
            self.hwnd = find_console_hwnd("GetVoids.exe")
            
            # Start stdout reader thread
            self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self.reader_thread.start()
            
            # Start message batch sender thread
            self.sender_thread = threading.Thread(target=self._batch_sender, daemon=True)
            self.sender_thread.start()

    def set_length(self, val):
        self.length_input = val
        self.length_event.set()

    def set_threads(self, val):
        self.threads_input = val
        self.threads_event.set()

    def stop(self):
        with self.lock:
            if self.proc is None:
                bot.send_message(self.chat_id, f"{TOOL_NAME} is not running.")
                return
                
            bot.send_message(self.chat_id, f"Stopping {TOOL_NAME}...")
            
            # Terminate process
            if self.proc.poll() is None:
                try:
                    if IS_WINDOWS:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        self.proc.kill()
                except Exception as e:
                    print(f"Error terminating process: {e}")

            
            # Wait for it
            self.proc.wait()
            
            # Force unblock thread if it's waiting for events
            self.length_event.set()
            self.threads_event.set()
            
            self.send_output_file()
            self._cleanup()
            bot.send_message(self.chat_id, f"{TOOL_NAME} has been stopped.", reply_markup=get_main_keyboard())

    def send_output_file(self):
        # Read the OUTPUT_FILE, copy it to List.txt, send it, and delete List.txt
        script_dir = SCRIPT_DIR
        output_path = os.path.join(script_dir, OUTPUT_FILE)
        
        if os.path.exists(output_path):
            try:
                temp_name = "List.txt"
                temp_path = os.path.join(script_dir, temp_name)
                shutil.copy2(output_path, temp_path)
                
                with open(temp_path, "rb") as f:
                    bot.send_document(self.chat_id, f)
                
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            except Exception as e:
                bot.send_message(self.chat_id, f"Failed to send output file: {e}")
        else:
            bot.send_message(self.chat_id, f"Output file '{OUTPUT_FILE}' not found on disk.")

    def _cleanup(self):
        self.proc = None
        self.state = "IDLE"
        self.stop_sender = True
        self.hwnd = None
        self.discord_msg_id = None

    def _read_stdout(self):
        buf = ""
        ansi_escape = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')
        
        while True:
            with self.lock:
                if self.proc is None or self.proc.poll() is not None:
                    break
                    
            try:
                char = self.proc.stdout.read(1)
                if not char:
                    break
                
                buf += char
                
                # 1. Look for Username Length Prompt
                if self.state == "STARTING" and "username length" in buf.lower():
                    # Send prompt to user
                    bot.send_message(self.chat_id, "Enter Username Length :")
                    buf = ""
                    with self.lock:
                        self.state = "WAITING_FOR_LENGTH"
                    
                    # Wait for user reply
                    self.length_event.wait()
                    
                    with self.lock:
                        if self.proc is None or self.proc.poll() is not None:
                            return
                        self.proc.stdin.write(self.length_input + "\n")
                        self.proc.stdin.flush()
                    self.length_event.clear()
                
                # 2. Look for Threads Prompt
                elif self.state == "WAITING_FOR_LENGTH" and "threads" in buf.lower():
                    # Send prompt to user
                    bot.send_message(self.chat_id, "Enter Number of Threads :")
                    buf = ""
                    with self.lock:
                        self.state = "WAITING_FOR_THREADS"
                    
                    # Wait for user reply
                    self.threads_event.wait()
                    
                    with self.lock:
                        if self.proc is None or self.proc.poll() is not None:
                            return
                        self.proc.stdin.write(self.threads_input + "\n")
                        self.proc.stdin.flush()
                    self.threads_event.clear()
                    
                    with self.lock:
                        self.state = "RUNNING"
                        # Send status message
                        bot.send_message(
                            self.chat_id,
                            f"*{TOOL_NAME}* is now running...\nLive counters are being sent to Discord.",
                            parse_mode="Markdown"
                        )
                        
                    # Start title monitoring thread for live counters
                    self.monitor_thread = threading.Thread(target=self._monitor_title, daemon=True)
                    self.monitor_thread.start()
                        
                else:
                    # Regular stdout line processing
                    if char in ('\n', '\r', '\x0c'):
                        line_raw = buf.strip()
                        line_clean = ansi_escape.sub('', line_raw).strip()
                        # Clean up trailing colons or empty characters to avoid ":" spam
                        if line_clean and line_clean != ":":
                            # Filter out Wine debug / setup messages
                            if any(x in line_clean for x in ["err:winediag:", "err:ole:", "wine:", "wine32", "fixme:"]):
                                buf = ""
                                continue
                            if "Voids:" in line_clean:
                                self.send_discord_counter(line_clean)
                            else:
                                self.send_queue.put(line_clean)
                        buf = ""
                    elif len(buf) > 400:
                        # Prevent infinite buffer if no newlines are printed
                        line_clean = ansi_escape.sub('', buf).strip()
                        if line_clean and line_clean != ":":
                            if any(x in line_clean for x in ["err:winediag:", "err:ole:", "wine:", "wine32", "fixme:"]):
                                buf = ""
                                continue
                            if "Voids:" in line_clean:
                                self.send_discord_counter(line_clean)
                            else:
                                self.send_queue.put(line_clean)
                        buf = ""


                        
            except Exception as e:
                print(f"Stdout reader error: {e}")
                break
                
        # Send any remaining buffer
        if buf:
            line_clean = ansi_escape.sub('', buf).strip()
            if line_clean and line_clean != ":":
                self.send_queue.put(line_clean)
                
        # Exit handling
        with self.lock:
            if self.proc is not None:
                ret = self.proc.poll()
                self.send_output_file()
                bot.send_message(self.chat_id, f"{TOOL_NAME} finished with exit code {ret}.", reply_markup=get_main_keyboard())
                self._cleanup()

    def send_discord_counter(self, title):
        global DISCORD_WEBHOOK, DISCORD_PROXY
        webhook_url = DISCORD_WEBHOOK
        if not webhook_url or webhook_url == "your_discord_webhook_url_here":
            fresh_settings = load_settings()
            webhook_url = fresh_settings.get("DISCORD_WEBHOOK", "")
            if webhook_url:
                DISCORD_WEBHOOK = webhook_url
            if fresh_settings.get("DISCORD_PROXY"):
                DISCORD_PROXY = fresh_settings.get("DISCORD_PROXY")

        if not webhook_url or webhook_url == "your_discord_webhook_url_here":
            return

        content = f"**{TOOL_NAME} - Live Counters:**\n```{title}```"
        payload = {"content": content}

        req_proxies = None
        if DISCORD_PROXY:
            req_proxies = {"http": DISCORD_PROXY, "https": DISCORD_PROXY}

        try:
            if self.discord_msg_id:
                patch_url = f"{webhook_url.rstrip('/')}/messages/{self.discord_msg_id}"
                res = requests.patch(patch_url, json=payload, timeout=(3.0, 5.0), proxies=req_proxies)
                if res.status_code == 200:
                    self.last_discord_error_time = 0
                    return
                elif res.status_code == 429:
                    try:
                        retry_after = res.json().get("retry_after", 2)
                        time.sleep(float(retry_after))
                    except Exception:
                        time.sleep(2)
                    return
                elif res.status_code == 404:
                    self.discord_msg_id = None

            post_url = webhook_url
            if "?" in post_url:
                post_url += "&wait=true"
            else:
                post_url += "?wait=true"

            res = requests.post(post_url, json=payload, timeout=(3.0, 5.0), proxies=req_proxies)
            if res.status_code in (200, 201):
                data = res.json()
                self.discord_msg_id = data.get("id")
                self.last_discord_error_time = 0
            elif res.status_code == 429:
                try:
                    retry_after = res.json().get("retry_after", 2)
                    time.sleep(float(retry_after))
                except Exception:
                    time.sleep(2)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            # Suppress network connection timeouts to prevent console spam
            now = time.time()
            if getattr(self, 'last_discord_error_time', 0) == 0 or (now - self.last_discord_error_time > 60):
                print(f"[Discord Webhook] Connection timed out. Retrying silently in background...")
                self.last_discord_error_time = now
        except Exception as e:
            now = time.time()
            if getattr(self, 'last_discord_error_time', 0) == 0 or (now - self.last_discord_error_time > 60):
                print(f"[Discord Webhook Error]: {e}")
                self.last_discord_error_time = now


    def _monitor_title(self):
        last_title = ""
        last_update_time = 0
        MIN_UPDATE_INTERVAL = 1.0  # Fast immediate updates while preventing rate limits

        while not self.stop_sender:
            if not self.hwnd:
                self.hwnd = find_console_hwnd("GetVoids.exe")
                if not self.hwnd:
                    self.hwnd = find_console_hwnd("Voids:")

            title = ""
            if self.hwnd:
                title = get_window_text(self.hwnd)
            if not title:
                title = get_console_title()

            title = title.strip()

            now = time.time()
            if title and "Voids:" in title:
                if title != last_title and (now - last_update_time >= MIN_UPDATE_INTERVAL):
                    last_title = title
                    last_update_time = now
                    self.send_discord_counter(title)

            time.sleep(0.5)


    def _batch_sender(self):
        batch = []
        last_send_time = time.time()
        
        while not self.stop_sender:
            try:
                line = self.send_queue.get(timeout=0.3)
                if line:
                    batch.append(line)
            except queue.Empty:
                pass
                
            # If batch is not empty and exceeds length or time threshold
            if batch and (len(batch) >= 15 or (time.time() - last_send_time) >= 4.0):
                text_to_send = "\n".join(batch)
                if len(text_to_send) > 4000:
                    text_to_send = text_to_send[:4000] + "\n...[truncated]"
                try:
                    bot.send_message(self.chat_id, text_to_send)
                except Exception as e:
                    print(f"Error sending batch: {e}")
                batch = []
                last_send_time = time.time()


# Global sessions & user menu states
active_sessions = {}  # chat_id -> GetVoidsSession
user_states = {}      # user_id -> state string (e.g. "WAITING_FOR_PROXIES")

# ----------------------------------------------------
# 4. Telegram Message Handlers
# ----------------------------------------------------
def check_authorized(message):
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Unauthorized user.")
        return False
    return True

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if not check_authorized(message):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_states[user_id] = "IDLE"
    bot.send_message(
        chat_id,
        f"Welcome to {TOOL_NAME} Runner! Use the buttons below to control the tool.",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda msg: True)
def handle_all_messages(message):
    if not check_authorized(message):
        return
        
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Get or create session
    session = active_sessions.get(chat_id)
    
    # ----------------------------------------------------
    # State: WAITING_FOR_LENGTH (Active run prompt)
    # ----------------------------------------------------
    if session and session.state == "WAITING_FOR_LENGTH":
        if text == "Stop":
            session.stop()
            active_sessions.pop(chat_id, None)
        else:
            session.set_length(text)
        return

    # ----------------------------------------------------
    # State: WAITING_FOR_THREADS (Active run prompt)
    # ----------------------------------------------------
    if session and session.state == "WAITING_FOR_THREADS":
        if text == "Stop":
            session.stop()
            active_sessions.pop(chat_id, None)
        else:
            session.set_threads(text)
        return

    # ----------------------------------------------------
    # State: WAITING_FOR_PROXIES (Proxy Add process)
    # ----------------------------------------------------
    if user_states.get(user_id) == "WAITING_FOR_PROXIES":
        if text == "Back":
            user_states[user_id] = "IDLE"
            bot.send_message(chat_id, "Proxy update cancelled.", reply_markup=get_settings_keyboard())
        else:
            # Overwrite Proxies.txt with user input
            try:
                proxies_path = PROXIES_FILE
                with open(proxies_path, "w", encoding="utf-8") as f:
                    f.write(message.text)
                
                # Check line count as proxy count estimate
                line_count = len([line for line in message.text.split('\n') if line.strip()])
                bot.send_message(
                    chat_id,
                    f"Proxies updated successfully! Saved {line_count} lines to {PROXIES_FILE}.",
                    reply_markup=get_settings_keyboard()
                )
            except Exception as e:
                bot.send_message(chat_id, f"Error saving proxies: {e}", reply_markup=get_settings_keyboard())
            user_states[user_id] = "IDLE"
        return

    # ----------------------------------------------------
    # Main Menu Actions
    # ----------------------------------------------------
    if text == "Start":
        if session and session.proc is not None:
            bot.send_message(chat_id, f"{TOOL_NAME} is already running!")
        else:
            session = GetVoidsSession(chat_id)
            active_sessions[chat_id] = session
            session.start()
            
    elif text == "Stop":
        if session:
            session.stop()
            active_sessions.pop(chat_id, None)
        else:
            bot.send_message(chat_id, f"{TOOL_NAME} is not running.", reply_markup=get_main_keyboard())
            
    elif text == "Settings":
        bot.send_message(chat_id, "Settings Menu:", reply_markup=get_settings_keyboard())
        
    elif text == "Back":
        # Back from settings menu to main menu
        bot.send_message(chat_id, "Main Menu:", reply_markup=get_main_keyboard())
        
    # ----------------------------------------------------
    # Settings Menu Actions
    # ----------------------------------------------------
    elif text == "Show proxies":
        proxies_path = PROXIES_FILE
        if os.path.exists(proxies_path):
            try:
                size = os.path.getsize(proxies_path)
                if size == 0:
                    bot.send_message(chat_id, "Proxies.txt is empty.")
                else:
                    with open(proxies_path, "rb") as f:
                        bot.send_document(chat_id, f, visible_file_name=PROXIES_FILE)
            except Exception as e:
                bot.send_message(chat_id, f"Failed to send proxies file: {e}")
        else:
            bot.send_message(chat_id, "Proxies.txt file does not exist.")
            
    elif text == "Add proxies":
        user_states[user_id] = "WAITING_FOR_PROXIES"
        bot.send_message(
            chat_id,
            "Please send the new proxies text. Old proxies will be deleted.\nPress Back to cancel.",
            reply_markup=get_back_keyboard()
        )
        
    else:
        bot.send_message(chat_id, "Invalid command. Please use the menu buttons.", reply_markup=get_main_keyboard())

# ----------------------------------------------------
# 5. Startup
# ----------------------------------------------------
if __name__ == "__main__":
    print(BANNER, flush=True)
    print(f"Starting {TOOL_NAME} Telegram Bot...", flush=True)
    print(f"Authorized Member IDs: {list(AUTHORIZED_USERS)}", flush=True)
    print(f"Output File Configured: {OUTPUT_FILE}", flush=True)
    print(f"Listening for messages...", flush=True)
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Bot stopped by user.", flush=True)
