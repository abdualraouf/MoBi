const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

// ==========================================
// إعدادات المسارات والمجلدات
// ==========================================
const DIAGRAMS_DIR = path.join(__dirname, 'diagrams');

// البحث عن مسار تشغيل برنامج Draw.io Desktop في نظام ويندوز
function getDrawioExecutable() {
    const candidates = [
        "C:\\Program Files\\draw.io\\draw.io.exe",
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'draw.io', 'draw.io.exe'),
        "C:\\Program Files (x86)\\draw.io\\draw.io.exe"
    ];

    for (const p of candidates) {
        if (fs.existsSync(p)) {
            return p;
        }
    }
    return null;
}

const drawioPath = getDrawioExecutable();

if (!drawioPath) {
    console.error("❌ لم يتم العثور على برنامج Draw.io Desktop مثبت على جهازك.");
    console.error("المسارات المفحوصة:\n - C:\\Program Files\\draw.io\\draw.io.exe\n - %LOCALAPPDATA%\\Programs\\draw.io\\draw.io.exe");
    process.exit(1);
}

// دالة تحويل ملف .drawio إلى .png باستخدام spawn لضمان سرعة واستقرار العملية في ويندوز
function convertDrawIO(inputFilePath, outputFilePath, callback) {
    if (!fs.existsSync(inputFilePath)) {
        console.error(`[Error] الملف غير موجود: ${inputFilePath}`);
        if (callback) callback(false);
        return;
    }

    const fileName = path.basename(inputFilePath);
    console.log(`[Processing] جاري تصدير ${fileName} بدقة عالية (300 DPI)...`);

    // إعداد المعاملات: -x للتصدير، -f png، --scale 3 لجودة عالية
    const args = ['-x', '-f', 'png', '--scale', '3', '-o', outputFilePath, inputFilePath];

    const child = spawn(drawioPath, args, {
        stdio: 'inherit',
        windowsHide: true
    });

    child.on('error', (err) => {
        console.error(`[Error] فشل تشغيل Draw.io: ${err.message}`);
        if (callback) callback(false);
    });

    child.on('close', (code) => {
        if (code === 0) {
            console.log(`✅ [Success] تم تصدير المخطط بنجاح إلى:\n   -> ${outputFilePath}\n`);
            if (callback) callback(true);
        } else {
            console.error(`❌ [Failed] فشل التصدير مع كود: ${code}`);
            if (callback) callback(false);
        }
    });
}

// دالة تحويل جميع المخططات الموجودة في مجلد diagrams
function convertAllDiagrams() {
    console.log("=======================================================");
    console.log("   MoBi - أداة تحويل وتصدير مخططات Draw.io إلى PNG");
    console.log(`   مسار البرنامج: ${drawioPath}`);
    console.log("=======================================================\n");

    if (!fs.existsSync(DIAGRAMS_DIR)) {
        console.log(`المجلد غير موجود، جاري إنشاؤه: ${DIAGRAMS_DIR}`);
        fs.mkdirSync(DIAGRAMS_DIR, { recursive: true });
    }

    const files = fs.readdirSync(DIAGRAMS_DIR).filter(f => f.endsWith('.drawio'));

    if (files.length === 0) {
        console.log(`لا توجد ملفات .drawio في مجلد ${DIAGRAMS_DIR}`);
        return;
    }

    console.log(`تم العثور على ${files.length} مخطط، جاري التحويل:\n`);

    files.forEach(file => {
        const input = path.join(DIAGRAMS_DIR, file);
        const output = path.join(DIAGRAMS_DIR, file.replace(/\.drawio$/i, '.png'));
        convertDrawIO(input, output);
    });
}

// نمط المراقبة التلقائية (Watcher Mode)
function startWatcher() {
    console.log("=======================================================");
    console.log(`[Watcher] جاري مراقبة مجلد المخططات: ${DIAGRAMS_DIR}`);
    console.log(`[Watcher] بمجرد حفظ أي تعديل في Draw.io سيتم تحديث صورة الـ PNG فوراً...`);
    console.log("=======================================================\n");

    const debounceTimers = {};

    fs.watch(DIAGRAMS_DIR, (eventType, filename) => {
        if (!filename || !filename.endsWith('.drawio')) return;

        const input = path.join(DIAGRAMS_DIR, filename);
        const output = path.join(DIAGRAMS_DIR, filename.replace(/\.drawio$/i, '.png'));

        if (debounceTimers[filename]) {
            clearTimeout(debounceTimers[filename]);
        }

        debounceTimers[filename] = setTimeout(() => {
            if (!fs.existsSync(input)) return;
            console.log(`\n[Detected] تم رصد تعديل على الملف: ${filename}`);
            convertDrawIO(input, output);
        }, 350);
    });
}

// ==========================================
// نقطة الدخول (Entry Point)
// ==========================================
const args = process.argv.slice(2);

if (args.includes('--watch') || args.includes('-w')) {
    // تشغيل وضع المراقبة التلقائية
    convertAllDiagrams();
    startWatcher();
} else if (args.length > 0 && !args[0].startsWith('-')) {
    // تحويل ملف محدد تم تمريره كمعامل
    const targetFile = path.resolve(args[0]);
    const outputFile = targetFile.replace(/\.drawio$/i, '.png');
    convertDrawIO(targetFile, outputFile);
} else {
    // تحويل جميع الملفات في المجلد
    convertAllDiagrams();
}
