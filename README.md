# rubika_bot_prcategory

بات روبیکا برای دسته‌بندی خودکار مشکلات تیکت‌ها.

هر وقت فایل اکسل با نام `Behsa_Report*` در گروه قرار بگیرد:
1. فایل دانلود می‌شود و ستون **«شماره موبایل»** حذف می‌شود (شماره‌های داخل متن تیکت هم ماسک می‌شوند).
2. یک مدل ML داخلی (TF‑IDF + Logistic Regression، بدون API خارجی) هر تیکت را دسته‌بندی می‌کند.
3. جدول خلاصه به صورت **PNG** (فونت وزیرمتن) + فایل اکسل دسته‌بندی‌شده در همان گروه ارسال می‌شود.

## اجرا
1. در روبیکا از `@botfather` بات بسازید و توکن بگیرید؛ بات را به گروه اضافه کنید (ترجیحاً ادمین).
2. `docker run -d --restart=always -v bot-data:/data -e RUBIKA_BOT_TOKEN=... ghcr.io/mr-moeini/rubika_bot_prcategory:latest`
   یا محلی: `pip install -r requirements.txt && cp .env.example .env && python -m bot.main`
3. تست روی فایل محلی بدون روبیکا: `python -m bot.demo Behsa_Report.xlsx out/`

## بهبود دقت
دسته‌ها و نمونه‌های آموزشی در `bot/data/seed_training.csv` هستند؛ ردیف جدید اضافه کنید، مدل موقع شروع دوباره آموزش می‌بیند.
تیکت‌هایی که اطمینان مدل کمتر از `MIN_CONFIDENCE` باشد در «سایر موارد» می‌روند.

## CI
`.github/workflows/ci.yml`: تست، ساخت PNG نمونه (artifact) و build/push ایمیج Docker به GHCR.
