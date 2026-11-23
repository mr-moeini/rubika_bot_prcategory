# rubika_bot_prcategory

بات روبیکا برای تحلیل و دسته‌بندی تیکت‌های «مشکلات بسته» (گزارش Behsa). دسته‌بندی با **ML داخلی** (TF‑IDF + Logistic Regression) و قواعد پرامپت تحلیل انجام می‌شود؛ هیچ API خارجی یا Claude استفاده نمی‌شود.

هر وقت فایل `Behsa_Report*.xlsx` در گروه قرار بگیرد:
1. ستون «شماره موبایل» حذف و شماره‌های داخل متن ماسک می‌شود.
2. فقط ردیف‌هایی که «نوع درخواست خدمات» آن‌ها با `[6] بسته ها > [6-8]` شروع می‌شود تحلیل می‌شوند (اگر فایل شامل انواع دیگر باشد، حالت کامل: ستون‌های «نوع خدمت» و «زیردسته» اضافه می‌شود و حذف‌شده‌ها «خارج از تحلیل» می‌گیرند).
3. گام ۱ پرامپت (۷ قاعده حذف) در `bot/rules.py` پیاده شده؛ گام ۲ (۱۳ دسته) با مدل ML + دو قاعده قطعی (دوشنبه سوری، عدم ارسال کد هدیه).
4. خروجی در گروه: PNG جدول خلاصه + فایل اکسل (ستون `Category` + شیت `Summerty` با فرمول COUNTIF، فونت B Nazanin و ردیف کنترل) + پیام فهرست حذف‌شده‌ها (شماره ردیف و دلیل) + فهرست مرزی/نیازمند تصمیم/تکراری.

## اجرا
- Docker: `docker run -d --restart=always -v bot-data:/data -e RUBIKA_BOT_TOKEN=... ghcr.io/mr-moeini/rubika_bot_prcategory:latest`
- محلی: `pip install -r requirements.txt && cp .env.example .env && python -m bot.main`
- بدون روبیکا، روی فایل محلی: `python -m bot.demo Behsa_Report.xlsx out/`
- بدون سرور: workflow `run-bot.yml` هر ۵ دقیقه یک بار اجرا می‌شود (secret `RUBIKA_BOT_TOKEN`، اختیاری `RUBIKA_CHAT_IDS`، و متغیر `ENABLE_SCHEDULED_BOT=true`).

توکن را از `@botfather` در روبیکا بگیرید و بات را به گروه اضافه کنید (ترجیحاً ادمین).

## بهبود دقت
نمونه‌های آموزشی در `bot/data/seed_training.csv` هستند؛ ردیف جدید اضافه کنید تا مدل موقع شروع دوباره آموزش ببیند.
آستانه‌ها: `MIN_CONFIDENCE` (زیر آن «نیازمند تصمیم»)، `BORDERLINE_CONFIDENCE` و `BORDERLINE_MARGIN` (تیکت مرزی).
