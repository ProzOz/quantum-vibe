/* Node tests for ภาษาคน story bind + Wukong fingerprint bind.
 * Reuses cached Bell-like counts (35%/65%). Does not call Origin. */
"use strict";

var fs = require("fs");
var vm = require("vm");
var path = require("path");

var store = {};
var fetchCalls = [];

function el(tag) {
  var node = {
    tagName: String(tag || "div").toUpperCase(),
    id: "",
    className: "",
    textContent: "",
    innerHTML: "",
    style: {},
    hidden: false,
    disabled: false,
    value: "",
    children: [],
    attrs: {},
    listeners: {},
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getAttribute: function (k) { return this.attrs[k]; },
    appendChild: function (c) { this.children.push(c); return c; },
    addEventListener: function (ev, fn) {
      this.listeners[ev] = this.listeners[ev] || [];
      this.listeners[ev].push(fn);
    },
    removeChild: function () {},
    setAttributeNS: function () {}
  };
  return node;
}

var ids = {};
["results", "btnRegen", "btnCopy", "btnRun", "btnEn", "btnTh", "btnAbout",
  "btnSettings", "about", "settings", "wukongModal", "prompt", "honesty",
  "labLine", "sub", "sisterLink", "examples", "examplesLabel", "promptLabel",
  "chips", "titleTh", "titleEn", "empty"].forEach(function (id) {
  ids[id] = el(id === "prompt" ? "textarea" : "div");
  ids[id].id = id;
});

var document = {
  body: el("body"),
  documentElement: el("html"),
  getElementById: function (id) { return ids[id] || null; },
  createElement: function (tag) { return el(tag); },
  createElementNS: function (ns, tag) { return el(tag); },
  createTextNode: function (t) { return { textContent: t }; },
  addEventListener: function () {},
  querySelector: function () { return null; }
};

var localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
  setItem: function (k, v) { store[k] = String(v); },
  removeItem: function (k) { delete store[k]; },
  clear: function () { store = {}; }
};

var ctx = {
  localStorage: localStorage,
  document: document,
  location: { hash: "" },
  fetch: function () {
    fetchCalls.push([].slice.call(arguments));
    return Promise.reject(new Error("fetch must not run in bind tests"));
  },
  navigator: { clipboard: null },
  addEventListener: function () {},
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval,
  AbortController: AbortController,
  JSON: JSON,
  Math: Math,
  Date: Date,
  Number: Number,
  String: String,
  Array: Array,
  Object: Object,
  Boolean: Boolean,
  RegExp: RegExp,
  Error: Error,
  parseInt: parseInt,
  isFinite: isFinite,
  encodeURIComponent: encodeURIComponent
};
ctx.window = ctx;
ctx.global = ctx;
vm.createContext(ctx);

function load(file) {
  var code = fs.readFileSync(path.join(__dirname, file), "utf8");
  vm.runInContext(code, ctx, { filename: file });
}

store["qv-lang"] = "th";
load("sim.js");
load("demos.js");
load("validate.js");
load("app.js");

var QVSim = ctx.QVSim;
var QVDemos = ctx.QVDemos;
var QVApp = ctx.QVApp;
var failed = 0;

function eq(name, got, want) {
  if (got !== want) {
    failed++;
    console.error("FAIL " + name + "\n  got:  " + JSON.stringify(got) + "\n  want: " + JSON.stringify(want));
  } else {
    console.log("ok   " + name);
  }
}

function ok(name, cond, detail) {
  if (!cond) {
    failed++;
    console.error("FAIL " + name + (detail ? " — " + detail : ""));
  } else {
    console.log("ok   " + name);
  }
}

function packOf(id) {
  var demo = QVDemos.DEMOS[id];
  var sim = QVSim.simulate(demo.circuit, 0xC0FFEE);
  return {
    source: "preset",
    id: id,
    demo: demo,
    circuit: demo.circuit,
    sim: sim,
    qasm: QVSim.toQasm(demo.circuit)
  };
}

function leftoverBellRec(extra) {
  var rec = {
    jobId: QVApp.KNOWN_BELL_JOB_ID,
    counts: { "00": 90, "11": 166 },
    percents: { "00": 35.15625, "11": 64.84375 },
    shots: 256,
    n: 2,
    rawResult: { "00": 90, "11": 166 },
    status: "finished",
    savedAt: 1,
    title: "Bell pair / entanglement"
  };
  extra = extra || {};
  Object.keys(extra).forEach(function (k) { rec[k] = extra[k]; });
  return rec;
}

