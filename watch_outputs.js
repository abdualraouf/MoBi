const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

// المجلد الأساسي لمخرجات الـ AI
const BASE_DIR = path.join(__dirname, 'ai_outputs');
// مجلد التصاميم المصدري المراد مراقبته
const WATCH_DIR = path.join(BASE_DIR, 'diagram_sources');
// المجلد الفرعي المخصص لحفظ الصور فقط
const IMAGES_DIR = path.join(BASE_DIR, 'generated_images');

// التأكد من وجود المجلدات المطلوبة
if (!fs.existsSync(BASE_DIR)) {
    fs.mkdirSync(BASE_DIR);
}
if (!fs.existsSync(WATCH_DIR)) {
    fs.mkdirSync(WATCH_DIR);
}
if (!fs.existsSync(IMAGES_DIR)) {
    fs.mkdirSync(IMAGES_DIR);
}

console.log(`=======================================================`);
console.log(`[Automation] جاري مراقبة المجلد: ${WATCH_DIR}`);
console.log(`[Automation] سيتم حفظ الصور تلقائياً في: ${IMAGES_DIR}`);
console.log(`[Automation] عند تعديل أي ملف .drawio سيتم تصديره تلقائياً.`);
console.log(`=======================================================\n`);

// دالة تحويل ملفات Mermaid
function convertMermaid(filePath, outputPath) {
    exec(`mmdc -i "${filePath}" -o "${outputPath}"`, (error, stdout, stderr) => {
        if (error) {
            console.error(`[Error] فشل تحويل Mermaid: ${error.message}`);
            return;
        }
        console.log(`[Success] تم تحويل Mermaid بنجاح إلى: ${path.basename(outputPath)}`);
    });
}

// دالة تحويل ملفات Draw.io (باستخدام مسار التثبيت الافتراضي للويندوز)
function convertDrawIO(filePath, outputPath) {
    const defaultPath = "C:\\Program Files\\draw.io\\draw.io.exe";
    const localAppData = process.env.LOCALAPPDATA;
    const localPath = localAppData ? path.join(localAppData, 'Programs', 'draw.io', 'draw.io.exe') : '';

    let drawioExecutable = `"${defaultPath}"`;
    let found = fs.existsSync(defaultPath);

    if (!found && localPath && fs.existsSync(localPath)) {
        drawioExecutable = `"${localPath}"`;
        found = true;
    }

    if (!found) {
        console.error(`[Error] لم يتم العثور على برنامج Draw.io Desktop مثبت على هذا النظام.`);
        console.error(`[Info] المسارات التي تم فحصها:\n 1. ${defaultPath}\n 2. ${localPath}`);
        console.error(`[Info] يرجى تثبيت برنامج Draw.io Desktop للويندوز ليتم تحويل المخططات تلقائياً.`);
        return;
    }
    
    // تم إضافة معامل --scale 3 لإنتاج صور عالية الدقة (300 DPI) صالحة للمستندات المطبوعة
    console.log(`[Processing] جاري تصدير ${path.basename(filePath)} بدقة 300 DPI...`);
    exec(`${drawioExecutable} -x -f png --scale 3 -o "${outputPath}" "${filePath}"`, (error, stdout, stderr) => {
        if (error) {
            console.error(`[Error] فشل تحويل Draw.io: ${error.message}`);
            return;
        }
        console.log(`[Success] تم تحويل Draw.io بنجاح إلى: ${path.basename(outputPath)}`);
    });
}

// مؤقت لضبط تكرار الأحداث (Debounce) وتفادي قفل الملفات في ويندوز
const debounceTimers = {};

// مراقبة المجلد بحثاً عن ملفات جديدة أو معدلة
fs.watch(WATCH_DIR, (eventType, filename) => {
    if (!filename) return;

    const filePath = path.join(WATCH_DIR, filename);
    const ext = path.extname(filename).toLowerCase();
    
    // إلغاء أي مؤقت سابق لنفس الملف في حال إطلاق ويندوز لعدة أحداث متتالية أثناء الحفظ
    if (debounceTimers[filename]) {
        clearTimeout(debounceTimers[filename]);
    }

    // الانتظار 350 ميلي ثانية حتى يكتمل حفظ البرنامج للملف تماماً
    debounceTimers[filename] = setTimeout(() => {
        if (!fs.existsSync(filePath)) return;
        try {
            if (fs.lstatSync(filePath).isDirectory()) return;
        } catch (e) {
            return;
        }

        const outputName = filename.replace(ext, '.png');
        const outputPath = path.join(IMAGES_DIR, outputName);

        if (ext === '.mmd' || ext === '.mermaid') {
            console.log(`[Detected] ملف Mermaid جديد أو معدل: ${filename}`);
            convertMermaid(filePath, outputPath);
        } else if (ext === '.drawio') {
            console.log(`[Detected] ملف Draw.io تم حفظه: ${filename}`);
            convertDrawIO(filePath, outputPath);
        }
    }, 350);
});