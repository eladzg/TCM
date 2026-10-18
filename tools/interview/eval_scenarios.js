// Runs the sample cases of app/interview/demo_cases.js through the engine and prints where the
// expected pattern ranked, as JSON lines plus a summary. Usage:
//   node tools/interview/eval_scenarios.js            # the curated cases
//   node tools/interview/eval_scenarios.js 200        # also 200 random cases built from patterns
"use strict";
const path = require("path");
const fs = require("fs");
const APP = path.join(__dirname, "..", "..", "app", "interview");
global.window = global;
for (const f of ["kb.js"]) new Function(fs.readFileSync(path.join(APP, f), "utf8"))();
const { createEngine } = require(path.join(APP, "engine.js"));
const D = require(path.join(APP, "demo_cases.js"));
const kb = global.TCM_KB;
const E = createEngine(kb);
const known = new Set(kb.syndromes.map((s) => s.id));
const feats = new Set(kb.features.map((f) => f.id));

function evalCase(c) {
  const bad = c.expect.filter((id) => !known.has(id)).concat(c.yes.concat(c.tongue, c.pulse).filter((id) => !feats.has(id)));
  if (bad.length) throw new Error(c.id + ": unknown ids " + bad.join(", "));
  const state = E.newState({});
  const obj = D.run(E, state, c);
  if (obj.halted || c.halt) return { id: c.id, halted: !!obj.halted, halt_expected: !!c.halt };
  E.setObjective(state, "tongue", obj.tongue);
  E.setObjective(state, "pulse", obj.pulse);
  const best = D.rankOf(E, state, c);
  const top = E.score(state).filter((x) => x.score > 0)[0];
  return { id: c.id, rank: best ? best.rank : null, matched: best ? best.id : null, top: top ? top.syndrome.id : null, asked: state.asked.length };
}

function summary(rows) {
  const halted = rows.filter((r) => r.halted).length;
  const haltMissed = rows.filter((r) => r.halt_expected && !r.halted).length;
  const haltWrong = rows.filter((r) => r.halted && !r.halt_expected).length;
  rows = rows.filter((r) => !r.halted && !r.halt_expected);
  const n = rows.length, at = (k) => rows.filter((r) => r.rank && r.rank <= k).length;
  return { n, halted, halt_missed: haltMissed, halt_unexpected: haltWrong, top1: at(1), top3: at(3), top5: at(5) };
}

const curated = D.CASES.map(evalCase);
const out = { curated, curated_summary: summary(curated) };
const nRandom = Number(process.argv[2] || 0);
if (nRandom) {
  const rnd = [];
  for (let s = 1; s <= nRandom; s++) rnd.push(evalCase(D.random(kb, s)));
  out.random_summary = summary(rnd);
  out.random_misses = rnd.filter((r) => !r.halted && (!r.rank || r.rank > 5)).slice(0, 20);
}
console.log(JSON.stringify(out, null, 1));
