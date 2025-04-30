# /api/slack_events.py
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import hmac
import hashlib
from urllib.parse import parse_qs # x-www-form-urlencoded をパースする場合

# 環境変数は後でVercel上で設定します
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TARGET_CHANNEL_ID = os.environ.get('TARGET_CHANNEL_ID')
MONITOR_CHANNEL_ID = os.environ.get('MONITOR_CHANNEL_ID')

# --- ★★★ Slack リクエスト署名検証関数 ★★★ ---
def verify_slack_request(headers, body_bytes):
    if not SLACK_SIGNING_SECRET:
        print('Warning: SLACK_SIGNING_SECRET is not set. Skipping verification.')
        return True # 開発中は検証をスキップする場合など

    signature = headers.get('X-Slack-Signature')
    timestamp = headers.get('X-Slack-Request-Timestamp')

    if not signature or not timestamp:
        print('Error: Missing signature or timestamp headers')
        return False

    # タイムスタンプチェック (5分以内か)
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            print('Error: Timestamp too old')
            return False
    except ValueError:
            print('Error: Invalid timestamp header')
            return False

    # 生のボディバイト列をUTF-8文字列としてデコードして使用
    sig_basestring = f"v0:{timestamp}:{body_bytes.decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(
        bytes(SLACK_SIGNING_SECRET, 'utf-8'),
        bytes(sig_basestring, 'utf-8'),
        hashlib.sha256
    ).hexdigest()

    try:
        # timing safe な比較
        return hmac.compare_digest(my_signature, signature)
    except Exception as e:
        print(f"Error comparing signatures: {e}")
        return False
# --- ここまで ---

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        # --- リクエストボディの読み取り ---
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body_bytes = self.rfile.read(content_length)
        except Exception as e:
            print(f"Error reading request body: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Internal Server Error")
            return

        # --- Slack リクエスト署名検証 (重要！) ---
        # if not verify_slack_request(self.headers, body_bytes):
        #     self.send_response(403)
        #     self.send_header('Content-type', 'text/plain')
        #     self.end_headers()
        #     self.wfile.write(b"Invalid Slack signature")
        #     return
        # --- ここまで ---

        # --- ボディのパース ---
        try:
            body_str = body_bytes.decode('utf-8')
            data = json.loads(body_str)
        except json.JSONDecodeError:
            print("Error: Could not decode JSON body")
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bad Request: Could not decode JSON")
            return
        except Exception as e:
            print(f"Error parsing request body: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Internal Server Error")
            return

        # --- Slack URL Verification ---
        if data.get('type') == 'url_verification':
            print("Handling Slack URL verification...")
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(bytes(data.get('challenge', ''), 'utf-8'))
            return

        # --- Slack イベント処理 (event_callback) ---
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            print(f"Received event: {json.dumps(event)}") # ログ出力

            # メッセージイベントの処理例 (後で詳細化)
            if (event.get('type') == 'message' and
                    'subtype' not in event and # 通常のメッセージのみ（ボットや編集などを除く）
                    event.get('channel') == MONITOR_CHANNEL_ID): # 監視対象チャンネルか？

                message_text = event.get('text', '')
                user = event.get('user')
                ts = event.get('ts') # メッセージのタイムスタンプ
                channel = event.get('channel')
                print(f"Received message: '{message_text}' from user {user} in channel {channel}")

                # --- TODO: ここに機能要望判定＆転送ロジックを実装 ---
                try:
                    # 1. Gemini で判定 (関数化すると良い)
                    # is_target_request = check_with_gemini(message_text)
                    is_target_request = "機能追加希望" in message_text # 仮の簡易判定

                    if is_target_request:
                        print("Message meets criteria, forwarding...")
                        # 2. Slack パーマリンク取得 (SDKが必要)
                        # permalink = get_permalink(channel, ts)
                        permalink = f"https://your-workspace.slack.com/archives/{channel}/p{ts.replace('.', '')}" # 仮のURL形式

                        if permalink:
                            # 3. 転送先チャンネルに投稿 (SDKが必要)
                            # post_to_slack(TARGET_CHANNEL_ID, f"プロダクトBで対応可能そうな要望がありました！\n{permalink}")
                            print(f"Would forward permalink: {permalink} to {TARGET_CHANNEL_ID}")
                    else:
                        print("Message does not meet criteria.")
                except Exception as e:
                    print(f"Error processing event logic: {e}")
                    # エラーが発生してもSlackには早めにOKを返す
                # --- ここまで ---

        # --- Slackに3秒以内にACK応答を返す ---
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")
        return

# --- Helper functions (後で実装) ---
# def check_with_gemini(text): ...
# def get_permalink(channel, ts): ...
# def post_to_slack(channel, text): ...