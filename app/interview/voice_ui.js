// Voice mode: connects the page to the ElevenLabs agent and routes its `interview_step` tool calls
// to the voice flow (voice_flow.js), which drives the same engine and clinician view as the chat.
import { Conversation } from "https://cdn.jsdelivr.net/npm/@elevenlabs/client@1.26.0/+esm";

const ui = window.TCMInterviewUI;
const startBtn = document.getElementById("voice-start");
const endBtn = document.getElementById("voice-end");
const bar = document.getElementById("voicebar");
const orb = document.getElementById("voice-orb");
const statusEl = document.getElementById("voice-status");

let conversation = null;
let flow = null;
let raf = 0;

function agentId() {
  const fromUrl = new URLSearchParams(location.search).get("agent");
  return fromUrl || (window.TCM_VOICE_CONFIG || {}).agentId || "";
}

function setStatus(text, mode) {
  statusEl.textContent = text;
  orb.className = "orb" + (mode ? " " + mode : "");
}

function pulse() {
  if (!conversation) return;
  const speaking = orb.classList.contains("speaking");
  const v = speaking ? conversation.getOutputVolume() : conversation.getInputVolume();
  orb.style.transform = "scale(" + (1 + Math.min(1, v * 3)).toFixed(2) + ")";
  raf = requestAnimationFrame(pulse);
}

function interviewStep(params) {
  const r = flow.step(params);
  ui.showUnderstood(r.findings || []);
  if (r.status === "halt") ui.halt();
  else ui.renderClinician();
  // The agent only needs what to say next; the rest stays on the page.
  return JSON.stringify({ status: r.status, say: r.say });
}

async function start() {
  const id = agentId();
  if (!id) {
    ui.say("לא הוגדר סוכן קולי. יש להוסיף agentId לקובץ voice_config.js.", "alert");
    return;
  }
  startBtn.disabled = true;
  const state = ui.beginVoice();
  flow = window.TCMVoiceFlow.createVoiceFlow(ui.engine, ui.kb, state);
  bar.hidden = false;
  setStatus("מבקש גישה למיקרופון…");
  const problem = await checkMicrophone();
  if (problem) {
    setStatus("אין גישה למיקרופון");
    showMicHelp(problem);
    endBtn.hidden = true;
    startBtn.disabled = false;
    return;
  }
  setStatus("מתחבר…");
  try {
    conversation = await Conversation.startSession({
      agentId: id,
      // WebRTC gives the best audio; ?transport=websocket works on networks that block it.
      connectionType: new URLSearchParams(location.search).get("transport") === "websocket" ? "websocket" : "webrtc",
      clientTools: { interview_step: interviewStep },
      onConnect: () => setStatus("מחובר", "listening"),
      onModeChange: ({ mode }) => setStatus(mode === "speaking" ? "יעל מדברת" : "יעל מקשיבה", mode),
      onMessage: ({ source, message }) => { if (message) ui.say(message, source === "user" ? "pt" : "sys"); },
      onError: (message) => ui.say("שגיאה בשיחה הקולית: " + message, "alert"),
      onDisconnect: ended
    });
    window.TCMVoiceSession = conversation;   // for debugging from the console
    raf = requestAnimationFrame(pulse);
  } catch (e) {
    setStatus("החיבור נכשל: " + (e && e.message ? e.message : e));
    conversation = null;
    startBtn.disabled = false;
  }
}

// ---- microphone diagnosis ----
// A web page cannot open the browser's own settings, so this names the actual blocker and links
// straight to what can be opened: the operating system's microphone privacy page, a fresh tab
// outside a preview frame, and a copyable chrome:// address.

const OS = /Windows/i.test(navigator.userAgent) ? "windows" : /Mac OS X|Macintosh/i.test(navigator.userAgent) ? "mac" : "other";
const BROWSER_SETTINGS = /Edg\//.test(navigator.userAgent) ? "edge://settings/content/microphone" : "chrome://settings/content/microphone";

function inFrame() {
  try { return window.self !== window.top; } catch (e) { return true; }
}

// Resolves to null when the microphone works, else {kind, detail}.
async function checkMicrophone() {
  // Chrome on Android opens downloaded files from content:// and never grants the microphone there.
  if (location.protocol === "content:" || (/Android/i.test(navigator.userAgent) && location.protocol === "file:")) {
    return { kind: "phonefile", detail: location.protocol };
  }
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return { kind: "insecure", detail: location.protocol };
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());   // only a check; the SDK opens its own stream
    return null;
  } catch (e) {
    const name = (e && e.name) || "Error";
    let permission = "unknown";
    try { permission = (await navigator.permissions.query({ name: "microphone" })).state; } catch (_) { /* not supported */ }
    if (name === "NotFoundError" || name === "OverconstrainedError") return { kind: "nodevice", detail: name };
    if (name === "NotReadableError" || name === "AbortError") return { kind: "busy", detail: name };
    if (name === "NotAllowedError" || name === "SecurityError") {
      if (inFrame()) return { kind: "frame", detail: name + "/" + permission };
      return { kind: permission === "denied" ? "site" : "system", detail: name + "/" + permission };
    }
    return { kind: "other", detail: name + ": " + (e.message || "") };
  }
}

function h(tag, attrs, kids) {
  const n = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  });
  (kids || []).forEach((c) => c && n.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
  return n;
}

function osSettingsButton() {
  if (OS === "windows") {
    return h("a", { class: "btn", href: "ms-settings:privacy-microphone", text: "פתיחת הגדרות המיקרופון של Windows" });
  }
  if (OS === "mac") {
    return h("a", { class: "btn", href: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
                    text: "פתיחת הגדרות המיקרופון של macOS" });
  }
  return null;
}