function storyText(pack) {
  return QVApp.humanCardLines(pack, pack.sim).join("\n");
}

function assertCleanStory(name, pack) {
  var lines = QVApp.humanCardLines(pack, pack.sim);
  ok(name + " max 4 lines", lines.length <= 4, String(lines.length));
  ok(name + " has lines", lines.length >= 1);
  var blob = lines.join("\n");
  ok(name + " no percent", !/%/.test(blob), blob);
  ok(name + " no leftover 35/64", !/\b35\b/.test(blob) && !/\b64\b/.test(blob), blob);
  ok(name + " no Job ID", !/job\s*id/i.test(blob) && blob.indexOf(QVApp.KNOWN_BELL_JOB_ID) === -1, blob);
  ok(name + " no 1024/256 lecture", !/\b1024\b/.test(blob) && !/\b256\b/.test(blob), blob);
  ok(name + " no qubit lecture", !/qubit|ควิบิต|คิวบิต/i.test(blob), blob);
  return lines;
}

// --- ภาษาคน hard-bind ---
eq("kind grover", QVApp.screenCircuitKind(packOf("grover")), "grover");
eq("kind bell", QVApp.screenCircuitKind(packOf("bell")), "bell");
eq("kind super", QVApp.screenCircuitKind(packOf("super")), "super");

var grover = packOf("grover");
var gLines = assertCleanStory("grover", grover);
ok("grover story names grover", /โกรเวอร์|เจอ/.test(gLines.join("\n")), gLines.join(" | "));
ok("grover story not Bell pair", !/คู่เบลล์/.test(gLines.join("\n")), gLines.join(" | "));

var groverWithBellHw = packOf("grover");
groverWithBellHw.wukongJobId = QVApp.KNOWN_BELL_JOB_ID;
groverWithBellHw.wukong = {
  ok: true,
  counts: { "00": 90, "11": 166 },
  percents: { "00": 35, "11": 64 },
  shots: 256,
  n: 2
};
groverWithBellHw.wukongRaw = { "00": 90, "11": 166 };
assertCleanStory("grover+leftover Bell HW", groverWithBellHw);
ok("grover+HW still grover kind", QVApp.screenCircuitKind(groverWithBellHw) === "grover");
ok("grover+HW story not Bell", !/คู่เบลล์/.test(storyText(groverWithBellHw)), storyText(groverWithBellHw));

var kimiGrover = {
  source: "kimi",
  id: null,
  prompt: "ทำโกรเวอร์ของเล่น",
  plan: {
    title: "Grover toy",
    mapping: "search toy, not a Bell pair / entanglement lecture",
    explain_th: "โกรเวอร์ของเล่น ไม่ใช่คู่เบลล์ 35% 64%",
    explain_en: "Grover toy not a Bell pair",
    qubits: 2,
    gates: []
  },
  circuit: QVDemos.DEMOS.grover.circuit,
  sim: QVSim.simulate(QVDemos.DEMOS.grover.circuit, 0xC0FFEE),
  qasm: QVSim.toQasm(QVDemos.DEMOS.grover.circuit)
};
eq("kimi grover kind despite Bell leftover words", QVApp.screenCircuitKind(kimiGrover), "grover");
assertCleanStory("kimi grover", kimiGrover);
ok("kimi grover story not Bell", !/คู่เบลล์/.test(storyText(kimiGrover)), storyText(kimiGrover));

var bellLines = assertCleanStory("bell", packOf("bell"));
ok("bell story is Bell", /คู่เบลล์/.test(bellLines.join("\n")), bellLines.join(" | "));

// --- fingerprint bind: cached Bell job must not paint on Grover ---
function resetJob(rec) {
  store = {};
  store["qv-lang"] = "th";
  if (rec) localStorage.setItem(QVApp.WUKONG_JOB_KEY, JSON.stringify(rec));
}

function bindCase(label, recExtra) {
  resetJob(leftoverBellRec(recExtra));
  var rec = QVApp.loadWukongJob();
  var pack = packOf("grover");
  QVApp.applySavedJobToPack(pack, rec);
  ok(label + " mismatch flag", pack.wukongMismatch === true);
  ok(label + " no attached counts", !pack.wukong, pack.wukong && JSON.stringify(pack.wukong.counts));
  ok(label + " does not match", QVApp.wukongMatchesCircuit(pack, rec) === false);
  ok(label + " is mismatch", QVApp.isWukongMismatch(pack) === true);
  ok(label + " display null", QVApp.wukongDisplay(pack) === null);
  eq(label + " panel mode", QVApp.wukongPanelMode(pack), "mismatch");
  QVApp.persistWukongJob(pack);
  var saved = QVApp.loadWukongJob();
  ok(label + " persist keeps Bell job id", saved && saved.jobId === QVApp.KNOWN_BELL_JOB_ID);
  var bellFp = QVApp.bellDemoFingerprint();
  ok(label + " persist does not write Grover fp", saved && saved.circuitFingerprint !== QVApp.circuitFingerprint(pack), saved && saved.circuitFingerprint);
  ok(label + " persist stamps Bell fp", saved && saved.circuitFingerprint === bellFp, saved && saved.circuitFingerprint);
  ok(label + " persist keeps Bell counts", saved && saved.counts && saved.counts["11"] === 166);
}

