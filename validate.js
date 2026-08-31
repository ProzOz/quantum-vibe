/* Quantum Vibe — planner JSON validator (browser). Duplicate logic lives in proxy.py. */
(function (global) {
  "use strict";

  var ALLOWED_OPS = {
    H: 1, X: 1, Y: 1, Z: 1, S: 1, T: 1,
    CX: 1, CZ: 1, SWAP: 1, RX: 1, RY: 1, RZ: 1
  };
  var ONEQ = { H: 1, X: 1, Y: 1, Z: 1, S: 1, T: 1 };
  var TWOQ = { CX: 1, CZ: 1, SWAP: 1 };
  var ROT = { RX: 1, RY: 1, RZ: 1 };
  var MAX_GATES = 20;

  function isInt(n) {
    return typeof n === "number" && isFinite(n) && Math.floor(n) === n;
  }

  function asString(v) {
    if (v == null) return "";
    if (typeof v === "string") return v;
    return String(v);
  }

  function validatePlan(raw) {
    if (raw == null || typeof raw !== "object" || Array.isArray(raw)) {
      return { ok: false, error: "plan must be a JSON object" };
    }
    var qubits = raw.qubits;
    if (typeof qubits === "string" && qubits.trim() !== "" && isFinite(Number(qubits))) {
      qubits = Number(qubits);
    }
    if (!isInt(qubits) || qubits < 1 || qubits > 4) {
      return { ok: false, error: "qubits must be an integer 1–4" };
    }

    var gates = raw.gates;
    if (!Array.isArray(gates)) return { ok: false, error: "gates must be an array" };
    if (gates.length > MAX_GATES) return { ok: false, error: "at most 20 gates" };

    var outGates = [];
    for (var i = 0; i < gates.length; i++) {
      var g = gates[i];
      if (!g || typeof g !== "object") {
        return { ok: false, error: "gate " + i + " is not an object" };
      }
      var op = asString(g.op).trim().toUpperCase();
      if (!ALLOWED_OPS[op]) {
        return { ok: false, error: "unknown gate: " + (g.op == null ? "(missing)" : String(g.op)) };
      }
      var q = g.q;
      if (typeof q === "string" && q.trim() !== "" && isFinite(Number(q))) q = Number(q);
      if (!isInt(q) || q < 0 || q >= qubits) {
        return { ok: false, error: "gate " + i + " (" + op + "): q must be in 0.." + (qubits - 1) };
      }

      if (ONEQ[op]) {
        outGates.push({ op: op, q: q });
      } else if (TWOQ[op]) {
        var t = g.t;
        if (typeof t === "string" && t.trim() !== "" && isFinite(Number(t))) t = Number(t);
        if (!isInt(t) || t < 0 || t >= qubits) {
          return { ok: false, error: "gate " + i + " (" + op + "): t must be in 0.." + (qubits - 1) };
        }
        if (q === t) {
          return { ok: false, error: "gate " + i + " (" + op + "): q and t must be distinct" };
        }
        outGates.push({ op: op, q: q, t: t });
      } else if (ROT[op]) {
        var theta = g.theta;
        if (typeof theta === "string" && theta.trim() !== "") theta = Number(theta);
        if (typeof theta !== "number" || !isFinite(theta)) {
          return { ok: false, error: "gate " + i + " (" + op + "): theta must be a finite number" };
        }
        outGates.push({ op: op, q: q, theta: theta });
      }
    }

    var plan = {
      title: asString(raw.title),
      qubits: qubits,
      gates: outGates,
      explain_th: asString(raw.explain_th),
      explain_en: asString(raw.explain_en),
      mapping: asString(raw.mapping),
      is_toy: true
    };
    return { ok: true, plan: plan };
  }

  function toSimCircuit(plan, shots) {
    var n = plan.qubits;
    var gates = [];
    for (var i = 0; i < plan.gates.length; i++) {
      var g = plan.gates[i];
      var type = g.op.toLowerCase();
      if (type === "cx" || type === "cz" || type === "swap") {
        gates.push({ type: type, a: g.q, b: g.t });
      } else if (type === "rx" || type === "ry" || type === "rz") {
        gates.push({ type: type, q: g.q, theta: g.theta });
      } else {
        gates.push({ type: type, q: g.q });
      }
    }
    return { n: n, gates: gates, shots: shots == null ? 1024 : shots };
  }

  var api = {
    validatePlan: validatePlan,
    toSimCircuit: toSimCircuit,
    ALLOWED_OPS: ALLOWED_OPS,
    MAX_GATES: MAX_GATES
  };
  global.QVValidate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : global);
