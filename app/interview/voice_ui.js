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
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setStatus("אין גישה למיקרופון. יש לאשר מיקרופון בדפדפן ולנסות שוב.");
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
