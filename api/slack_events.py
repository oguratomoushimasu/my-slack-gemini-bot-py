# /api/slack_events.py
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import hmac
import hashlib
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
# import google.generativeai as genai # ★Gemini関連をコメントアウト

# 環境変数
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
# GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # ★Gemini関連をコメントアウト
TARGET_CHANNEL_ID = os.environ.get('TARGET_CHANNEL_ID')
MONITOR_CHANNEL_ID = os.environ.get('MONITOR_CHANNEL_ID')

# --- Slackクライアント初期化 ---
try:
    slack_client = WebClient(token=SLACK_BOT_TOKEN)
    print("Slack client initialized.")
except Exception as e:
    print(f"Error initializing Slack client: {e}")
    slack_client = None
# --- ここまで ---

# --- Geminiクライアント初期化 (コメントアウト) ---
# try:
#     genai.configure(api_key=GEMINI_API_KEY)
#     gemini_model = genai.GenerativeModel('gemini-pro')
#     print("Gemini client initialized.")
# except Exception as e:
#     print(f"Error initializing Gemini client: {e}")
#     gemini_model = None
# --- ここまで ---

# --- 署名検証関数 (変更なし) ---
def verify_slack_request(headers, body_bytes):
    # (前回実装したコードのまま)
    if not SLACK_SIGNING_SECRET: return True # 安全のため、実装済みならコメントアウトを推奨
    signature = headers.get('X-Slack-Signature')
    timestamp = headers.get('X-Slack-Request-Timestamp')
    if not signature or not timestamp: return False
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5: return False
    except ValueError: return False
    sig_basestring = f"v0:{timestamp}:{body_bytes.decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(bytes(SLACK_SIGNING_SECRET,'utf-8'), bytes(sig_basestring,'utf-8'), hashlib.sha256).hexdigest()
    try: return hmac.compare_digest(my_signature, signature)
    except Exception: return False
# --- ここまで ---

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        print("--- Function handler started ---")
        # ... (リクエスト読み取り、署名検証、ボディパース、URL検証 - 前回のコードのまま) ...
        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length)
        if not verify_slack_request(self.headers, body_bytes): # 署名検証は有効にしておく
             self.send_response(403); self.end_headers(); self.wfile.write(b"Invalid Slack signature"); return
        try: data = json.loads(body_bytes.decode('utf-8'))
        except Exception: self.send_response(400); self.end_headers(); self.wfile.write(b"Bad Request"); return
        if data.get('type') == 'url_verification':
             self.send_response(200); self.send_header('Content-type','text/plain'); self.end_headers(); self.wfile.write(bytes(data.get('challenge',''),'utf-8')); return
        # --- ここまで省略 ---

        # --- イベント処理 ---
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            received_channel_id = event.get('channel')

            # 監視対象チャンネルからのメッセージか？
            if (event.get('type') == 'message' and
                    'subtype' not in event and
                    received_channel_id == MONITOR_CHANNEL_ID):

                message_text = event.get('text', '') # 一応取得はしておく
                user = event.get('user')
                ts = event.get('ts')
                print(f"Received message from MONITOR channel ({MONITOR_CHANNEL_ID}): '{message_text}'")

                # --- ★★★ テスト用: 無条件で転送処理を実行 ★★★ ---
                try:
                    if not slack_client:
                        print("Error: Slack client not initialized.")
                        return # 早期リターン

                    if not TARGET_CHANNEL_ID:
                         print("Error: TARGET_CHANNEL_ID is not set.")
                         return # 早期リターン

                    # 1. 元メッセージのパーマリンク取得
                    print(f"Getting permalink for channel {received_channel_id}, ts {ts}")
                    permalink_response = slack_client.chat_getPermalink(
                        channel=received_channel_id,
                        message_ts=ts
                    )
                    permalink = permalink_response.get('permalink')
                    print(f"Got permalink: {permalink}")

                    if permalink:
                        # 2. 転送先チャンネルに投稿
                        post_message = f"【テスト】監視チャンネルからのメッセージです！\n{permalink}" # テストであることがわかるように
                        print(f"Posting to channel {TARGET_CHANNEL_ID}: {post_message}")
                        slack_client.chat_postMessage(
                            channel=TARGET_CHANNEL_ID,
                            text=post_message,
                            unfurl_links=True # リンクを展開表示
                        )
                        print("Message forwarded successfully (for testing).")
                    else:
                        print("Error: Could not get permalink.")

                except SlackApiError as e:
                    # Slack APIのエラーを具体的に表示
                    print(f"Slack API Error during forwarding test: {e.response['error']}")
                    print(f"Needed scope: {e.response.get('needed')}, Provided scope: {e.response.get('provided')}") # スコープ不足の場合に役立つ
                except Exception as e:
                    print(f"Error during forwarding test: {e}")
                # --- ここまで ---

        # --- ACK応答 ---
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")
        return