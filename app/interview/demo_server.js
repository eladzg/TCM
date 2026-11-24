// Demo mode: when there is no clinic server (GitHub Pages), this file answers the app's /api calls in the
// browser, so the records, "היום", "יומן", "ניהול" and approval tabs can be tried without installing anything.
// Every patient here is invented for the demo. Changes stay in this browser tab (sessionStorage) and
// nothing is sent anywhere. With a real server (server/app.py answers /api/health) this file does nothing.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var realFetch = window.fetch.bind(window);
  var KEY = "tcm-demo-server-v1";
  var CFG = {"kinds": [{"kind": "first", "label": "ביקור ראשון", "minutes": 90, "price": 0}, {"kind": "followup", "label": "טיפול המשך", "minutes": 60, "price": 0}, {"kind": "check", "label": "מפגש מעקב", "minutes": 45, "price": 0}, {"kind": "herbs_pickup", "label": "איסוף צמחים", "minutes": 15, "price": 0}], "statuses": ["booked", "confirmed", "change_requested", "done", "no_show", "cancelled"], "alert_codes": {"PREGNANCY": "היריון", "ANTICOAGULANT": "נוגדי קרישה / נוגדי טסיות", "ANTIDIABETIC": "תרופות לסוכרת", "ANTIDEPRESSANT": "נוגדי דיכאון", "DIGOXIN": "דיגוקסין", "DEVICE": "קוצב לב או מכשיר מושתל", "EPILEPSY": "אפילפסיה", "IMMUNO": "דיכוי חיסוני או כימותרפיה", "ORGAN": "מחלת כבד או כליות", "ALLERGY": "אלרגיה", "NEEDLE": "רגישות למחטים / התעלפות", "OTHER": "אחר"}, "pay_methods": ["cash", "card", "transfer", "bit", "check", "other"], "consent_kinds": ["treatment", "privacy", "whatsapp"], "forms": {"treatment": {"version": "2026-11-draft1", "title": "הסכמה לטיפול", "text": ["אני מבקש/ת לקבל טיפול ברפואה סינית, שעשוי לכלול דיקור במחטים חד-פעמיות, כוסות רוח, מוקסה (חימום), עיסוי ומרשם צמחי מרפא.", "הוסבר לי שהטיפול אינו מחליף אבחון וטיפול רפואי, ושעליי להמשיך במעקב אצל הרופא/ה שלי ולא להפסיק תרופות בלי להתייעץ איתו/ה.", "הוסבר לי שייתכנו תופעות לוואי חולפות, כגון כאב קל או שטף דם קטן במקום הדיקור, עייפות או סחרחורת, ושצמחי מרפא עלולים להשפיע על תרופות.", "אדווח למטפל/ת על היריון או אפשרות להיריון, על תרופות שאני נוטל/ת, על מחלות רקע ועל מכשיר מושתל כמו קוצב לב.", "אני רשאי/ת להפסיק את הטיפול בכל שלב."]}, "privacy": {"version": "2026-11-draft1", "title": "שמירת מידע ופרטיות", "text": ["המידע שאמסור, כולל השאלון, הערות הטיפול ומדדי ההתקדמות, נשמר בשרת של הקליניקה, מוצפן, ומשמש לטיפול בי בלבד.", "השם ומספר הטלפון שלי נשמרים בנפרד מהמידע הקליני, במפתח הצפנה נפרד.", "מידע קליני לא נמסר לשום גורם חיצוני. לצורך מחקר ושיפור המערכת ייתכן שימוש בנתונים בלי שם, בלי טלפון ובלי טקסט חופשי.", "אני רשאי/ת לבקש לעיין במידע שלי, לתקן אותו או למחוק אותו."]}, "whatsapp": {"version": "2026-11-draft1", "title": "הודעות וואטסאפ", "text": ["אני מסכים/ה לקבל מהקליניקה הודעות וואטסאפ לוגיסטיות: אישור תור, תזכורת לפני תור, קישורים לשאלונים וטפסים, ומועדי מפגשים.", "ההודעות נשלחות דרך שירות WhatsApp של חברת Meta, ולכן Meta רואה את מספר הטלפון שלי ואת תוכן ההודעה. ההודעות לא יכללו שום מידע רפואי: לא תלונה, לא אבחנה ולא טיפול.", "כדאי לא לכתוב פרטים רפואיים בתשובה בוואטסאפ. אפשר לספר אותם בפגישה.", "אפשר לבטל את ההסכמה בכל עת, בפנייה לקליניקה, ואז לא יישלחו עוד הודעות אוטומטיות."]}}, "mymop": {"version": "MYMOP2 (Paterson 1996), Hebrew draft", "scale": "0 = טוב ככל האפשר · 6 = גרוע ככל האפשר", "s1": "בחר/י את הבעיה (תסמין) שהכי מטריד/ה אותך. כמה היא הייתה קשה בשבוע האחרון?", "s2": "בעיה שנייה שמטרידה אותך (לא חובה). כמה היא הייתה קשה בשבוע האחרון?", "activity": "פעילות אחת שחשובה לך (גופנית, חברתית או נפשית) שהבעיה מקשה עליה. כמה קשה היה לבצע אותה בשבוע האחרון?", "wellbeing": "איך היית מתאר/ת את ההרגשה הכללית שלך בשבוע האחרון?"}, "form_tasks": ["consent:treatment", "consent:privacy", "consent:whatsapp", "mymop"], "workdays": [6, 0, 1, 2, 3], "days_off": {"2026-04-02": "פסח", "2026-04-08": "שביעי של פסח", "2026-04-22": "יום העצמאות", "2026-05-22": "שבועות", "2026-09-12": "ראש השנה", "2026-09-13": "ראש השנה", "2026-09-21": "יום כיפור", "2026-09-26": "סוכות", "2026-10-03": "שמיני עצרת", "2027-04-22": "פסח", "2027-04-28": "שביעי של פסח", "2027-05-12": "יום העצמאות", "2027-06-11": "שבועות", "2027-10-02": "ראש השנה", "2027-10-03": "ראש השנה", "2027-10-11": "יום כיפור", "2027-10-16": "סוכות", "2027-10-23": "שמיני עצרת"}, "timezone": "Asia/Jerusalem", "whatsapp": {"cloud_api": false, "webhook": false, "send_hours": ["09:00", "19:00"], "reminder_time": "10:00", "address": "רחוב הדוגמה 1, תל אביב", "lang": "he", "templates": [{"id": "appt_confirm", "label": "אישור תור", "body": "שלום {name}, נקבע לך תור ביום {weekday} {date} בשעה {time}.\nכתובת: {address}\nלשינוי או ביטול אפשר להשיב להודעה זו.", "params": ["name", "weekday", "date", "time", "address"], "buttons": [], "meta_name": "appt_confirm", "check": []}, {"id": "reminder", "label": "תזכורת לתור", "body": "שלום {name}, תזכורת לתור ביום {weekday} {date} בשעה {time}.\nנשמח לאישור בלחיצה על הכפתור.", "params": ["name", "weekday", "date", "time"], "buttons": [{"id": "confirm", "text": "מאשר/ת"}, {"id": "change", "text": "צריך לשנות"}], "meta_name": "reminder", "check": []}, {"id": "intake_link", "label": "קישור לשאלון", "body": "שלום {name}, לפני הפגישה הראשונה נשמח שתמלא/י שאלון קצר בקישור {link}\nהקישור אישי ונסגר אחרי השליחה.", "params": ["name", "link"], "buttons": [], "meta_name": "intake_link", "check": []}, {"id": "forms_link", "label": "קישור לטפסים", "body": "שלום {name}, לפני הפגישה נשמח שתמלא/י טופס קצר בקישור {link}\nהקישור אישי ונסגר אחרי השליחה.", "params": ["name", "link"], "buttons": [], "meta_name": "forms_link", "check": []}, {"id": "series_schedule", "label": "מועדי המפגשים", "body": "שלום {name}, אלה מועדי המפגשים שקבענו: {dates}.\nלשינוי אפשר להשיב להודעה זו.", "params": ["name", "dates"], "buttons": [], "meta_name": "series_schedule", "check": []}, {"id": "followup_check", "label": "בדיקת שלומך", "body": "שלום {name}, עברו שבועיים מהמפגש האחרון. נשמח לשמוע מה שלומך ואם תרצה/י לקבוע מפגש המשך.", "params": ["name"], "buttons": [], "meta_name": "followup_check", "check": []}]}, "gcal": {"configured": false, "connected": false, "read_calendars": ["primary"], "clinic_calendar": null, "title": {"mode": "fixed", "text": "טיפול"}, "last_sync": null, "last_error": null}};
  CFG.kinds.forEach(function (k) { k.price = { first: 350, followup: 280, check: 200 }[k.kind] || 0; });

  var mode = null;   // a promise of "real" or "demo"
  function detect() {
    if (!mode) {
      mode = /[?&]demo=1\b/.test(location.search) ? Promise.resolve("demo") :
        realFetch(API + "/health", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) { return j && j.service === "tcm-clinic-server" && !j.demo ? "real" : "demo"; }, function () { return "demo"; });
    }
    return mode;
  }

  // ---- time helpers (local clinic time, minutes precision, like the server's "YYYY-MM-DDTHH:MM") ----
  function pad(n) { return String(n).padStart(2, "0"); }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function stamp(d) { return iso(d) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()); }
  function parse(s) { return new Date(s.length === 10 ? s + "T00:00" : s); }
  function ts(s) { return Math.floor(parse(s).getTime() / 1000); }
  function fmt(t) { return stamp(new Date(t * 1000)); }
  function now() { return Math.floor(Date.now() / 1000); }
  function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
  function pyDay(d) { return (d.getDay() + 6) % 7; }   // Monday = 0, as in Python
  function rid(prefix) { return prefix + "-" + Math.random().toString(16).slice(2, 14); }
  function recId() { var a = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", s = "R-"; for (var i = 0; i < 8; i++) s += a[Math.floor(Math.random() * a.length)]; return s; }
  var DAYS_SUN = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

  // ---- the invented clinic ----
  var PEOPLE = [
    { name: "נועה לוי (דוגמה)", phone: "050-0000001", case: "liver_yang", age: 41, sex: "F", status: "in_review", since: 120 },
    { name: "דוד כהן (דוגמה)", phone: "050-0000002", case: "spleen_qi", age: 56, sex: "M", status: "in_review", since: 90 },
    { name: "מיכל ברק (דוגמה)", phone: "050-0000003", case: "kidney_yin", age: 52, sex: "F", status: "submitted", since: 2 },
    { name: "יוסי אברהם (דוגמה)", phone: "050-0000004", case: "cold_damp_bi", age: 67, sex: "M", status: "closed", since: 160 },
    { name: "שירה פרץ (דוגמה)", phone: "050-0000005", case: "pregnant_nausea", age: 31, sex: "F", status: "in_review", since: 40 },
    { name: "אורי מזרחי (דוגמה)", phone: "050-0000006", case: null, age: null, sex: null, status: "awaiting_patient", since: 1 }
  ];

  function workday(d, db) { return CFG_workdays(db).indexOf(pyDay(d)) !== -1 && !daysOff(db)[iso(d)]; }
  function CFG_workdays(db) { return db.workdays; }
  function daysOff(db) { return Object.assign({}, CFG.days_off, db.days_off); }

  function seed() {
    var db = { records: [], appts: [], series: [], notes: [], alerts: [], outcomes: [], consents: [], packages: [], payments: [],
               queue: [], replies: [], messages: [], kb: [], docs: {}, workdays: CFG.workdays.slice(), days_off: {}, signed_in: true,
               wa: { send_hours: CFG.whatsapp.send_hours.slice(), reminder_time: CFG.whatsapp.reminder_time, address: CFG.whatsapp.address, meta_names: {} },
               gcal_title: { mode: "fixed", text: "טיפול" }, kinds: JSON.parse(JSON.stringify(CFG.kinds)), backup: { file: "records-" + iso(new Date()).replace(/-/g, "") + "-0700.db.gz.enc", at: now() - 4 * 3600 } };
    var today = new Date(); today.setHours(0, 0, 0, 0);
    PEOPLE.forEach(function (p, i) {
      var r = { record_id: recId(), status: p.status, created_at: now() - p.since * 86400, updated_at: now() - Math.min(p.since, 3) * 86400,
                link_expires_at: now() + 7 * 86400, identity: { name: p.name, phone: p.phone }, age: p.age, sex: p.sex, halted: false, documents: {}, case: p.case };
      if (p.case) r.documents.intake = 1;
      db.records.push(r);
      if (p.status === "awaiting_patient") {
        var first = nextWork(db, addDays(today, 2));
        db.appts.push(appt(db, r.record_id, stamp(at(first, 9, 0)), "first"));
        return;
      }
      ["treatment", "privacy"].concat(i === 2 ? [] : ["whatsapp"]).forEach(function (k) {
        db.consents.push({ id: rid("C"), record_id: r.record_id, kind: k, form_version: CFG.forms[k].version, signed_at: r.created_at + 600, revoked_at: null,
                           source: i % 2 ? "patient_link" : "clinic", signer: p.name.replace(" (דוגמה)", ""), signature: SIG });
      });
    });
    var R = db.records;
    // History: weekly visits over the past months, with notes and MYMOP going the right way.
    function history(r, weeks, hour, opts) {
      var start = addDays(today, -7 * weeks);
      var pkg = opts.pkg ? { id: rid("P"), record_id: r.record_id, label: "סדרת 7 טיפולים", sessions: 7, price: 1750, created_at: ts(iso(start)) } : null;
      if (pkg) db.packages.push(pkg);
      for (var w = 0; w < weeks; w++) {
        var d = nextWork(db, addDays(start, 7 * w));
        if (iso(d) >= iso(today)) break;
        var a = appt(db, r.record_id, stamp(at(d, hour, 0)), w === 0 ? "first" : "followup");
        a.status = opts.noShow && opts.noShow.indexOf(w) !== -1 ? "no_show" : "done";
        if (pkg && w > 0 && w <= 7) a.package_id = pkg.id;
        db.appts.push(a);
        if (a.status === "done" && opts.notes) {
          db.notes.push({ id: rid("N"), record_id: r.record_id, version: 1, appt_id: a.id, created_at: a.ts + 3600, created_by: "clinician:demo", first_at: a.ts + 3600,
                          data: opts.notes[w % opts.notes.length] });
        }
        if (a.status === "done" && opts.mymop && w % 2 === 0) {
          var k = Math.min(w / 2, opts.mymop.length - 1), m = opts.mymop[k];
          db.outcomes.push({ id: rid("O"), record_id: r.record_id, at: a.ts - 600, appt_id: a.id, source: w ? "patient_link" : "clinician",
                             s1: m[0], s2: m[1], activity: m[2], wellbeing: m[3], labels: opts.labels });
        }
        if (a.status === "done" && !a.package_id) db.payments.push({ id: rid("Y"), record_id: r.record_id, amount: a.price, at: a.ts + 3000, method: ["bit", "card", "cash"][w % 3], receipt_no: String(1000 + db.payments.length), package_id: null, appt_id: a.id, day: iso(d) });
      }
      if (pkg) db.payments.push({ id: rid("Y"), record_id: r.record_id, amount: 1750, at: pkg.created_at + 3600 * 24 * 7, method: "transfer", receipt_no: String(1000 + db.payments.length), package_id: pkg.id, appt_id: null, day: iso(addDays(start, 7)) });
    }
    history(R[0], 10, 16, { pkg: true, labels: { symptom1: "כאבי ראש", symptom2: "שינה", activity_name: "עבודה מול מחשב" },
      mymop: [[5, 4, 4, 4], [4, 4, 3, 3], [3, 3, 3, 3], [2, 2, 2, 2], [2, 1, 1, 2]],
      notes: [{ complaint: "כאבי ראש ברקות 4 פעמים בשבוע, מחמירים בלחץ", tongue: "אדומה בצדדים", pulse: "מיתרי", done: "LR3, LI4, GB20, Yintang", response: "נרגעה במהלך הטיפול", next: "שבוע הבא" },
              { complaint: "פחות התקפים, 2 בשבוע", done: "LR3, GB20, PC6", response: "טוב", next: "להמשיך" },
              { complaint: "שינה השתפרה, כאב ראש אחד בשבוע", done: "LR3, KI3, HT7", next: "לשקול מרווח של שבועיים" }] });
    history(R[1], 6, 11, { labels: { symptom1: "נפיחות אחרי האוכל", activity_name: "הליכה" }, mymop: [[5, null, 4, 4], [4, null, 3, 4], [3, null, 3, 3]], noShow: [3],
      notes: [{ complaint: "נפיחות ועייפות אחרי ארוחות", tongue: "חיוורת, סימני שיניים", pulse: "חלש", done: "ST36, SP6, CV12", next: "המלצות תזונה" }] });
    history(R[3], 9, 9, { labels: { symptom1: "כאב ברכיים", activity_name: "עלייה במדרגות" }, mymop: [[5, null, 5, 4], [4, null, 4, 3], [3, null, 3, 3], [3, null, 2, 2], [2, null, 2, 2]], noShow: [2, 5],
      notes: [{ complaint: "כאב ברכיים בבוקר ובקור", done: "ST35, Xiyan, GB34 + מוקסה", next: "המשך" }] });
    history(R[4], 3, 13, { labels: { symptom1: "בחילות" }, mymop: [[4, null, null, 4], [3, null, null, 3]],
      notes: [{ complaint: "בחילות בבוקר, שבוע 14", done: "PC6 בלבד, דיקור עדין", response: "הקלה", next: "בלי נקודות אסורות בהיריון" }] });
    db.alerts.push({ id: rid("L"), record_id: R[4].record_id, code: "PREGNANCY", label: CFG.alert_codes.PREGNANCY, active: true, updated_at: now() - 30 * 86400, text: "שבוע 14" });
    db.alerts.push({ id: rid("L"), record_id: R[1].record_id, code: "ANTICOAGULANT", label: CFG.alert_codes.ANTICOAGULANT, active: true, updated_at: now() - 80 * 86400, text: "אספירין 100" });
    db.series.push({ id: rid("S"), record_id: R[3].record_id, plan_version: 1, length: 7, per_week: 1, followup_appt: null, created_at: now() - 60 * 86400 });
    db.appts.filter(function (a) { return a.record_id === R[3].record_id && a.kind === "followup"; }).slice(0, 7).forEach(function (a, i) { a.series_id = db.series[0].id; a.series_no = i + 1; });

    // Today and the coming days.
    var t0 = nextWork(db, today), t1 = nextWork(db, addDays(t0, 1)), t2 = nextWork(db, addDays(t1, 1));
    [[R[0], t0, 10, 0, "followup", "confirmed"], [R[1], t0, 12, 30, "followup", "booked"], [R[4], t0, 16, 0, "followup", "change_requested"],
     [R[2], t1, 9, 30, "first", "booked"], [null, t1, 14, 0, "followup", "booked"], [R[1], t2, 11, 0, "followup", "booked"]].forEach(function (x) {
      var a = appt(db, x[0] ? x[0].record_id : null, stamp(at(x[1], x[2], x[3])), x[4]);
      a.status = x[5];
      if (!x[0]) { a.source = "google"; a.external_title = "פגישה (מיומן גוגל)"; }
      db.appts.push(a);
    });
    // A new series for Noa, starting next week.
    makeSeries(db, R[0].record_id, iso(addDays(today, 7)), "16:00", 7, 1, null, null, 1);
    db.appts.forEach(function (a) { if (a.record_id && a.ts > now() && a.status !== "cancelled") queueReminder(db, a); });
    var miss = db.queue.filter(function (q) { return q.record_id === R[1].record_id; })[0];
    if (miss) { miss.status = "missed"; miss.due_at = now() - 20 * 3600; }
    db.replies.push({ id: rid("W"), record_id: R[4].record_id, kind: "button", payload: "change", text: null, at: now() - 5 * 3600, handled: false });
    db.replies.push({ id: rid("W"), record_id: R[0].record_id, kind: "button", payload: "confirm", text: null, at: now() - 22 * 3600, handled: true });
    db.kb = [];
    return db;
  }
  function at(d, h, m) { var x = new Date(d); x.setHours(h, m, 0, 0); return x; }
  function nextWork(db, d) { var x = new Date(d); for (var i = 0; i < 14 && !workday(x, db); i++) x = addDays(x, 1); return x; }
  function kindOf(db, k) { return db.kinds.filter(function (x) { return x.kind === k; })[0] || db.kinds[1]; }
  function appt(db, recordId, start, kind) {
    var k = kindOf(db, kind), s = parse(start);
    return { id: rid("A"), record_id: recordId, minutes: k.minutes, kind: k.kind, status: "booked", series_id: null, series_no: null, source: "clinic",
             gcal_state: "push", price: k.price, package_id: null, start: start, end: stamp(new Date(s.getTime() + k.minutes * 60000)), ts: ts(start), external_title: null };
  }
  function hasConsent(db, r, k) { return db.consents.some(function (c) { return c.record_id === r && c.kind === k && !c.revoked_at; }); }
  function prevWorkday(db, d) { var x = addDays(d, -1); for (var i = 0; i < 14 && !workday(x, db); i++) x = addDays(x, -1); return x; }
  function queueReminder(db, a) {
    db.queue = db.queue.filter(function (q) { return !(q.appt_id === a.id && q.status === "pending"); });
    if (!hasConsent(db, a.record_id, "whatsapp")) return;
    var hm = db.wa.reminder_time.split(":"), d = at(prevWorkday(db, parse(a.start)), +hm[0], +hm[1]);
    db.queue.push({ id: rid("Q"), record_id: a.record_id, appt_id: a.id, template: "reminder", due_at: Math.floor(d.getTime() / 1000), status: a.ts <= now() ? "missed" : "pending", last_error: null, sent_at: null });
  }
  function plan(db, start, time, length, perWeek) {
    var out = [], moved = [], d = parse(start), hm = time.split(":");
    var step = perWeek === 2 ? [3, 4] : [7];
    for (var i = 0; i < length; i++) {
      var want = new Date(d), x = new Date(d), why = null;
      for (var g = 0; g < 14 && !workday(x, db); g++) { why = why || daysOff(db)[iso(x)] || "לא יום עבודה"; x = addDays(x, 1); }
      if (iso(x) !== iso(want)) moved.push({ from: iso(want), why: why, to: iso(x) });
      out.push(stamp(at(x, +hm[0], +hm[1])));
      d = addDays(d, step[i % step.length]);
    }
    var fu = nextWork(db, addDays(parse(out[out.length - 1]), 14));
    return { sessions: out, followup: stamp(at(fu, +hm[0], +hm[1])), moved: moved };
  }
  function makeSeries(db, recordId, start, time, length, perWeek, firstKind, packageId, planVersion) {
    var p = plan(db, start, time, length, perWeek), s = { id: rid("S"), record_id: recordId, plan_version: planVersion || null, length: length, per_week: perWeek, followup_appt: null, created_at: now() };
    var ids = p.sessions.map(function (st, i) {
      var a = appt(db, recordId, st, i === 0 && firstKind ? firstKind : "followup");
      a.series_id = s.id; a.series_no = i + 1; a.package_id = packageId || null;
      db.appts.push(a); queueReminder(db, a); return a.id;
    });
    var f = appt(db, recordId, p.followup, "check"); f.series_id = s.id; f.series_no = 0; db.appts.push(f); queueReminder(db, f);
    s.followup_appt = f.id; db.series.push(s);
    return { series_id: s.id, appointments: ids, followup: f.id, moved: p.moved };
  }

  // ---- state in this tab ----
  var db = null;
  function load() {
    if (db) return db;
    try { db = JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (e) { db = null; }
    if (!db || db.day !== iso(new Date())) { db = seed(); db.day = iso(new Date()); }
    return db;
  }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(db)); } catch (e) { /* full or off: keep in memory */ } }

  function rec(id) { return db.records.filter(function (r) { return r.record_id === id; })[0]; }
  function nameOf(id) { var r = rec(id); return r && r.identity ? r.identity.name : null; }
  function publicRecord(r) {
    var o = {}; Object.keys(r).forEach(function (k) { if (k !== "case") o[k] = r[k]; });
    o.documents = Object.assign({}, r.documents); return o;
  }
  function sortAppts(list) { return list.slice().sort(function (a, b) { return a.ts - b.ts; }); }
  function activeCodes(r) { return db.alerts.filter(function (a) { return a.record_id === r && a.active; }).map(function (a) { return a.code; }); }
  function account(r) {
    var visits = db.appts.filter(function (a) { return a.record_id === r && a.status === "done"; });
    var pk = db.packages.filter(function (p) { return p.record_id === r; }).map(function (p) {
      return Object.assign({}, p, { used: visits.filter(function (a) { return a.package_id === p.id; }).length });
    });
    var charged = pk.reduce(function (s, p) { return s + p.price; }, 0) + visits.filter(function (a) { return !a.package_id; }).reduce(function (s, a) { return s + (a.price || 0); }, 0);
    var pays = db.payments.filter(function (p) { return p.record_id === r; });
    var paid = pays.reduce(function (s, p) { return s + p.amount; }, 0);
    return { visits: visits.map(function (a) { return { id: a.id, start: a.start, price: a.price, package_id: a.package_id }; }), packages: pk, payments: pays, charged: charged, paid: paid, balance: charged - paid };
  }

  // A whole interview for a sample record, made in the browser from a sample case (demo_cases.js).
  function intakeState(r) {
    if (db.docs[r.record_id + ":intake"]) return db.docs[r.record_id + ":intake"];
    var UI = window.TCMInterviewUI, D = window.TCMDemoCases;
    if (!UI || !D || !r.case) return null;
    var c = D.CASES.filter(function (x) { return x.id === r.case; })[0];
    var E = UI.engine, st = E.newState({}), transcript = [];
    var obj = D.run(E, st, c, function (x, who) { if (typeof x === "string") transcript.push({ role: who === "pt" ? "patient" : "system", text: x }); });
    st.transcript = st.transcript && st.transcript.length ? st.transcript : transcript;
    var doc = { data: { schema_version: "intake.v1", state: JSON.parse(JSON.stringify(st)) }, version: 1, created_at: r.created_at + 900 };
    if (r.status !== "submitted") db.docs[r.record_id + ":review"] = { data: { schema_version: "review.v1", state: doc.data.state, objective: { tongue: obj.tongue, pulse: obj.pulse } }, version: 1, created_at: r.created_at + 3600 };
    db.docs[r.record_id + ":intake"] = doc;
    return doc;
  }

  // ---- WhatsApp text, as the server renders it (no real phone numbers in the demo) ----
  function tpl(id) { return CFG.whatsapp.templates.filter(function (t) { return t.id === id; })[0]; }
  function render(id, r, a, extra) {
    var t = tpl(id), d = a ? parse(a.start) : null;
    var p = { name: ((r && r.identity && r.identity.name) || "").split(" ")[0], weekday: d ? DAYS_SUN[d.getDay()] : "", date: d ? pad(d.getDate()) + "." + pad(d.getMonth() + 1) : "",
              time: a ? a.start.slice(11, 16) : "", address: db.wa.address, link: extra.link || (extra.link_path ? location.origin + extra.link_path : ""), dates: extra.dates || "" };
    return t.body.replace(/\{(\w+)\}/g, function (m, k) { return p[k] !== undefined ? p[k] : m; });
  }
  var CLINICAL = ["דיקור", "מחטים", "כאב", "אבחנה", "היריון", "צמחים", "תרופה", "סרטן", "דיכאון", "לחץ דם", "סוכרת", "טיפול שורש", "כבד", "כליות"];
  function check(text) { return CLINICAL.filter(function (w) { return (text || "").indexOf(w) !== -1; }); }
  function waOut(id, r, a, extra) {
    var text = render(id, r, a, extra || {});
    db.messages.push({ id: rid("M"), record_id: r.record_id, template: id, channel: "wa.me", status: "opened", at: now() });
    // An invented patient's wa.me link has no number (WhatsApp asks whom to send it to); a number the clinician typed in is used.
    var num = r.identity && !invented(r.identity.phone) ? waNumber(r.identity.phone) : null;
    return { blocked: [], text: text, link: "https://wa.me/" + (num || "") + "?text=" + encodeURIComponent(text), demo: true };
  }

  // ---- routes ----
  function E(status, detail) { var e = new Error(detail); e.status = status; return e; }
  var routes = [
    ["GET", /^\/health$/, function () { return { ok: true, service: "tcm-clinic-server", demo: true }; }],
    ["POST", /^\/login$/, function () { db.signed_in = true; return { username: "demo" }; }],
    ["POST", /^\/logout$/, function () { db.signed_in = false; return { ok: true }; }],
    ["GET", /^\/me$/, function () { return { username: "demo" }; }],
    ["GET", /^\/records$/, function () { return { records: db.records.slice().sort(function (a, b) { return b.updated_at - a.updated_at; }).map(publicRecord) }; }],
    ["POST", /^\/records$/, function (m, b) {
      var r = { record_id: recId(), status: "awaiting_patient", created_at: now(), updated_at: now(), link_expires_at: now() + 7 * 86400,
                identity: b.identity || null, age: null, sex: null, halted: false, documents: {}, case: null };
      db.records.push(r);
      return link(r);
    }],
    ["POST", /^\/records\/([^/]+)\/link$/, function (m) { var r = need(m[1]); r.link_expires_at = now() + 7 * 86400; return link(r); }],
    ["DELETE", /^\/records\/([^/]+)$/, function (m) {
      need(m[1]);
      ["records", "appts", "series", "notes", "alerts", "outcomes", "consents", "packages", "payments", "queue", "replies", "messages"].forEach(function (k) {
        db[k] = db[k].filter(function (x) { return x.record_id !== m[1]; });
      });
      return { ok: true };
    }],
    ["GET", /^\/records\/([^/]+)$/, function (m) {
      var r = need(m[1]), o = publicRecord(r), intake = r.documents.intake ? intakeState(r) : null;
      var plans = db.docs[r.record_id + ":plans"] || [];
      return Object.assign(o, { intake: intake, review: db.docs[r.record_id + ":review"] || null, report: db.docs[r.record_id + ":report"] || null,
                                plan: plans.length ? plans[plans.length - 1] : null, plan_versions: plans.length });
    }],
    ["PUT", /^\/records\/([^/]+)\/status$/, function (m, b) { var r = need(m[1]); r.status = b.status; r.updated_at = now(); return { ok: true }; }],
    ["POST", /^\/records\/([^/]+)\/(review|report|plan)$/, function (m, b) {
      var r = need(m[1]), k = m[2], v;
      if (k === "plan") { var l = db.docs[r.record_id + ":plans"] = db.docs[r.record_id + ":plans"] || []; v = l.length + 1; l.push({ data: b.document, version: v, created_at: now() }); }
      else { var old = db.docs[r.record_id + ":" + k]; v = old ? old.version + 1 : 1; db.docs[r.record_id + ":" + k] = { data: b.document, version: v, created_at: now() }; }
      r.documents[k] = v; r.updated_at = now();
      if (k === "review" && r.status === "submitted") r.status = "in_review";
      return { version: v };
    }],

    ["GET", /^\/pm\/config$/, function () {
      var c = JSON.parse(JSON.stringify(CFG));
      c.kinds = db.kinds; c.workdays = db.workdays; c.days_off = daysOff(db);
      c.whatsapp.send_hours = db.wa.send_hours; c.whatsapp.reminder_time = db.wa.reminder_time; c.whatsapp.address = db.wa.address;
      c.whatsapp.templates.forEach(function (t) { if (db.wa.meta_names[t.id]) t.meta_name = db.wa.meta_names[t.id]; });
      c.gcal.title = db.gcal_title;
      c.backup = { latest: db.backup.file, age_hours: (now() - db.backup.at) / 3600, error: null };
      c.jobs = { running: false, last: {}, error: null };
      c.demo = true;
      var L = live();
      c.whatsapp.cloud_api = !!L; c.whatsapp.test_mode = !!L; c.whatsapp.webhook = false;
      c.whatsapp.demo_live = L ? { phone_id: L.phone_id } : null;
      return c;
    }],
    ["GET", /^\/pm\/today$/, function (m, b, q) {
      var day = q.day || iso(new Date()), nowS = stamp(new Date());
      var appts = sortAppts(db.appts.filter(function (a) { return a.start.slice(0, 10) === day && a.status !== "cancelled"; })).map(function (a) {
        return Object.assign({}, a, { name: nameOf(a.record_id), alerts: a.record_id ? activeCodes(a.record_id) : [],
          consent_missing: a.record_id ? ["treatment", "privacy"].filter(function (k) { return !hasConsent(db, a.record_id, k); }) : [] });
      });
      var noShow = {};
      db.appts.forEach(function (a) { if (a.status === "no_show" && a.record_id) noShow[a.record_id] = (noShow[a.record_id] || 0) + 1; });
      var ended = db.series.filter(function (s) {
        var list = db.appts.filter(function (a) { return a.series_id === s.id && a.series_no > 0; });
        return list.length && list.every(function (a) { return a.status === "done" || a.status === "no_show" || a.status === "cancelled"; }) &&
          !db.appts.some(function (a) { return a.record_id === s.record_id && a.start > nowS && a.status !== "cancelled"; });
      }).map(function (s) { return { record_id: s.record_id, name: nameOf(s.record_id) }; });
      var soon = stamp(addDays(new Date(), 7));
      return {
        day: day, day_off: daysOff(db)[day] || null, appointments: appts,
        intakes_waiting: db.records.filter(function (r) { return r.status === "submitted"; }).map(function (r) { return { record_id: r.record_id, name: nameOf(r.record_id), at: r.updated_at }; }),
        in_review: db.records.filter(function (r) { return r.status === "in_review"; }).map(function (r) { return { record_id: r.record_id, name: nameOf(r.record_id) }; }),
        series_ended: ended,
        unsent_messages: db.queue.filter(function (x) { return ["missed", "failed", "blocked", "skipped_no_consent"].indexOf(x.status) !== -1; })
          .map(function (x) { return Object.assign({}, x, { name: nameOf(x.record_id), due: fmt(x.due_at) }); }),
        replies: db.replies.filter(function (r) { return !r.handled; }).map(function (r) { return Object.assign({}, r, { name: nameOf(r.record_id) }); }),
        repeat_no_show: Object.keys(noShow).filter(function (k) { return noShow[k] >= 2; }).map(function (k) { return { record_id: k, name: nameOf(k), n: noShow[k] }; }),
        unlinked_events: db.appts.filter(function (a) { return !a.record_id && a.source === "google" && a.start >= nowS.slice(0, 10); }).length,
        intake_before_first: db.records.filter(function (r) { return r.status === "awaiting_patient"; }).map(function (r) {
          var a = sortAppts(db.appts.filter(function (x) { return x.record_id === r.record_id && x.start >= nowS && x.start <= soon && x.status !== "cancelled"; }))[0];
          return a ? { record_id: r.record_id, name: nameOf(r.record_id), start: a.start } : null;
        }).filter(Boolean)
      };
    }],
    ["GET", /^\/pm\/calendar$/, function (m, b, q) {
      var start = q.start, days = +(q.days || 7), end = iso(addDays(parse(start), days)), off = {}, all = daysOff(db);
      Object.keys(all).forEach(function (d) { if (d >= start && d < end) off[d] = all[d]; });
      return { start: start, days: days, days_off: off, workdays: db.workdays, gcal: gcal(),
        appointments: sortAppts(db.appts.filter(function (a) { return a.start >= start && a.start < end; })).map(function (a) { return Object.assign({}, a, { name: nameOf(a.record_id) }); }) };
    }],
    ["POST", /^\/pm\/appointments$/, function (m, b) {
      if (!b.start) throw E(422, "start is required");
      var a = appt(db, b.record_id || null, b.start.slice(0, 16), b.kind || "followup");
      db.appts.push(a); if (a.record_id) queueReminder(db, a);
      return { appointment: a };
    }],
    ["PUT", /^\/pm\/appointments\/([^/]+)$/, function (m, b) {
      var a = db.appts.filter(function (x) { return x.id === m[1]; })[0];
      if (!a) throw E(404, "no such appointment");
      if ("record_id" in b) a.record_id = b.record_id || null;
      if (b.kind) { var k = kindOf(db, b.kind); a.kind = k.kind; a.minutes = k.minutes; a.price = k.price; }
      if (b.start) { a.start = b.start.slice(0, 16); a.ts = ts(a.start); }
      a.end = stamp(new Date(parse(a.start).getTime() + a.minutes * 60000));
      if (b.status) a.status = b.status;
      if (a.status === "cancelled" || a.status === "done" || a.status === "no_show") db.queue.forEach(function (q) { if (q.appt_id === a.id && q.status === "pending") q.status = "cancelled"; });
      else if (a.record_id && (b.start || "record_id" in b)) queueReminder(db, a);
      return { appointment: a };
    }],
    ["GET", /^\/pm\/series\/preview$/, function (m, b, q) { return plan(db, q.start, q.time || "16:00", +q.length || 7, +q.per_week || 1); }],
    ["POST", /^\/pm\/records\/([^/]+)\/series$/, function (m, b) {
      need(m[1]);
      var out = makeSeries(db, m[1], b.start, b.time || "16:00", +b.length || 7, +b.per_week || 1, b.first_kind, b.package_id, b.plan_version);
      if (b.send_schedule && hasConsent(db, m[1], "whatsapp")) db.messages.push({ id: rid("M"), record_id: m[1], template: "series_schedule", channel: "cloud_api", status: "sent", at: now() });
      return out;
    }],
    ["GET", /^\/pm\/records\/([^/]+)$/, function (m) {
      var r = need(m[1]), id = r.record_id;
      var notes = db.notes.filter(function (n) { return n.record_id === id; });
      var latest = {};
      notes.forEach(function (n) { if (!latest[n.id] || latest[n.id].version < n.version) latest[n.id] = n; });
      return {
        record_id: id, identity: r.identity, record: { record_id: id, status: r.status, created_at: r.created_at, updated_at: r.updated_at, created_by: "clinician:demo" },
        alerts: db.alerts.filter(function (a) { return a.record_id === id; }),
        notes: Object.keys(latest).map(function (k) { var n = latest[k]; return Object.assign({}, n, { versions: notes.filter(function (x) { return x.id === k; }).length }); })
          .sort(function (a, b) { return b.first_at - a.first_at; }),
        appointments: sortAppts(db.appts.filter(function (a) { return a.record_id === id; })),
        series: db.series.filter(function (s) { return s.record_id === id; }).map(function (s) {
          return Object.assign({}, s, { done: db.appts.filter(function (a) { return a.series_id === s.id && a.series_no > 0 && a.status === "done"; }).length });
        }),
        outcomes: db.outcomes.filter(function (o) { return o.record_id === id; }).sort(function (a, b) { return a.at - b.at; }),
        consents: db.consents.filter(function (c) { return c.record_id === id; }).map(function (c) { var o = Object.assign({}, c); delete o.signature; return o; }),
        account: account(id),
        replies: db.replies.filter(function (x) { return x.record_id === id; }),
        queue: db.queue.filter(function (x) { return x.record_id === id; }).map(function (x) { return Object.assign({}, x, { due: fmt(x.due_at) }); }).sort(function (a, b) { return a.due_at - b.due_at; })
      };
    }],
    ["GET", /^\/pm\/records\/([^/]+)\/alerts$/, function (m) { return { alerts: db.alerts.filter(function (a) { return a.record_id === m[1] && a.active; }) }; }],
    ["POST", /^\/pm\/records\/([^/]+)\/alerts$/, function (m, b) {
      need(m[1]);
      if (!CFG.alert_codes[b.code]) throw E(422, "unknown alert code");
      var a = b.alert_id ? db.alerts.filter(function (x) { return x.id === b.alert_id; })[0] : null;
      if (!a) { a = { id: rid("L"), record_id: m[1], code: b.code, label: CFG.alert_codes[b.code], active: true, updated_at: now(), text: b.text || "" }; db.alerts.push(a); }
      else { a.active = b.active !== false; a.text = b.text || ""; a.updated_at = now(); }
      return { alert_id: a.id };
    }],
    ["POST", /^\/pm\/records\/([^/]+)\/notes$/, function (m, b) {
      need(m[1]);
      var d = b.note || {}, appt_id = d.appt_id || null, data = {};
      Object.keys(d).forEach(function (k) { if (k !== "appt_id" && d[k]) data[k] = d[k]; });
      if (!Object.keys(data).length) throw E(422, "an empty note");
      var prev = b.note_id ? db.notes.filter(function (n) { return n.id === b.note_id; }) : [];
      var first = prev.length ? prev[0].first_at : now();
      var n = { id: b.note_id || rid("N"), record_id: m[1], version: prev.length + 1, appt_id: appt_id || (prev[0] && prev[0].appt_id) || null, created_at: now(), created_by: "clinician:demo", first_at: first, data: data };
      db.notes.push(n);
      return { note_id: n.id, version: n.version };
    }],
    ["GET", /^\/pm\/records\/([^/]+)\/notes\/([^/]+)$/, function (m) {
      var h = db.notes.filter(function (n) { return n.id === m[2]; }).sort(function (a, b) { return a.version - b.version; });
      if (!h.length) throw E(404, "no such note");
      return Object.assign({}, h[h.length - 1], { versions: h.length, history: h });
    }],
    ["POST", /^\/pm\/records\/([^/]+)\/outcomes$/, function (m, b) {
      need(m[1]);
      if (b.s1 === undefined || b.wellbeing === undefined) throw E(422, "symptom 1 and wellbeing are required");
      var labels = {};
      ["symptom1", "symptom2", "activity_name"].forEach(function (k) { if (b[k]) labels[k] = b[k]; });
      var last = db.outcomes.filter(function (o) { return o.record_id === m[1]; }).pop();
      var o = { id: rid("O"), record_id: m[1], at: now(), appt_id: null, source: "clinician", s1: b.s1, s2: b.s2 === undefined ? null : b.s2,
                activity: b.activity === undefined ? null : b.activity, wellbeing: b.wellbeing, labels: Object.keys(labels).length ? labels : (last ? last.labels : {}) };
      db.outcomes.push(o);
      return { outcome_id: o.id };
    }],
    ["POST", /^\/pm\/records\/([^/]+)\/consents$/, function (m, b) {
      var r = need(m[1]);
      if (!CFG.forms[b.kind]) throw E(422, "unknown consent kind");
      var c = { id: rid("C"), record_id: r.record_id, kind: b.kind, form_version: CFG.forms[b.kind].version, signed_at: now(), revoked_at: null, source: "clinic", signer: b.signer || "", signature: b.signature };
      db.consents.push(c);
      if (b.kind === "whatsapp") db.appts.forEach(function (a) { if (a.record_id === r.record_id && a.ts > now() && a.status !== "cancelled") queueReminder(db, a); });
      return { consent_id: c.id };
    }],
    ["GET", /^\/pm\/consents\/([^/]+)$/, function (m) {
      var c = db.consents.filter(function (x) { return x.id === m[1]; })[0];
      if (!c) throw E(404, "no such consent");
      var f = CFG.forms[c.kind];
      return Object.assign({}, c, { title: f.title, text: c.form_version === f.version ? f.text : null });
    }],
    ["POST", /^\/pm\/consents\/([^/]+)\/revoke$/, function (m) {
      var c = db.consents.filter(function (x) { return x.id === m[1]; })[0];
      if (!c) throw E(404, "no such consent");
      c.revoked_at = now();
      if (c.kind === "whatsapp") db.queue.forEach(function (q) { if (q.record_id === c.record_id && q.status === "pending") q.status = "cancelled"; });
      return { ok: true };
    }],
    ["POST", /^\/pm\/records\/([^/]+)\/form-link$/, function (m) {
      need(m[1]);
      var t = "demo-" + Math.random().toString(36).slice(2, 12);
      return { token: t, path: "/app/forms.html#" + t, url: pageUrl("forms.html", t), expires_at: now() + 7 * 86400 };
    }],
    ["POST", /^\/pm\/records\/([^/]+)\/whatsapp$/, function (m, b) {
      var r = need(m[1]);
      if (!r.identity || !r.identity.phone) throw E(422, "no phone number in the record");
      var a = b.appt_id ? db.appts.filter(function (x) { return x.id === b.appt_id; })[0] : null;
      if (!a && (b.template === "reminder" || b.template === "appt_confirm")) a = sortAppts(db.appts.filter(function (x) { return x.record_id === r.record_id && x.ts > now(); }))[0];
      var extra = { link: b.link, link_path: b.link_path };
      if (b.template === "series_schedule") {
        var s = b.series_id || (db.series.filter(function (x) { return x.record_id === r.record_id; }).pop() || {}).id;
        extra.dates = sortAppts(db.appts.filter(function (x) { return x.series_id === s && x.series_no > 0; })).map(function (x) { var d = parse(x.start); return DAYS_SUN[d.getDay()] + " " + d.getDate() + "." + (d.getMonth() + 1) + " " + x.start.slice(11, 16); }).join(" · ");
      }
      var L = live(), to = !b.manual && L && r.identity && !invented(r.identity.phone) && waNumber(r.identity.phone);
      if (!L || b.manual) return waOut(b.template, r, a, extra);
      var text = render(b.template, r, a, extra);
      if (!to) {
        var o = waOut(b.template, r, a, extra);
        o.sent = false; o.error = invented(r.identity.phone) ? "invented: מספר של מטופל/ת בדוי/ה, לא שולחים אליו." : "no usable phone number";
        return o;
      }
      // Meta's test number: the Hebrew goes as plain text, with no hello_world stand-in, so a link arrives whole or not at all.
      return graph("POST", "/" + L.phone_id + "/messages", { messaging_product: "whatsapp", to: to, type: "text", text: { body: text, preview_url: false } }).then(function (res) {
        db.messages.push({ id: rid("M"), record_id: r.record_id, template: b.template, channel: "cloud_api", status: "sent", at: now() });
        return { blocked: [], sent: true, test_mode: true, id: ((res.messages || [])[0] || {}).id, text: text };
      }, function (e) {
        var o = waOut(b.template, r, a, extra);
        o.sent = false; o.error = e.message; return o;
      });
    }],
    ["POST", /^\/pm\/queue\/([^/]+)\/(manual|retry|dismiss)$/, function (m) {
      var q = db.queue.filter(function (x) { return x.id === m[1]; })[0];
      if (!q) throw E(404, "no such message");
      if (m[2] === "dismiss") { q.status = "dismissed"; return { ok: true }; }
      if (m[2] === "retry") { q.status = "pending"; q.due_at = now() + 60; return { ok: true }; }
      q.status = "sent_by_hand"; q.sent_at = now();
      return waOut(q.template, rec(q.record_id), db.appts.filter(function (a) { return a.id === q.appt_id; })[0], {});
    }],
    ["POST", /^\/pm\/replies\/([^/]+)\/handled$/, function (m) { db.replies.forEach(function (r) { if (r.id === m[1]) r.handled = true; }); return { ok: true }; }],
    ["POST", /^\/pm\/records\/([^/]+)\/payments$/, function (m, b) {
      need(m[1]);
      if (!(b.amount > 0)) throw E(422, "amount must be positive");
      var p = { id: rid("Y"), record_id: m[1], amount: b.amount, at: now(), method: b.method || "card", receipt_no: b.receipt_no || "", package_id: b.package_id || null, appt_id: null, day: b.day || iso(new Date()) };
      db.payments.push(p);
      return { account: account(m[1]) };
    }],
    ["POST", /^\/pm\/records\/([^/]+)\/packages$/, function (m, b) {
      need(m[1]);
      db.packages.push({ id: rid("P"), record_id: m[1], label: b.label || "חבילה", sessions: +b.sessions || 1, price: +b.price || 0, created_at: now() });
      return { account: account(m[1]) };
    }],
    ["GET", /^\/pm\/records\/([^/]+)\/timeline$/, function (m) {
      var r = need(m[1]), id = r.record_id, items = [{ at: r.created_at, type: "record" }];
      if (r.documents.intake) items.push({ at: r.created_at + 900, type: "doc:intake", version: 1 });
      ["review", "report"].forEach(function (k) { var d = db.docs[id + ":" + k]; if (d) items.push({ at: d.created_at, type: "doc:" + k, version: d.version }); });
      (db.docs[id + ":plans"] || []).forEach(function (d) { items.push({ at: d.created_at, type: "doc:plan", version: d.version }); });
      db.appts.forEach(function (a) { if (a.record_id === id) items.push({ at: a.ts, type: "appointment", id: a.id, kind: a.kind, status: a.status, series_no: a.series_no }); });
      var seen = {};
      db.notes.filter(function (n) { return n.record_id === id; }).forEach(function (n) { seen[n.id] = seen[n.id] || { at: n.first_at, type: "note", id: n.id, versions: 0 }; seen[n.id].versions++; });
      Object.keys(seen).forEach(function (k) { items.push(seen[k]); });
      db.outcomes.forEach(function (o) { if (o.record_id === id) items.push({ at: o.at, type: "mymop", s1: o.s1, s2: o.s2, wellbeing: o.wellbeing, source: o.source }); });
      db.consents.forEach(function (c) {
        if (c.record_id !== id) return;
        items.push({ at: c.signed_at, type: "consent", kind: c.kind });
        if (c.revoked_at) items.push({ at: c.revoked_at, type: "consent_revoked", kind: c.kind });
      });
      db.messages.forEach(function (x) { if (x.record_id === id) items.push({ at: x.at, type: "message", template: x.template, channel: x.channel, status: x.status }); });
      db.queue.forEach(function (x) { if (x.record_id === id && x.sent_at) items.push({ at: x.sent_at, type: "message", template: x.template, channel: "wa.me", status: x.status }); });
      db.replies.forEach(function (x) { if (x.record_id === id) items.push({ at: x.at, type: "reply", kind: x.kind }); });
      db.payments.forEach(function (p) { if (p.record_id === id) items.push({ at: p.at, type: "payment", amount: p.amount }); });
      db.packages.forEach(function (p) { if (p.record_id === id) items.push({ at: p.created_at, type: "package", label: p.label }); });
      items.forEach(function (i) { i.when = fmt(i.at); });
      return { items: items.sort(function (a, b) { return b.at - a.at; }) };
    }],
    ["GET", /^\/pm\/stats$/, function () {
      var months = [], d = new Date(); d.setDate(1);
      for (var i = 11; i >= 0; i--) { var x = new Date(d.getFullYear(), d.getMonth() - i, 1); months.push({ month: x.getFullYear() + "-" + pad(x.getMonth() + 1), visits: 0, no_show: 0, cancelled: 0, new_records: 0, revenue: 0, messages: 0 }); }
      var by = {}; months.forEach(function (m) { by[m.month] = m; });
      db.appts.forEach(function (a) { var m = by[a.start.slice(0, 7)]; if (!m) return; if (a.status === "done") m.visits++; else if (a.status === "no_show") m.no_show++; else if (a.status === "cancelled") m.cancelled++; });
      db.records.forEach(function (r) { var m = by[fmt(r.created_at).slice(0, 7)]; if (m) m.new_records++; });
      db.payments.forEach(function (p) { var m = by[p.day.slice(0, 7)]; if (m) m.revenue += p.amount; });
      db.messages.forEach(function (x) { var m = by[fmt(x.at).slice(0, 7)]; if (m) m.messages++; });
      var done = months.reduce(function (s, m) { return s + m.visits; }, 0), ns = months.reduce(function (s, m) { return s + m.no_show; }, 0);
      var per = {};
      db.outcomes.forEach(function (o) { (per[o.record_id] = per[o.record_id] || []).push(o); });
      var changes = Object.keys(per).filter(function (k) { return per[k].length > 1; }).map(function (k) { var l = per[k].sort(function (a, b) { return a.at - b.at; }); return l[0].s1 - l[l.length - 1].s1; });
      return { months: months, no_show_rate: done + ns ? ns / (done + ns) : null,
        mymop: { patients: changes.length, mean_change_s1: changes.length ? Math.round(10 * changes.reduce(function (s, c) { return s + c; }, 0) / changes.length) / 10 : null,
                 improved_1_or_more: changes.filter(function (c) { return c >= 1; }).length },
        series: { total: db.series.length, completed: db.series.filter(function (s) { return db.appts.filter(function (a) { return a.series_id === s.id && a.series_no > 0; }).every(function (a) { return a.status === "done"; }); }).length } };
    }],
    ["PUT", /^\/pm\/whatsapp\/demo-credentials$/, function (m, b) {
      var id = String(b.phone_id || "").replace(/\D/g, ""), tok = String(b.token || "").trim();
      if (!id || !tok) throw E(422, "צריך Phone Number ID ואסימון");
      if (/^(1555|972|0)/.test(id) || id.length < 13) throw E(422, "זה נראה כמו מספר הטלפון של מספר הבדיקה, לא ה־Phone Number ID. ה־ID הוא מספר ארוך (בדרך כלל 15–16 ספרות) שמופיע ב־API Setup מתחת למספר הטלפון, ליד הכיתוב Phone number ID.");
      try { sessionStorage.setItem(LIVE_KEY, JSON.stringify({ phone_id: id, token: tok })); } catch (e) { throw E(500, "הדפדפן לא שומר נתונים בלשונית"); }
      return { ok: true };
    }],
    ["DELETE", /^\/pm\/whatsapp\/demo-credentials$/, function () { try { sessionStorage.removeItem(LIVE_KEY); } catch (e) { /* ignore */ } return { ok: true }; }],
    ["GET", /^\/pm\/whatsapp\/status$/, function () {
      var L = live();
      if (!L) return { ok: false, error: "לא הוזנו Phone Number ID ואסימון" };
      return graph("GET", "/" + L.phone_id + "?fields=display_phone_number,verified_name,quality_rating", null).then(function (n) {
        return { ok: true, number: n.display_phone_number, name: n.verified_name, quality: n.quality_rating, templates: null, templates_error: "במצב בדיקה לא צריך תבניות" };
      }, function (e) { return { ok: false, error: e.message }; });
    }],
    ["POST", /^\/pm\/whatsapp\/test$/, function (m, b) {
      if (!live()) throw E(409, "לא הוזנו Phone Number ID ואסימון");
      var to = waNumber(b.phone);
      if (!to) throw E(422, "מספר לא תקין");
      return graph("POST", "/" + live().phone_id + "/messages", { messaging_product: "whatsapp", to: to, type: "template", template: { name: "hello_world", language: { code: "en_US" } } })
        .then(function (r) { return { id: ((r.messages || [])[0] || {}).id }; });
    }],
    ["POST", /^\/pm\/whatsapp\/templates$/, function () { throw E(409, "במצב בדיקה של Meta לא צריך לשלוח תבניות לאישור"); }],
    ["POST", /^\/pm\/whatsapp\/check$/, function (m, b) { return { hits: check(b.text) }; }],
    ["PUT", /^\/pm\/whatsapp\/config$/, function (m, b) {
      if (b.send_hours) db.wa.send_hours = b.send_hours; if (b.reminder_time) db.wa.reminder_time = b.reminder_time;
      if (b.address !== undefined) db.wa.address = b.address; if (b.meta_names) db.wa.meta_names = b.meta_names;
      return { ok: true };
    }],
    ["PUT", /^\/pm\/gcal\/config$/, function (m, b) { if (b.title) db.gcal_title = b.title; return { ok: true }; }],
    ["GET", /^\/pm\/gcal\/start$/, function () { throw E(409, "במצב הדגמה אין חיבור ליומן גוגל"); }],
    ["POST", /^\/pm\/gcal\/(sync|disconnect)$/, function () { return { ok: true, pulled: 0, pushed: 0 }; }],
    ["PUT", /^\/pm\/prices$/, function (m, b) {
      var k = kindOf(db, b.kind);
      if (b.label) k.label = b.label; if (b.minutes > 0) k.minutes = b.minutes; if (b.price >= 0) k.price = b.price;
      return { ok: true };
    }],
    ["PUT", /^\/pm\/workdays$/, function (m, b) { db.workdays = (b.days || []).map(Number); return { ok: true }; }],
    ["PUT", /^\/pm\/days-off$/, function (m, b) { if (!b.day) throw E(422, "day is required"); db.days_off[b.day] = b.label || "חופש"; return { ok: true }; }],
    ["POST", /^\/pm\/backup$/, function () { db.backup = { file: "records-" + stamp(new Date()).replace(/[-:T]/g, "").slice(0, 12) + ".db.gz.enc (הדגמה)", at: now() }; return { file: db.backup.file }; }],
    ["POST", /^\/pm\/backup\/check$/, function () {
      return { file: db.backup.file, integrity: "ok", documents_opened: Object.keys(db.docs).length,
               counts: { records: db.records.length, documents: Object.keys(db.docs).length, pm_appointments: db.appts.length, pm_notes: db.notes.length } };
    }],

    // Clinical approvals (approvals.js): a signed log, kept in this tab only.
    ["GET", /^\/kb\/decisions$/, function () {
      var latest = {};
      db.kb.forEach(function (row) { if (row.action === "reset") delete latest[row.key]; else latest[row.key] = row; });
      return { decisions: Object.keys(latest).map(function (k) { return latest[k]; }), total_rows: db.kb.length, chain_ok: true, chain: db.kb.length + " decisions, chain intact (הדגמה)" };
    }],
    ["POST", /^\/kb\/decisions$/, function (m, b) {
      var saved = (b.decisions || []).map(function (d) {
        var row = Object.assign({}, d, { seq: db.kb.length + 1, actor: "clinician:demo", at: now(), hash: Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2) });
        db.kb.push(row); return row;
      });
      return { saved: saved };
    }],
    ["GET", /^\/kb\/log$/, function () { return { rows: db.kb.slice().reverse(), total_rows: db.kb.length }; }]
  ];
  function need(id) { var r = rec(id); if (!r) throw E(404, "no such record"); return r; }
  // Patient pages sit next to this page: app/interview/patient.html beside app/interview/index.html in the
  // repository, docs/app/patient.html beside docs/index.html on GitHub Pages (https://<user>.github.io/<repo>/).
  function pageUrl(name, token) {
    var dir = location.pathname.replace(/[^/]*$/, "");
    var rel = /\/app\/interview\/$/.test(dir) ? name : "app/" + name;
    return location.origin + dir + rel + "#" + token;
  }
  function link(r) {
    var t = "demo-" + Math.random().toString(36).slice(2, 14);
    return { record_id: r.record_id, patient_token: t, patient_path: "/app/patient.html#" + t, patient_url: pageUrl("patient.html", t), expires_at: r.link_expires_at };
  }
  function gcal() { return { configured: false, connected: false, read_calendars: ["primary"], clinic_calendar: null, title: db.gcal_title, last_sync: null, last_error: null }; }

  function answer(method, path, body) {
    load();
    var qi = path.indexOf("?"), query = {};
    if (qi !== -1) { path.slice(qi + 1).split("&").forEach(function (kv) { var p = kv.split("="); query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ""); }); path = path.slice(0, qi); }
    if (!db.signed_in && !/^\/(health|login)$/.test(path)) return reply(401, { detail: "sign in first" });
    for (var i = 0; i < routes.length; i++) {
      var rt = routes[i], m = rt[0] === method && rt[1].exec(path);
      if (!m) continue;
      try {
        var out = rt[2](m, body || {}, query);
        save(); banner();
        if (out && typeof out.then === "function") {
          return out.then(function (o) { save(); return reply(200, o); }, function (e) { save(); return reply(e.status || 502, { detail: e.message }); });
        }
        if (method !== "GET") setTimeout(liveTick, 50);
        return reply(200, out);
      }
      catch (e) { return reply(e.status || 500, { detail: e.message }); }
    }
    return reply(404, { detail: "not in the demo" });
  }
  function reply(status, body) { return new Response(JSON.stringify(body), { status: status, headers: { "Content-Type": "application/json" } }); }

  // ---- live WhatsApp from the demo: Meta's test number, called straight from this browser ----
  // The Phone Number ID and the temporary token live only in this tab's sessionStorage (never in the page,
  // the repository or any server). graph.facebook.com answers browsers (CORS *). Test-number rules: Hebrew
  // goes as plain text, which Meta allows within 24 hours of the recipient writing to the number; when Meta
  // refuses it, Meta's approved "hello_world" goes instead. Invented patients (050-00000xx) are never sent to.
  var LIVE_KEY = "tcm-demo-wa-live", GRAPH = "https://graph.facebook.com/v26.0";
  function live() { try { return JSON.parse(sessionStorage.getItem(LIVE_KEY) || "null"); } catch (e) { return null; } }
  function waNumber(p) {
    var d = String(p || "").replace(/\D/g, "");
    if (d.indexOf("00") === 0) d = d.slice(2);
    if (d.charAt(0) === "0") d = "972" + d.slice(1);
    return d.length >= 11 && d.length <= 15 ? d : null;
  }
  function invented(phone) { return /^0?50-?0{5}\d\d$/.test(String(phone || "").replace(/\s/g, "")); }
  function graph(method, path, body) {
    var L = live();
    return realFetch(GRAPH + path, { method: method, headers: Object.assign({ Authorization: "Bearer " + L.token }, body ? { "Content-Type": "application/json" } : {}),
                                     body: body ? JSON.stringify(body) : undefined })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.ok) return j;
          var er = j.error || {}, e = new Error("Meta " + r.status + (er.code ? " (code " + er.code + ")" : "") + ": " + (((er.error_data || {}).details) || er.message || "error"));
          if (er.code === 100) e.message = "Meta לא מכירה את ה־Phone Number ID שהוזן. כנראה הוזן מספר הטלפון במקום ה־ID: ב־API Setup ה־ID מופיע מתחת למספר הטלפון, ליד הכיתוב Phone number ID. (" + e.message + ")";
          if (er.code === 131047 || er.code === 131030) e.message = "(code " + er.code + ") " + e.message;
          if (er.code === 190) e.message = "האסימון פג או שגוי. צריך להפיק אסימון זמני חדש ב־API Setup ולחבר מחדש. (" + e.message + ")";
          e.status = 502; throw e;
        });
      });
  }
  function sendLive(to, text) {
    var pid = live().phone_id;
    return graph("POST", "/" + pid + "/messages", { messaging_product: "whatsapp", to: to, type: "text", text: { body: text, preview_url: false } })
      .catch(function () { return graph("POST", "/" + pid + "/messages", { messaging_product: "whatsapp", to: to, type: "template", template: { name: "hello_world", language: { code: "en_US" } } }); });
  }
  var ticking = false;
  function liveTick() {
    if (!db || !live() || ticking) return;
    var t = now(), due = db.queue.filter(function (q) { return q.status === "pending" && q.due_at <= t; });
    due.forEach(function (q) {
      var a = db.appts.filter(function (x) { return x.id === q.appt_id; })[0];
      if (a && a.ts <= t) q.status = "missed";
    });
    var r, a, list = due.filter(function (q) { return q.status === "pending"; });
    var q = list.filter(function (x) { var rr = rec(x.record_id); return rr && rr.identity && !invented(rr.identity.phone) && waNumber(rr.identity.phone) && hasConsent(db, x.record_id, "whatsapp"); })[0];
    save();
    if (!q) return;
    r = rec(q.record_id); a = db.appts.filter(function (x) { return x.id === q.appt_id; })[0];
    ticking = true;
    sendLive(waNumber(r.identity.phone), render(q.template, r, a, {})).then(function () {
      q.status = "sent"; q.sent_at = now();
      db.messages.push({ id: rid("M"), record_id: q.record_id, template: q.template, channel: "cloud_api", status: "sent", at: now() });
    }, function (e) { q.status = "failed"; q.last_error = e.message.slice(0, 300); }).then(function () { ticking = false; save(); setTimeout(liveTick, 500); });
  }
  setInterval(function () { if (db) liveTick(); }, 30000);

  // A clear label on every screen while the demo answers.
  var shown = false;
  function banner() {
    if (shown || !document.body) return;
    var wrap = document.querySelector(".wrap");
    if (!wrap) return;
    shown = true;
    var b = document.createElement("div");
    b.className = "demo-banner";
    b.setAttribute("role", "note");
    b.innerHTML = "<b>מצב הדגמה</b><span>אין כאן שרת קליניקה. כל המטופלים בדויים, ושום דבר לא נשלח או נשמר מחוץ ללשונית הזאת. " +
      "וואטסאפ נשלח באמת רק אם חיברת את מספר הבדיקה של Meta בלשונית ניהול הקליניקה, ורק למספר שהזנת בעצמך. יומן גוגל לא מחובר.</span>";
    var reset = document.createElement("button");
    reset.type = "button"; reset.className = "mini"; reset.textContent = "איפוס נתוני ההדגמה";
    reset.addEventListener("click", function () { try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ } location.hash = ""; location.reload(); });
    b.appendChild(reset);
    var css = document.createElement("style");
    css.textContent = ".demo-banner{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;margin:0 0 14px;padding:10px 16px;border-radius:18px;" +
      "border:1px dashed color-mix(in srgb,var(--amber) 60%,transparent);background:color-mix(in srgb,var(--amber-soft) 55%,var(--glass));font-size:.9rem}" +
      ".demo-banner b{color:var(--amber);letter-spacing:.02em}.demo-banner span{flex:1;min-width:14em;color:var(--ink)}";
    document.head.appendChild(css);
    var nav = document.querySelector("nav.tabs");
    if (nav && nav.parentNode === wrap) wrap.insertBefore(b, nav); else wrap.insertBefore(b, wrap.firstChild);
  }

  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var rel = url.indexOf(location.origin) === 0 ? url.slice(location.origin.length) : url;
    if (rel.indexOf(API + "/") !== 0) return realFetch(input, init);
    var method = ((init && init.method) || "GET").toUpperCase(), body = null;
    try { body = init && init.body ? JSON.parse(init.body) : null; } catch (e) { body = null; }
    return detect().then(function (m) {
      if (m === "real") return realFetch(input, init);
      return answer(method, rel.slice(API.length), body);
    });
  };
  window.TCMDemoServer = { active: function () { return detect().then(function (m) { return m === "demo"; }); }, reset: function () { db = seed(); db.day = iso(new Date()); save(); } };

  // A plain signature for the invented consent forms.
  var SIG = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="260" height="90"><path d="M10 60 C40 10 60 90 90 40 S140 70 160 30 S220 60 250 45" fill="none" stroke="#1d2216" stroke-width="2.5" stroke-linecap="round"/><text x="10" y="85" font-size="11" fill="#777">הדגמה</text></svg>');
})();
