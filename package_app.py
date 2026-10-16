import os
import subprocess
import sys

def build():
    print("=" * 60)
    print("   MoBi - سكريبت تجميع التطبيق وإنتاج ملف MoBi.exe")
    print("=" * 60)

    # Use virtualenv python if available
    python_cmd = sys.executable

    print("\n[1/2] جاري تشغيل PyInstaller لبناء الملف التنفيذي المستقل...")
    cmd = [python_cmd, "-m", "PyInstaller", "--noconfirm", "mobi.spec"]
    
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n[2/2] ✅ تم إنتاج الملف التنفيذي بنجاح في مجلد: dist/MoBi.exe")
        print("يمكنك الآن نسخ ملف MoBi.exe إلى جهاز العميل وتشغيله مباشرة دون الحاجة لتثبيت بايثون!")
    else:
        print("\n❌ حدث خطأ أثناء التجميع عبر PyInstaller.")

if __name__ == "__main__":
    build()
