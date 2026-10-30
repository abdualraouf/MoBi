/**
 * MoBi POS Barcode Scanner Handler & Audio Feedback
 * Works offline with any standard USB / Wireless HID Barcode Scanner.
 */

// Web Audio API Sound Synthesizer (Zero external file dependencies)
const AudioFeedback = {
    audioCtx: null,
    
    init() {
        if (!this.audioCtx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioCtx = new AudioContext();
            }
        }
    },

    playSuccessBeep() {
        try {
            this.init();
            if (!this.audioCtx) return;
            if (this.audioCtx.state === 'suspended') {
                this.audioCtx.resume();
            }

            const osc = this.audioCtx.createOscillator();
            const gain = this.audioCtx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, this.audioCtx.currentTime); // 880Hz (A5)
            gain.gain.setValueAtTime(0.15, this.audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.1);

            osc.connect(gain);
            gain.connect(this.audioCtx.destination);

            osc.start();
            osc.stop(this.audioCtx.currentTime + 0.1);
        } catch (e) {
            console.warn("Audio feedback error:", e);
        }
    },

    playErrorBeep() {
        try {
            this.init();
            if (!this.audioCtx) return;
            if (this.audioCtx.state === 'suspended') {
                this.audioCtx.resume();
            }

            const osc = this.audioCtx.createOscillator();
            const gain = this.audioCtx.createGain();

            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(220, this.audioCtx.currentTime); // Low buzz
            gain.gain.setValueAtTime(0.2, this.audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.25);

            osc.connect(gain);
            gain.connect(this.audioCtx.destination);

            osc.start();
            osc.stop(this.audioCtx.currentTime + 0.25);
        } catch (e) {
            console.warn("Audio feedback error:", e);
        }
    }
};

// Global Barcode Buffer for Hardware HID Scanners
let barcodeBuffer = "";
let lastKeyTime = 0;

document.addEventListener("keydown", function (e) {
    const currentTime = Date.now();
    const barcodeInput = document.getElementById("barcode-scanner-input");

    // Shortcut Keys Handling
    if (e.key === "F2") {
        e.preventDefault();
        if (barcodeInput) barcodeInput.focus();
        return;
    }
    if (e.key === "F4") {
        e.preventDefault();
        const payBtn = document.getElementById("btn-complete-sale");
        if (payBtn) payBtn.click();
        return;
    }
    if (e.key === "F9") {
        e.preventDefault();
        const clearBtn = document.getElementById("btn-clear-cart");
        if (clearBtn) clearBtn.click();
        return;
    }

    // Determine if input is from a high-speed barcode reader (inter-key time < 35ms)
    const isScannerSpeed = (currentTime - lastKeyTime) < 35;
    lastKeyTime = currentTime;

    // If focused on an ordinary textarea or text input other than barcode input, don't capture unless scanner speed
    const activeEl = document.activeElement;
    const isOtherInput = activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA") && activeEl !== barcodeInput;

    if (isOtherInput && !isScannerSpeed) {
        // User is typing in another input (e.g. pos-picker-search); let native event proceed
        return;
    }

    if (e.key === "Enter") {
        if (barcodeBuffer.length >= 3) {
            e.preventDefault();
            const scannedCode = barcodeBuffer.trim();
            barcodeBuffer = "";
            handleScannedBarcode(scannedCode);
        } else if (activeEl === barcodeInput && barcodeInput.value.trim().length >= 2) {
            e.preventDefault();
            const code = barcodeInput.value.trim();
            barcodeInput.value = "";
            handleScannedBarcode(code);
        }
        return;
    }

    if (e.key.length === 1) {
        if (isScannerSpeed || activeEl === barcodeInput) {
            barcodeBuffer += e.key;
        } else {
            // Reset buffer if human typing slowly outside barcode input
            barcodeBuffer = e.key;
        }
    }
});

function handleScannedBarcode(code) {
    console.log("[Scanner] Barcode detected:", code);
    
    // Check if on POS screen
    const posContainer = document.getElementById("pos-cart-container");
    if (posContainer) {
        // Trigger HTMX post to add product (sound is played via HX-Trigger scanSuccess/scanError)
        htmx.ajax('POST', '/pos/add-item', {
            target: '#pos-cart-container',
            swap: 'outerHTML',
            values: { query: code }
        }).then(() => {
            const input = document.getElementById("barcode-scanner-input");
            if (input) {
                input.value = "";
                input.focus();
            }
        }).catch(() => {
            AudioFeedback.playErrorBeep();
        });
        return;
    }

    // Check if on Repair lookup screen
    const repairLookup = document.getElementById("repair-ticket-lookup");
    if (repairLookup) {
        window.location.href = `/repairs?search=${encodeURIComponent(code)}`;
        return;
    }
}

// Listen for server-triggered scanSuccess / scanError events from HTMX responses
document.addEventListener("scanSuccess", function () {
    AudioFeedback.playSuccessBeep();
});

document.addEventListener("scanError", function () {
    AudioFeedback.playErrorBeep();
});

// Window helper for manual audio triggers
window.MoBiAudio = AudioFeedback;
