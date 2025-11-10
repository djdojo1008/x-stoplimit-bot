# bot/main.py
import os, re, sys, datetime, requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter, Retry

# === 設定 ===
SESSION = os.getenv("SESSION", "前場")  # "前場" or "後場"
USER_AGENT = "Mozilla/5.0 (compatible; XStopLimitBot/1.0)"
KABUTAN_BASE = "https://kabutan.jp"
SEARCH_URL = "https://kabutan.jp/news/marketnews/"

# === HTTP共通 ===
session = requests.Session()
retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
session.mount("https://", HTTPAdapter(max_retries=retry))
HDRS = {"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"}

# ===== ユーティリティ =====
def ensure_env(keys):
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        print(f"[ENV ERROR] 未設定: {', '.join(missing)}", file=sys.stderr)
        sys.exit(3)

def is_market_holiday():
    """土日または日本の祝日ならTrueを返す"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(jst).date()

    # 土日
    if today.weekday() >= 5:
        return True

    # 日本の祝日判定（jpholidayが無ければ土日判定のみで通す）
    try:
        import jpholiday
        return jpholiday.is_holiday(today)
    except ImportError:
        print("[WARN] jpholidayが未インストールのため祝日判定をスキップ")
        return False

# ===== データ取得 =====
def find_latest_article(session_word):
    """株探のニュース一覧から『本日の【ストップ高／ストップ安】 前場/後場』の最新記事URLを探す"""
    res = session.get(SEARCH_URL, headers=HDRS, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    anchors = soup.select("a")
    pat = re.compile(rf"^本日の【ストップ高／ストップ安】\s*{re.escape(session_word)}$")
    for a in anchors:
        t = a.get_text(strip=True)
        href = a.get("href") or ""
        if pat.search(t) and href.startswith("/news/marketnews/"):
            return t, KABUTAN_BASE + href
    return None, None

def parse_stops(article_url):
    """記事本文から ストップ高/安 の銘柄をDOMベースで抽出（4〜5桁対応）"""
    res = session.get(article_url, headers=HDRS, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    def grab(heading_kw):
        h = soup.find(lambda tag: tag.name in ("h2", "h3", "strong") and heading_kw in tag.get_text())
        if not h:
            return []
        items, seen = [], set()
        for sib in h.find_all_next(["p", "li", "div"], limit=150):
            txt = sib.get_text(" ", strip=True)
            if "●" in txt and heading_kw not in txt and ("ストップ高" in txt or "ストップ安" in txt):
                break
            m = re.search(r"[＜<]([0-9]{4,5})[＞>]", txt) or re.search(r"\b([0-9]{4,5})\b", txt)
            code = m.group(1) if m else None
            name = re.sub(r"[＜<].*?[＞>]", "", txt)
            name = re.sub(r"[\s/・,:：-]+$", "", name).strip()
            if code and name and code not in seen:
                items.append((code, name))
                seen.add(code)
        return items[:20]

    s_high = grab("ストップ高")
    s_low  = grab("ストップ安")
    return s_high, s_low

# ===== 投稿本文生成 =====
def build_post(session_word, s_high, s_low, src_title, article_url):
    """280字以内。長ければ銘柄件数→ハッシュタグの順に圧縮して収める。"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today_date = datetime.datetime.now(jst).date()

    def fmt_list(lst, keep):
        if not lst:
            return "なし"
        show = lst[:keep]
        return " / ".join([f"{c} {n}" for c, n in show])

    hashtags = " ".join(pick_hashtags(today_date))
    header = f"【{today_date:%Y/%m/%d} {session_word}のストップ高/安】"
    url_line = f"\n詳報: {article_url}"

    keep_high = 10
    keep_low  = 10

    while True:
        body = (
            f"{header}\n"
            f"S高: {fmt_list(s_high, keep_high)}\n"
            f"S安: {fmt_list(s_low,  keep_low)}\n"
            f"出典: 株探（{src_title or '本日のストップ高/安'}）\n"
            f"{hashtags}"
        )
        text = body + url_line

        if len(text) <= 280:
            return text

        if keep_high > 1:
            keep_high -= 1
            continue
        if keep_low > 1:
            keep_low -= 1
            continue

        short_tags = " ".join(hashtags.split()[:5])
        text = (
            f"{header}\n"
            f"S高: {fmt_list(s_high, keep_high)}\n"
            f"S安: {fmt_list(s_low,  keep_low)}\n"
            f"出典: 株探（{src_title or '本日のストップ高/安'}）\n"
            f"{short_tags}"
        ) + url_line

        return text[:280]

# ===== X投稿 =====
def post_to_x(status_text):
    import tweepy
    client = tweepy.Client(
        consumer_key=os.environ["TW_API_KEY"],
        consumer_secret=os.environ["TW_API_SECRET"],
        access_token=os.environ["TW_ACCESS_TOKEN"],
        access_token_secret=os.environ["TW_ACCESS_SECRET"],
    )
    try:
        client.create_tweet(text=status_text)
    except Exception as e:
        print(f"[X POST ERROR] {e}", file=sys.stderr)
        sys.exit(2)

# ===== メイン =====
def main():
    # 市場休場日のスキップ（週末＋祝日）
    if is_market_holiday():
        print("市場休場日のため投稿スキップ")
        return

    title, url = find_latest_article(SESSION)
    if not url:
        print("該当記事が見つかりませんでした。時間をあけて再実行してください。", file=sys.stderr)
        sys.exit(1)

    s_high, s_low = parse_stops(url)
    if not s_high and not s_low:
        print("抽出結果が空のため投稿スキップ（記事フォーマット変更の可能性）", file=sys.stderr)
        sys.exit(0)

    post = build_post(SESSION, s_high, s_low, title or "本日のストップ高/安", url)
    print(post)
    print(f"[LEN]={len(post)}")

    if os.getenv("DRY_RUN") == "1":
        return

    ensure_env(["TW_API_KEY", "TW_API_SECRET", "TW_ACCESS_TOKEN", "TW_ACCESS_SECRET"])
    post_to_x(post)

if __name__ == "__main__":
    main()

# ===== ハッシュタグローテ =====
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

    forced = os.getenv("HASHTAG_SET")
    if forced in {"1", "2", "3"}:
        base = {"1": set1, "2": set2, "3": set3}[forced]
    else:
        wd = today.weekday()
        if wd in (0, 3):   # 月・木
            base = set1
        elif wd in (1, 4): # 火・金
            base = set2
        else:              # 水・土・日
            base = set3

    extra = (os.getenv("EXTRA_TAGS") or "").strip()
    if extra:
        base = base + extra.split()
    return base[:7]