bindCase("known Bell, no stored fp", { circuitFingerprint: "" });
bindCase("known Bell, Bell fp", { circuitFingerprint: QVApp.bellDemoFingerprint() });
bindCase("known Bell, poisoned Grover fp", { circuitFingerprint: QVApp.circuitFingerprint(packOf("grover")) });

resetJob(leftoverBellRec({ circuitFingerprint: QVApp.bellDemoFingerprint() }));
var bellPack = packOf("bell");
QVApp.applySavedJobToPack(bellPack, QVApp.loadWukongJob());
ok("bell screen matches known Bell job", QVApp.wukongMatchesCircuit(bellPack) === true);
eq("bell screen panel bars", QVApp.wukongPanelMode(bellPack), "bars");
ok("bell screen has counts", !!(bellPack.wukong && bellPack.wukong.counts && bellPack.wukong.counts["00"] === 90));

resetJob(leftoverBellRec({ circuitFingerprint: "" }));
var groverRefresh = packOf("grover");
QVApp.applySavedJobToPack(groverRefresh, QVApp.loadWukongJob());
var parsedBell = { counts: { "00": 90, "11": 166 }, percents: { "00": 35, "11": 64 }, shots: 256, n: 2 };
QVApp.applyWukongParsed(groverRefresh, parsedBell, { device: "WK_C180" });
ok("force-refresh Grover does not attach Bell bars", groverRefresh.wukong == null);
ok("force-refresh Grover mismatch", groverRefresh.wukongMismatch === true);
eq("force-refresh Grover mode", QVApp.wukongPanelMode(groverRefresh), "mismatch");

ok("no Origin fetch", fetchCalls.length === 0, "fetches=" + fetchCalls.length);

var th = QVApp.I18N.th;
var en = QVApp.I18N.en;
ok("th origin free", /ฟรี/.test(th.originFree) && /ฟรี/.test(th.originBlockTitle), th.originFree);
ok("en origin free", /free/i.test(en.originFree) && /free/i.test(en.originBlockTitle), en.originFree);
ok("th origin is fridge chip", /ตู้เย็นจริง/.test(th.originWhat), th.originWhat);
ok("en origin is fridge chip", /fridge/i.test(en.originWhat), en.originWhat);
ok("th origin not always-paid warning", !/ไม่ฟรีเสมอไป/.test(th.originFree + th.originHow5));
ok("en origin not always-paid warning", !/not always free/i.test(en.originFree + (en.originHow5 || "")));
ok("th kimi optional", /ว่างได้/.test(th.moonshotKey), th.moonshotKey);
ok("en kimi optional", /optional/i.test(en.moonshotKey), en.moonshotKey);
ok("honesty banner stays th", /ของเล่น/.test(th.honesty) && /ไม่ได้ชนะ/.test(th.honesty), th.honesty);
ok("honesty banner stays en", /teaching|toys/i.test(en.honesty) && /do not beat/i.test(en.honesty), en.honesty);
ok("th origin no advantage claim as a feature", /ไม่ใช่ quantum advantage/.test(th.originToyNote), th.originToyNote);
ok("en origin no advantage claim as a feature", /not quantum advantage/i.test(en.originToyNote), en.originToyNote);
["originBlockTitle","originWhat","originFree","originHowTitle","originHow1","originHow2","originHow3","originHow4","originHow5","originPasteHere","originConsoleBtn","originToyNote","kimiSharedOn","kimiSharedOff","moonshotKeyHint"].forEach(function (k) {
  ok("th has " + k, typeof th[k] === "string" && th[k].length > 4, k + "=" + th[k]);
  ok("en has " + k, typeof en[k] === "string" && en[k].length > 4, k + "=" + en[k]);
});

if (failed) {
  console.error("\n" + failed + " failed");
  process.exit(1);
}
console.log("\nall bind tests passed");