function copyButton(text) {
  const b = h("button", { class: "btn ghost", type: "button", text: "העתקת הכתובת " + text });
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); b.textContent = "הועתק. הדביקו בשורת הכתובת של דפדפן חדש"; }
    catch (e) { b.textContent = text; }
  });
  return b;
}

function retryButton(panel) {
  return h("button", { class: "btn", type: "button", text: "לנסות שוב",
                       onclick: () => { panel.remove(); endBtn.hidden = false; start(); } });
}

function showMicHelp(problem) {
  const old = document.getElementById("mic-help");
  if (old) old.remove();
  const panel = h("div", { class: "panel mic-help", id: "mic-help", role: "alert" });
  const steps = [];
  let title = "";
  const buttons = [];
  if (problem.kind === "frame") {
    title = "הדף פתוח בתוך תצוגה מקדימה, והיא לא מאפשרת שימוש במיקרופון.";
    steps.push("יש לפתוח את הדף בלשונית נפרדת של Chrome או Edge: להוריד את הקובץ ולפתוח אותו בלחיצה כפולה.");
    buttons.push(h("a", { class: "btn", href: location.href, target: "_blank", rel: "noopener", text: "פתיחה בלשונית חדשה" }));
  } else if (problem.kind === "site") {
    title = "הדפדפן חוסם את המיקרופון לדף הזה.";
    steps.push("ללחוץ על סמל המנעול או ההגדרות משמאל לכתובת הדף, ולשנות את \"מיקרופון\" ל\"אישור\".");
    steps.push("או להדביק את הכתובת " + BROWSER_SETTINGS + " בלשונית חדשה, ולהוריד את הדף מרשימת \"לא מורשה\".");
    steps.push("אחר כך לרענן את הדף וללחוץ שוב על \"שיחה קולית\".");
    buttons.push(copyButton(BROWSER_SETTINGS));
  } else if (problem.kind === "system") {
    title = "הדפדפן אישר, אבל מערכת ההפעלה חוסמת את המיקרופון לדפדפן.";
    steps.push(OS === "windows" ? "בהגדרות שייפתחו: להפעיל \"גישה למיקרופון\" ואת \"אפשר לאפליקציות שולחן עבודה לגשת למיקרופון\"."
      : OS === "mac" ? "בהגדרות שייפתחו: לסמן את Chrome או Edge ברשימה, ואז לסגור ולפתוח מחדש את הדפדפן."
      : "לבדוק בהגדרות הפרטיות של המערכת שלדפדפן מותר להשתמש במיקרופון.");
    steps.push("אם זה לא עוזר, לבדוק גם את הגדרת האתר בדפדפן (" + BROWSER_SETTINGS + ").");
    const os = osSettingsButton();
    if (os) buttons.push(os);
    buttons.push(copyButton(BROWSER_SETTINGS));
  } else if (problem.kind === "busy") {
    title = "המיקרופון תפוס על ידי תוכנה אחרת.";
    steps.push("לסגור תוכנות שמשתמשות במיקרופון (Zoom, Teams, WhatsApp וכדומה) ולנסות שוב.");
    const os = osSettingsButton();
    if (os) buttons.push(os);
  } else if (problem.kind === "nodevice") {
    title = "לא נמצא מיקרופון במחשב.";
    steps.push("לחבר מיקרופון או אוזניות עם מיקרופון, ולבדוק שהוא מוגדר כהתקן ברירת המחדל במערכת.");
    const os = osSettingsButton();
    if (os) buttons.push(os);
  } else if (problem.kind === "phonefile") {
    title = "בטלפון אי אפשר להשתמש במיקרופון בקובץ שהורד.";
    steps.push("Chrome באנדרואיד חוסם מיקרופון בקבצים שנפתחים מהזיכרון של הטלפון, גם כשההרשאה מאושרת.");
    steps.push("אפשר לפתוח את אותו הקובץ ב-Chrome או Edge במחשב, או להשתמש בדף בכתובת https.");
  } else if (problem.kind === "insecure") {
    title = "הדפדפן לא מאפשר מיקרופון בכתובת הזו.";
    steps.push("יש לפתוח את הקובץ ישירות מהמחשב (כתובת שמתחילה ב-file://) או מכתובת https, ב-Chrome או Edge.");
  } else {
    title = "לא הצלחנו להפעיל את המיקרופון.";
    steps.push("לבדוק את הגדרת המיקרופון בדפדפן (" + BROWSER_SETTINGS + ") ובמערכת ההפעלה, ולנסות שוב.");
    buttons.push(copyButton(BROWSER_SETTINGS));
    const os = osSettingsButton();
    if (os) buttons.push(os);
  }
  buttons.push(retryButton(panel));
  panel.appendChild(h("h3", { text: title }));
  panel.appendChild(h("ol", { class: "ev" }, steps.map((t) => h("li", { text: t }))));
  panel.appendChild(h("div", { class: "answers" }, buttons));
  panel.appendChild(h("p", { class: "voice-note", text: "פרטים טכניים: " + problem.detail }));
  bar.insertAdjacentElement("afterend", panel);
}

function ended() {
  cancelAnimationFrame(raf);
  conversation = null;
  if (flow) flow.finish();
  setStatus("השיחה הסתיימה. הסיכום מחכה בלשונית 'סיכום למטפל'.");
  orb.style.transform = "";
  endBtn.hidden = true;
  startBtn.disabled = false;
  ui.renderClinician();
}

startBtn.addEventListener("click", () => { endBtn.hidden = false; start(); });
endBtn.addEventListener("click", () => { if (conversation) conversation.endSession(); else ended(); });
