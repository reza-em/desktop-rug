# Desktop Rug · فرش دسکتاپ

A Persian rug that lives on your desktop — sweep messy files under it.

> سورس کامل داخل پوشه‌ی [`desktop-rug/`](desktop-rug/) است. باندل آماده‌ی ویندوز (exe + فایل‌های bat) در ریشه‌ی همین ریپو قرار دارد.

## ساختار ریپو

```
.
├── DesktopRug.exe              # باینری آماده ویندوز 10/11 (64-bit)
├── Enable-DesktopRug.bat / فعال‌سازی فرش.bat     # نصب + اجرای خودکار + اجرای فوری
├── Disable-DesktopRug.bat / غیرفعال‌سازی فرش.bat # بستن + حذف اجرای خودکار (تنظیمات می‌ماند)
├── Uninstall-DesktopRug.bat / حذف کامل فرش.bat   # حذف برنامه + تنظیمات
├── README_FA.txt               # راهنمای فارسی باندل ویندوز
├── DesktopRug-source-v3.zip    # آرشیو سورس
└── desktop-rug/                # سورس کامل (پایتون + CI + اسکرین‌شات‌ها)
    ├── README.md               # داک کامل (انگلیسی)
    ├── desktop_rug/            # کد اصلی
    ├── tools/                  # gen_rug.py, make_release.py, ...
    ├── packaging/              # spec, icon, README_FA_windows.txt
    ├── tests/
    └── .github/workflows/build.yml
```

## نصب سریع (ویندوز)

1. همین ریپو را دانلود/کلون کنید.
2. روی `فعال‌سازی فرش.bat` (یا `Enable-DesktopRug.bat`) دابل‌کلیک کنید — بدون نیاز به ادمین.
3. خاموش: `غیرفعال‌سازی فرش.bat` — حذف کامل: `حذف کامل فرش.bat`

جزئیات فارسی در [README_FA.txt](README_FA.txt) و داک کامل انگلیسی در [desktop-rug/README.md](desktop-rug/README.md).

## Run from source

```bash
python3 -m venv .venv && .venv/bin/pip install -r desktop-rug/requirements.txt
# optional native speed-up:
gcc -O3 -ffast-math -fno-finite-math-only -shared -fPIC -o desktop-rug/desktop_rug/native/libclothsim.so desktop-rug/desktop_rug/native/clothsim.c -lm
.venv/bin/python -m desktop_rug  # from desktop-rug/ dir, or ./run_from_source.sh
```

## License

See [desktop-rug/LICENSE](desktop-rug/LICENSE).
