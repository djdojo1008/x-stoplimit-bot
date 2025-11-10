
# bot/main.py
import os, re, sys, datetime, requests
from bs4 import BeautifulSoup

# === 設定 ===
SESSION = os.getenv("SESSION", "前場")  # "前場" or "後場"
USER_AGENT = "Mozilla/5.0 (compatible; XStopLimitBot/1.0)"

KABUTAN_BASE = "https://kabutan.jp"
SEARCH_URL = "https://kabutan.jp/news/marketnews/"

def find_latest_article(session_word):
    """株探のニュース一覧から『本日の【ストップ高／ストップ安】 前場/後場』の最新記事URLを探す"""
    res = requests.get(SEARCH_URL, headers={"User-Agent": USER_AGENT}, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    anchors = soup.select("a")
    pat = re.compile(r"本日の【ストップ高／ストップ安】\\s*" + re.escape(session_word))
    for a in anchors:
        t = (a.get_text() or "").strip()
        href = a.get("href") or ""
        if pat.search(t) and href.startswith("/news/marketnews/"):
            return t, KABUTAN_BASE + href
    return None, None

def parse_stops(article_url):
    """記事本文から ストップ高/安 の銘柄を素朴に抽出"""
    res = requests.get(article_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    text = soup.get_text("\\n")

    def extract(block_title):
        m = re.search(block_title + r"\\s*([\\s\\S]+?)\\n\\n", text)
        if not m:
            return []
        block = m.group(1)
        items, seen = [], set()
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            m1 = re.search(r"[＜<]([0-9]{4})[＞>]", line) or re.search(r"\\b([0-9]{4})\\b", line)
            code = m1.group(1) if m1 else None
            name = re.sub(r"[＜<].*?[＞>]", "", line)
            name = re.sub(r"[\\s/・,:：-]+$", "", name).strip()
            if code and name and code not in seen:
                items.append((code, name))
                seen.add(code)
        return items[:20]
    s_high = extract("●ストップ高の銘柄一覧")
    s_low  = extract("●ストップ安の銘柄一覧")
    return s_high, s_low

def build_post(session_word, s_high, s_low, src_title):
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(jst).date().isoformat()

    def fmt(lst):
        if not lst: return "なし"
        return " / ".join([f"{c} {n}" for c,n in lst][:10])

    text = (
        f"【{session_word}のストップ高/安 {today}】\\n"
        f"S高: {fmt(s_high)}\\n"
        f"S安: {fmt(s_low)}\\n"
        f"出典: 株探（{src_title}）\\n"
        f"#日本株 #ストップ高 #ストップ安"
    )
    return text[:270]

def post_to_x(status_text):
    """tweepy(v1.1) で投稿"""
    import tweepy
    api_key = os.environ["TW_API_KEY"]
    api_secret = os.environ["TW_API_SECRET"]
    access_token = os.environ["TW_ACCESS_TOKEN"]
    access_secret = os.environ["TW_ACCESS_SECRET"]
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api = tweepy.API(auth)
    api.update_status(status_text)

def main():
    title, url = find_latest_article(SESSION)
    if not url:
        print("該当記事が見つかりませんでした。時間をあけて再実行してください。", file=sys.stderr)
        sys.exit(1)
    s_high, s_low = parse_stops(url)
    post = build_post(SESSION, s_high, s_low, title or "本日のストップ高/安")
    print(post)  # ログに出す
    post_to_x(post)

if __name__ == "__main__":
    main()
