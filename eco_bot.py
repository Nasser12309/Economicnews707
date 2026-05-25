import asyncio
import logging
import sqlite3
import html
import re
from datetime import datetime
import httpx
import feedparser
from deep_translator import GoogleTranslator
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# إصلاح مشكلة التوقيت في أندرويد عبر استيراد توقيت عالمي ثابت
import pytz

# الإعدادات الخاصة بك جاهزة ومدمجة
BOT_TOKEN = "8991292693:AAGjQhTeRueFAkR8knIW3vt30UXb97z8P40"
CHANNEL_ID = "@Economicnews707"  
FETCH_INTERVAL_MINUTES = 15       

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# الروابط المستقرة والمفتوحة
ECONOMIC_SOURCES = {
    "رويترز أعمال (Reuters)": "https://www.reuters.com/arc/outboundfeeds/news-all/?outputType=xml",
    "اقتصاد CNBC العالمية": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "يورونيوز الاقتصادية": "https://arabic.euronews.com/rss?format=all&level=theme&name=business",
    "فرانس 24 اقتصاد": "https://www.france24.com/ar/اقتصاد/rss",
    "الشرق للأعمال (Bloomberg)": "https://www.asharqbusiness.com/rss"
}

def init_db():
    conn = sqlite3.connect('published_news.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE,
            published_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def is_already_published(link):
    conn = sqlite3.connect('published_news.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM news WHERE link = ?", (link,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def save_to_db(link):
    conn = sqlite3.connect('published_news.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO news (link, published_date) VALUES (?, ?)", (link, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def clean_html_tags(text):
    if not text:
        return ""
    clean_re = re.compile('<.*?>')
    return re.sub(clean_re, '', text).strip()

def translate_text(text, max_chars=500):
    try:
        if not text or len(text.strip()) == 0:
            return "اضغط على رابط المصدر لمشاهدة التفاصيل."
        trimmed_text = text[:max_chars]
        translated = GoogleTranslator(source='auto', target='ar').translate(trimmed_text)
        return translated
    except Exception as e:
        logging.error(f"خطأ أثناء الترجمة: {e}")
        return text 

def format_message(title_ar, summary_ar, source_name, original_link):
    clean_summary = html.escape(summary_ar)
    msg = (
        f"🚨 <b>خبر اقتصادي عالمي | {source_name}</b>\n\n"
        f"📌 <b>{title_ar}</b>\n\n"
        f"📝 {clean_summary}...\n\n"
        f"🌐 <a href='{original_link}'>اقرأ الخبر كاملاً من المصدر الأصلي</a>\n\n"
        f"#اقتصاد #أخبار_اقتصادية #اقتصاد_عالمي #{source_name.replace(' ', '_').replace('(', '').replace(')', '')}"
    )
    return msg

async def send_to_telegram(client, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        response = await client.post(url, json=payload)
        if response.status_code == 200:
            logging.info("تم نشر الخبر بنجاح في القناة.")
            return True
        else:
            logging.error(f"فشل إرسال الخبر لتلجرام: {response.text}")
            return False
    except Exception as e:
        logging.error(f"خطأ في الاتصال بتلجرام: {e}")
        return False

async def fetch_and_process_news():
    logging.info("بدء جلب الأخبار من المصادر العالمية المحدثة...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        for source_name, url in ECONOMIC_SOURCES.items():
            try:
                logging.info(f"يتم الآن فحص: {source_name}")
                response = await client.get(url)
                
                if response.status_code != 200:
                    logging.warning(f"تعذر جلب {source_name}، كود الحالة: {response.status_code}")
                    continue
                
                feed = feedparser.parse(response.text)
                
                for entry in feed.entries[:2]:
                    link = entry.get('link', '')
                    if not link or is_already_published(link):
                        continue
                    
                    title = entry.get('title', '')
                    summary = entry.get('summary', entry.get('description', 'اضغط على الرابط لمعرفة التفاصيل.'))
                    
                    summary_clean = clean_html_tags(summary)
                    
                    logging.info(f"خبر جديد تم العثور عليه: {title}")
                    
                    title_ar = translate_text(title, max_chars=150)
                    summary_ar = translate_text(summary_clean, max_chars=400)
                    
                    message = format_message(title_ar, summary_ar, source_name, link)
                    success = await send_to_telegram(client, message)
                    
                    if success:
                        save_to_db(link)
                        await asyncio.sleep(5)
                        
            except Exception as e:
                logging.error(f"حدث خطأ أثناء معالجة المصدر {source_name}: {e}")

# تم تصحيح السطر هنا بإضافة def بنجاح
async def main():
    init_db()
    logging.info("تم تشغيل قاعدة البيانات بنجاح.")
    
    await fetch_and_process_news()
    
    scheduler = AsyncIOScheduler(timezone=pytz.utc)
    scheduler.add_job(fetch_and_process_news, 'interval', minutes=FETCH_INTERVAL_MINUTES)
    scheduler.start()
    logging.info(f"تم تفعيل المجدول الزمني بنجاح عبر UTC. الفحص كل {FETCH_INTERVAL_MINUTES} دقيقة.")

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("تم إيقاف البوت بنجاح.")
