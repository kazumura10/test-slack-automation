import requests
import dotenv
import os
import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

dotenv.load_dotenv()
TOKEN = os.environ.get("BOT_TOKEN")
APP_TOKEN = os.environ.get("APP_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
openai.api_key = os.environ.get("OPENAI_API_KEY")

# 以下の情報はSlackのチャンネル情報を取得するための情報，一回のみ取得すればよい
CHANNEL = 'bot-test'

# timestampは試験的に固定値を入れている，UNIX時間(小数点以下は6桁)
TS = "1713944329.798709"
EMOJI = 'white_check_mark'
# MESSAGE_ID = '48f4b72c-1d08-45e7-9bb2-73d51bfb2ed9'

def send_message(text):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": "Bearer "+TOKEN}
    data  = {
    'channel': CHANNEL,
    'text': text
    }
    r = requests.post(url, headers=headers, data=data)
    # print("return ", r.json())

def add_reaction(token, channel, ts, emoji):
    url = "https://slack.com/api/reactions.add"
    headers = {"Authorization": "Bearer "+token}
    data  = {
    'channel': channel,
    'timestamp': ts,
    'name': emoji
    }
    r = requests.post(url, headers=headers, data=data)
    # print("return ", r.json())

def get_files(j):
    """
    ユーザ，テキスト，ファイルを取得する関数

    ・ファイルがある場合はファイル名とリンクを表示
    ・json key: filesの中身
    　・files['permalink']: Slackのリンク
    　・files['url_private']: ファイルリンク
    　・files['timestamp']: タイムスタンプ
    　・files['name']: ファイル名
    """
    if 'files' in j.keys():
        files = j['files']
        # print(files)
        for file in files:
            print("user: "+j['user'], ",text: " + j['text'], ",filename: " + str(file['name']), ",filelink: " + str(file['url_private']))
    else:
        print("user: "+j['user'],", text: " + j['text'])

def get_messages(token, channel_id, ts):
    """
    チャンネル内の全メッセージを取得する関数

    ・ts: タイムスタンプ(UNIX時間)
    ・'thread_ts'がある場合はスレッドが存在する
    ・同一スレッド内のメッセージは'thread_ts'が同じ値を持つ
    """
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": "Bearer "+token}
    data  = {
    'channel': channel_id,
    "ts" : ts
    }
    r = requests.post(url, headers=headers, data=data)
    jsons = r.json()
    for j in jsons['messages']:
        if 'thread_ts' in j.keys():
            get_thread(j)
            # テスト用：親スレッドにリアクションをつける場合，ここで呼び出せる
            # add_reaction(token, channel_id, j['thread_ts'], EMOJI)
        else:
            get_files(j)

def get_thread(message):
    """
    スレッドのメッセージを取得する関数

    ・スレッドが展開されていた（返信が付いている）場合のみ使用
    """
    url = "https://slack.com/api/conversations.replies"
    headers = {"Authorization": "Bearer "+TOKEN}
    data  = {
    'channel': CHANNEL_ID,
    'ts': message['thread_ts']
    }
    r = requests.post(url, headers=headers, data=data)
    jsons = r.json()
    for j in jsons['messages']:
        get_files(j)
    # print("return ", r.json())

MSG_PROMPT = "文脈に即した返答を作成してください。文脈：{}"
def openai_chat(content: str, prompt_template: str) -> str:
    """
    OpenAI Chat APIを使用して、GPTによる応答生成を行う関数
    """
    prompt = prompt_template.format(content)
    
    response = openai.ChatCompletion.create(
                        model = "gpt-4-turbo-2024-04-09",
                        messages = [
                            {"role": "system", "content": "あなたは優秀な回答アシスタントです。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0
                    )

    text = response['choices'][0]['message']['content']
    # history = content + text
    print(text)
    return text

# Slack Boltアプリを作成
slack_app = App(token=TOKEN)
# 履歴を保持する変数
HISTORY = ""

# app_mentionイベントを処理する
@slack_app.event("app_mention")
def mention_handler(body, say):
    """メンションが付けられた時に同じテキストをスレッドで返信する"""
    mention = body["event"]
    text = mention["text"]
    channel = mention["channel"]
    thread_ts = mention["ts"]

    print(f"メンションされました: {text}")
    res = openai_chat(text, MSG_PROMPT)

    # スレッドで返信
    say(text=res, channel=channel, thread_ts=thread_ts)

# gpt4コマンドはGPT-4による返答を返す
@slack_app.command("/gpt4")
def gpt4_command(ack, body, say):
    ack()
    text = body["text"]
    # res_url = body["response_url"]
    usr_name = body["user_name"]
    channel = body["channel_id"]
    global HISTORY

    print(f"コマンドが入力されました: {text}")
    input_text = usr_name + "さん: " + text
    if HISTORY == "":
        res = openai_chat(text, MSG_PROMPT)
    else:
        res = openai_chat(HISTORY + text, MSG_PROMPT)
    res = "Bot: " + res
    return_msg = input_text + "\n" + res
    HISTORY += return_msg + "\n"

    say(text=return_msg, channel=channel)

# echoコマンドは受け取ったテキストをそのまま返す
@slack_app.command("/echo")
def repeat_text(ack, respond, command):
    ack()
    respond(f"{command['text']}")

# resetコマンドは履歴をリセットする
@slack_app.command("/reset")
def reset_history(ack, respond):
    ack()
    global HISTORY
    HISTORY = ""
    respond("履歴をリセットしました。")

def main():
    """
    1. SlackAPIの実行
    2. Slack Boltを使ったSlack Botの実行
    1と2のどちらかを選択して実行
    """
    # 1. SlackAPIの実行
    # send_message("Hello, World!")
    get_messages(TOKEN, CHANNEL_ID, TS)

    # 2. Slack Boltを使ったSlack Botの実行
    # handler = SocketModeHandler(slack_app, APP_TOKEN)
    # handler.start()

if __name__ == '__main__':
    main()    