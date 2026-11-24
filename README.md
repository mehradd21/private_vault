# Private Vault — اپلیکیشن اندرویدی گنجینه خصوصی

نام نمایشی اپلیکیشن: **App**  
آیکون اپلیکیشن از تصویر پیوستی (`apple-app-store--v2.jpg`) ساخته شده و در `assets/icon.png` قرار دارد.

اپلیکیشنی استاندارد و قابل نصب روی اندروید برای نگهداری خصوصی عکس و ویدئو:

- انتخاب فایل از هر پوشه قابل دسترس گوشی از طریق **Android Storage Access Framework**.
- ذخیره در **Internal App Storage** (`Context.getFilesDir()/vault/...`)، نه حافظه عمومی و نه `Android/data`.
- رمزنگاری **AES-256-GCM** به صورت بلوکی (چانکهای ۲۵۶ کیلوبایتی) با Nonce تصادفی و Authentication Tag مستقل برای هر چانک.
- مشتقسازی کلید با **Argon2id** و نگهداری کلید اصلی (Vault Master Key) توسط **Android Keystore** (با پشتیبانی امنیتی در نسخههای قدیمیتر).
- قفل فوری هنگام رفتن به پسزمینه، خاموش شدن صفحه، بازگشت از Recent Apps و قفل خودکار پس از عدم فعالیت.
- FLAG_SECURE برای جلوگیری از Screenshot/ضبط صفحه و نمایش محتوای خنثی در Recent Apps.
- گالری داخلی RTL فارسی با تب تصاویر/ویدئوها/مخفی، جستجو، مرتبسازی، چندانتخابی، نمایش تمامصفحه، پخش ویدئو، تغییر نام، حذف، مخفیسازی، خروج (Export) و «باز کردن با» از طریق FileProvider.
- حذف نسخه اصلی تنها با تأیید صریح کاربر و پس از اعتبارسنجی فایل رمزنگاریشده.

## ساختار پروژه

```
private_vault/
├── main.py                     # نقطه ورود
├── buildozer.spec              # تنظیمات Buildozer (عنوان = App)
├── android/                    # FileProvider manifest + provider_paths.xml
├── assets/                     # آیکون ساختهشده از تصویر پیوستی
├── vaultapp/
│   ├── app.py                  # Kivy App، ناوبری، Intentها و قفل
│   ├── core/
│   │   ├── crypto.py           # AES-GCM استریمینگ، Argon2id، KeyEnvelope
│   │   ├── keystore.py         # Android Keystore / بکاند تست
│   │   ├── auth.py             # رمز عبور، تلاش ناموفق، session و قفل
│   │   ├── database.py         # SQLite بدون کلید یا رمز عبور
│   │   ├── vault.py            # Import/Export/حذف اتمیک و فایلهای موقت
│   │   ├── media.py            # Thumbnail و مدت ویدئو
│   │   ├── android_api.py      # SAF، FileProvider و Intentها
│   │   ├── lifecycle.py        # FLAG_SECURE و قفل پسزمینه
│   │   └── service.py          # دروازهٔ مورد استفاده UI
│   ├── ui/                     # صفحات و ویجتهای Kivy (فارسی/RTL)
│   └── utils/                  # مسیرها، تشخیص نوع فایل، رشتهها
├── tests/                      # تستهای crypto/auth/vault/database
└── docs/                       # معماری امنیتی، ساخت و گزارش تست
```

## اجرای تستها (روی PC)

```bash
cd private_vault
python -m pip install -r requirements.txt
python -m pytest -q
```

همچنین میتوانید رابط را روی دسکتاپ تست کنید:

```bash
python main.py
```

روی دسکتاپ، «افزودن فایل» یک مسیر فایل میپرسد و «آشکارسازی» یک پوشه مقصد میگیرد؛ روی اندروید بهجای آن file picker بومی اندروید باز میشود.

## ساخت APK

Buildozer به صورت بومی فقط روی لینوکس پشتیبانی میشود. سریعترین مسیر، استفاده از GitHub Actions است:

1. پوشه `private_vault` را در یک مخزن GitHub قرار دهید.
2. workflow موجود در `.github/workflows/build-apk.yml` را اجرا کنید (`workflow_dispatch`).
3. فایل `App-APK` را از قسمت Artifacts دانلود کنید (`bin/privatevault-1.0-debug.apk`).

یا روی یک ماشین اوبونتو:

```bash
sudo apt install git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config \
     zlib1g-dev libncurses5-dev libncursesw5-dev cmake libffi-dev libssl-dev libltdl-dev
pip install --upgrade buildozer "cython==0.29.37"
buildozer -v android debug
```

خروجی: `bin/*.apk`.

> **توضیح مهم در مورد محیط فعلی:** در محیط ویندوزی که کدها در آن نوشته شدند، Java، Android SDK و WSL نصب نیستند و Buildozer قادر به ساخت APK نمیباشد. بنابراین فایل APK در این محیط تولید نشد؛ کد کامل، تنظیمات ساخت و workflow خودکار ساخت APK تحویل داده شده است.

## نکات امنیتی مهم

مستندات کامل: [معماری](docs/ARCHITECTURE.md)، [امنیت](docs/SECURITY.md)، [ساخت و نصب](docs/BUILD.md) و [گزارش تست](docs/TEST_REPORT.md).

هیچ امنیت مطلق وجود ندارد: این اپلیکیشن در برابر Root، دسترسی فیزیکی پیشرفته، استخراج حافظه یا حذف خود اپلیکیشن مقاوم نیست و چنین ادعایی نمیکند.
