
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
    today_date = datetime.datetime.now(jst).date()

    def fmt(lst):
        if not lst: return "なし"
        return " / ".join([f"{c} {n}" for c,n in lst][:10])

    hashtags = " ".join(pick_hashtags(today_date))
    text = (
        f"\n"
        f"S高: {fmt(s_high)}\n"
        f"S安: {fmt(s_low)}\n"
        f"出典: 株探（{src_title or '本日のストップ高/安'}）\n"
        f"{hashtags}"
    )
    return text[:270]  # 270文字に収める（余裕を持たせてMAX280文字）


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

# ===== ここから追記 =====
def pick_hashtags(today):
    """
    曜日でタグを自動ローテ（AI系は避ける）
    月・木: デイトレ/スイング勢
    火・金: 兼業投資家
    水: 初心者〜中級者
    ※ HASHTAG_SET=1/2/3 で強制指定、EXTRA_TAGSで追タグ可（半角スペース区切り）
    """
    set1 = ["#株探", "#ストップ高", "#ストップ安", "#デイトレ", "#スイングトレード", "#注目銘柄", "#毎日投稿"]
    set2 = ["#株探", "#ストップ高", "#ストップ安", "#株式投資", "#投資メモ", "#株ニュース", "#フォロワー募集中"]
    set3 = ["#株探", "#ストップ高", "#ストップ安", "#株初心者", "#注目銘柄", "#今日の株", "#株クラフォロー歓迎"]

    # 環境変数で強制切替（1/2/3）
    forced = os.getenv("HASHTAG_SET")
    if forced in {"1", "2", "3"}:
        base = {"1": set1, "2": set2, "3": set3}[forced]
    else:
        wd = today.weekday()  # Mon=0 ... Sun=6
        if wd in (0, 3):   # 月・木
            base = set1
        elif wd in (1, 4): # 火・金
            base = set2
        else:              # 水・土・日（実行は平日のみ想定）
            base = set3

    extra = (os.getenv("EXTRA_TAGS") or "").strip()
    if extra:
        base = base + extra.split()

    # 5〜7個程度に抑える（念のため7個に丸める）
    return base[:7]
# ===== 追記ここまで =====

