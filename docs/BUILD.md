# ساخت و نصب

## پیشنیازها

- Python 3.10 یا بالاتر
- Kivy 2.3+
- cryptography 42+
- argon2-cffi 23+
- Pillow 10+
- pytest 8+
- برای ساخت APK: لینوکس اوبونتو ۲۲٫۰۴، JDK 17، Android SDK/NDK و Buildozer

در محیط فعلی ویندوزی Java، Android SDK، WSL و Docker موجود نیستند. به همین دلیل APK به صورت محلی ساخته نشد. workflow آمادهٔ GitHub Actions ساخت را در یک ماشین لینوکسی انجام میدهد.

## نصب وابستگیها و تست

```bash
cd private_vault
python -m pip install -r requirements.txt
python -m pytest -q
```

نتیجهٔ ثبتشده: `13 passed`.

## اجرای رابط روی دسکتاپ

```bash
python main.py
```

روی دسکتاپ، دکمهٔ «افزودن فایل» مسیر فایلها را میپرسد و «آشکارسازی» یک پوشهٔ مقصد میگیرد. این حالت فقط برای توسعه و تست است؛ در اندروید از Storage Access Framework بومی استفاده میشود.

## ساخت APK با GitHub Actions

1. محتویات پوشهٔ `private_vault` را در شاخهٔ اصلی یک مخزن GitHub قرار دهید.
2. به تب Actions بروید و workflow به نام `Build Private Vault APK` را انتخاب کنید.
3. دکمهٔ `Run workflow` را بزنید.
4. پس از اتمام، Artifact به نام `App-APK` را دانلود و از حالت فشرده خارج کنید.
5. فایل `bin/privatevault-1.0-debug.apk` را روی دستگاه اندروید نصب کنید.

workflow در مسیر `.github/workflows/build-apk.yml` قرار دارد و روی تگهای `v*` نیز به صورت خودکار اجرا میشود. این workflow بهطور خودکار python-for-android را در کامیت سازگار کپی میکند و بستهٔ `build==1.4.2` را پین میکند تا خطای معروف `setuptools.build_meta` رخ ندهد.

## ساخت محلی روی اوبونتو

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config \
  zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake \
  libffi-dev libssl-dev libltdl-dev

python3 -m pip install --upgrade pip
python3 -m pip install buildozer "cython==0.29.37"

buildozer -v android update
buildozer -v android debug
```

خروجی در `bin/*.apk` قرار میگیرد. امضای release برای انتشار در فروشگاه نیاز به تنظیمات keystore جداگانه دارد و در نسخهٔ حاضر فقط APK debug ساخته میشود.

## تنظیمات مهم buildozer.spec

| کلید | مقدار | دلیل |
|---|---|---|
| `title` | `App` | نام نمایشی درخواستشده توسط کاربر |
| `package.name` | `privatevault` | نام داخلی بسته |
| `package.domain` | `org.mehrad` | دامنهٔ بسته |
| `version` | `1.0` | نسخهٔ APK |
| `requirements` | `python3,kivy,cryptography,argon2-cffi,pyjnius,Pillow,ffpyplayer` | Kivy، AES-GCM، Argon2id، Android API، thumbnail و پخش ویدئو |
| `icon.filename` | `assets/icon.png` | آیکون ساختهشده از تصویر پیوستی |
| `android.minapi` | `24` | حداقل اندروید ۷٫۰ |
| `android.api` | `35` | هدف ساخت با SDK 35 |
| `android.ndk` | `25b` | NDK توصیهشده توسط نسخهٔ پینشدهٔ p4a |
| `p4a.commit` | `37d272cc...` | جلوگیری از FFmpeg 8 ناسازگار با ffpyplayer 4.5.1 |
| `android.permissions` | خالی | 전체 دسترسی به فایلها از طریق SAF انجام میشود |
| `android.add_resources` | `provider_paths.xml` | محدود کردن FileProvider به فایلهای موقت |
| `android.extra_manifest_application_arguments` | `provider.xml` | اضافه کردن provider به manifest |
| `android.allow_backup` | `False` | جلوگیری از پشتیبانگیری کلیدها |

## نصب و اولین اجرا

1. APK را باز کنید و نصب را تأیید کنید.
2. اپلیکیشن `App` را اجرا کنید.
3. صفحهٔ «ایجاد رمز عبور» ظاهر میشود؛ رمز عبور را دو بار وارد کنید.
4. دکمهٔ «افزودن فایل» را بزنید و عکس یا ویدئوهای موردنظر را از هر پوشهای انتخاب کنید.
5. فایلها را بررسی و سپس «شروع انتقال» را بزنید.
6. پس از اتمام، در صورت تمایل حذف نسخهٔ اصلی را تأیید کنید.

## عیبیابی

| مشکل | بررسی |
|---|---|
| Buildozer خطای Java/SDK میدهد | `%JAVA_HOME%` و SDK را طبق مستندات Buildozer تنظیم کنید یا از GitHub Actions استفاده کنید. |
| خطای `libpostproc/postprocess.h` یا `libavcodec/avfft.h` | از همان کامیت پینشدهٔ p4a و NDK 25b استفاده کنید؛ p4a develop جدیدتر FFmpeg 8 را میسازد که با ffpyplayer 4.5.1 ناسازگار است. |
| خطای `Backend 'setuptools.build_meta' is not available` یا `No module named 'math'` هنگام ساخت cryptography | workflow بستهٔ `build==1.4.2` را در `.p4a/pythonforandroid/recipe.py` پین میکند؛ در ساخت محلی همان پین را اعمال کنید یا از همان workflow استفاده کنید. |
| خطای `Android Gradle plugin requires Java 17 to run` | در GitHub Actions از `actions/setup-java@v4` با `java-version: '17'` استفاده کنید؛ در ساخت محلی `JAVA_HOME` را به JDK 17 تنظیم کنید. |
| آیکون قدیمی نمایش داده میشود | پوشهٔ `.buildozer` را حذف و دوباره بسازید. |
| قرنطینه شدن فایل توسط آنتیوایروس | از مسیر پروژهٔ محلی یا کانال رسمی استفاده کنید؛ APK debug امضای توسعه دارد. |
| قفل نشدن هنگام بازگشت از Recent Apps | تست باید روی دستگاه واقعی تکمیل شود؛ رفتار شبیهساز معتبر نیست. |
