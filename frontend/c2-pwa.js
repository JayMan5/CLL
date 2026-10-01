import QRCode from "qrcode";
import { BrowserQRCodeReader } from "@zxing/browser";

const OPAQUE_QR_PATTERN = /^courtlog:v1:[A-Za-z0-9_-]{43}$/;
let installPrompt = null;
let scannerControls = null;
let scannerReader = null;
let scannerAllowed = false;
let scannerHandler = null;
let scanning = false;
let cameraGeneration = 0;
let initialized = false;

function setText(id, text) {
  const element = document.getElementById(id);
  if (element) element.textContent = text;
}

function setCameraButtons(active) {
  const start = document.getElementById("btn-start-camera");
  const stop = document.getElementById("btn-stop-camera");
  if (start) {
    start.classList.toggle("hidden", active);
    start.disabled = active;
  }
  if (stop) stop.classList.toggle("hidden", !active);
}

function updateNetworkStatus() {
  const status = document.getElementById("scan-network-status");
  if (!status) return;
  if (navigator.onLine === false) {
    status.textContent = "Offline — no custody scans are submitted or queued. Reconnect before checking in a file.";
    status.dataset.state = "offline";
  } else {
    status.textContent = "Online — a check-in is recorded only after CourtLOG confirms it.";
    status.dataset.state = "online";
  }
}

async function initialize() {
  if (initialized) return;
  initialized = true;

  updateNetworkStatus();
  window.addEventListener("online", updateNetworkStatus);
  window.addEventListener("offline", updateNetworkStatus);

  const installButton = document.getElementById("btn-install-pwa");
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    installPrompt = event;
    if (installButton) installButton.classList.remove("hidden");
  });
  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    if (installButton) installButton.classList.add("hidden");
    setText("pwa-install-status", "CourtLOG is installed on this device.");
  });
  if (installButton) {
    installButton.addEventListener("click", async () => {
      if (!installPrompt) {
        setText("pwa-install-status", "On iPhone or iPad, open the browser Share menu and choose Add to Home Screen.");
        return;
      }
      const prompt = installPrompt;
      installPrompt = null;
      installButton.classList.add("hidden");
      await prompt.prompt();
      const choice = await prompt.userChoice;
      setText("pwa-install-status", choice?.outcome === "accepted"
        ? "CourtLOG installation accepted."
        : "Installation was dismissed; you can install CourtLOG from your browser menu later.");
    });
  }

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/service-worker.js", { scope: "/" })
      .catch(() => console.warn("CourtLOG offline shell could not be installed."));
  }
}

async function renderQrLabel(payload, canvas) {
  if (!OPAQUE_QR_PATTERN.test(String(payload))) {
    throw new Error("The server returned an invalid opaque QR label.");
  }
  if (!(canvas instanceof HTMLCanvasElement)) {
    throw new Error("The local QR drawing surface is unavailable.");
  }
  await QRCode.toCanvas(canvas, payload, {
    errorCorrectionLevel: "M",
    margin: 3,
    width: 320,
    color: { dark: "#0b1220", light: "#ffffff" }
  });
  return canvas;
}

function setScanHandler(handler) {
  scannerHandler = typeof handler === "function" ? handler : null;
}

function setRole(role) {
  scannerAllowed = role === "Sheriff";
  if (!scannerAllowed) stopCamera();
}

function stopCamera() {
  cameraGeneration += 1;
  const controls = scannerControls;
  scannerControls = null;
  if (controls) {
    try { controls.stop(); } catch (_) { /* the stream may already be stopped */ }
  }
  const video = document.getElementById("qr-camera-video");
  if (video) {
    try { video.pause(); } catch (_) { /* jsdom and some embedded browsers omit pause */ }
    video.srcObject = null;
    video.classList.add("hidden");
  }
  setCameraButtons(false);
  if (!scanning) setText("camera-scan-status", "Camera stopped. Use the USB/manual token field if needed.");
}

async function startCamera() {
  if (!scannerAllowed) {
    setText("camera-scan-status", "Sign in with the Sheriff account assigned to the file before using camera check-in.");
    return false;
  }
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    setText("camera-scan-status", "Camera capture requires a secure HTTPS page and browser camera support. Use the USB/manual fallback if unavailable.");
    return false;
  }
  if (scannerControls) stopCamera();

  const video = document.getElementById("qr-camera-video");
  if (!video) {
    setText("camera-scan-status", "Camera preview is unavailable. Use the USB/manual fallback.");
    return false;
  }

  const generation = ++cameraGeneration;
  setText("camera-scan-status", "Requesting camera permission…");
  const startButton = document.getElementById("btn-start-camera");
  if (startButton) startButton.disabled = true;
  video.classList.remove("hidden");

  try {
    scannerReader = new BrowserQRCodeReader(undefined, {
      delayBetweenScanAttempts: 250,
      delayBetweenScanSuccess: 900,
      tryPlayVideoTimeout: 5000
    });
    const controls = await scannerReader.decodeFromConstraints(
      { audio: false, video: { facingMode: { ideal: "environment" } } },
      video,
      (result, _error) => {
        if (!result || scanning) return;
        scanning = true;
        const payload = result.getText();
        setText("camera-scan-status", "QR read. Waiting for server authorization; do not treat this as a check-in yet.");
        stopCamera();
        (async () => {
          try {
            if (!scannerHandler) {
              setText("camera-scan-status", "The check-in handler is unavailable. No scan was submitted.");
              return;
            }
            const confirmed = await scannerHandler(payload);
            setText("camera-scan-status", confirmed
              ? "CourtLOG confirmed this check-in."
              : "Not confirmed by CourtLOG. Check the status and reconnect or retry as instructed.");
          } catch (_) {
            setText("camera-scan-status", "Not confirmed by CourtLOG. No offline scan was queued; reconnect and retry.");
          } finally {
            scanning = false;
          }
        })();
      }
    );

    if (generation !== cameraGeneration) {
      controls.stop();
      return false;
    }
    scannerControls = controls;
    video.classList.remove("hidden");
    setCameraButtons(true);
    setText("camera-scan-status", "Camera is on. Hold the QR label steady inside the frame.");
    return true;
  } catch (error) {
    const name = error?.name;
    const message = name === "NotAllowedError" || name === "SecurityError"
      ? "Camera permission was denied. Allow camera access in browser settings or use the USB/manual fallback."
      : name === "NotFoundError" || name === "OverconstrainedError"
        ? "No usable camera was found. Use the USB/manual fallback."
        : name === "NotReadableError"
          ? "The camera is busy or unavailable. Close other camera apps and try again, or use the fallback."
          : "Camera could not start. Use the USB/manual fallback; no check-in was submitted.";
    video.classList.add("hidden");
    setText("camera-scan-status", message);
    return false;
  } finally {
    if (generation === cameraGeneration && startButton && !scannerControls) startButton.disabled = false;
  }
}

window.CourtLogPwa = {
  initialize,
  renderQrLabel,
  setScanHandler,
  setRole,
  startCamera,
  stopCamera
};
