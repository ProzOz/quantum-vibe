/* Quantum Vibe — local 1–4 qubit statevector simulator. No QPU. */
(function (global) {
  "use strict";

  function c(re, im) { return [re, im || 0]; }
  function cadd(a, b) { return [a[0] + b[0], a[1] + b[1]]; }
  function cmul(a, b) { return [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]]; }
  function cabs2(a) { return a[0] * a[0] + a[1] * a[1]; }
  function cneg(a) { return [-a[0], -a[1]]; }

  var INV_SQRT2 = 1 / Math.sqrt(2);
  var KNOWN_GATES = {
    h: 1, x: 1, y: 1, z: 1, s: 1, sdg: 1, t: 1, tdg: 1,
    rx: 1, ry: 1, rz: 1, cx: 1, cz: 1, swap: 1, barrier: 1
  };

  function uH() {
    return [
      [c(INV_SQRT2), c(INV_SQRT2)],
      [c(INV_SQRT2), c(-INV_SQRT2)]
    ];
  }
  function uX() { return [[c(0), c(1)], [c(1), c(0)]]; }
  function uY() { return [[c(0), c(0, -1)], [c(0, 1), c(0)]]; }
  function uZ() { return [[c(1), c(0)], [c(0), c(-1)]]; }
  function uS() { return [[c(1), c(0)], [c(0), c(0, 1)]]; }
  function uSdg() { return [[c(1), c(0)], [c(0), c(0, -1)]]; }
  function uT() {
    var a = Math.SQRT1_2;
    return [[c(1), c(0)], [c(0), c(a, a)]];
  }
  function uTdg() {
    var a = Math.SQRT1_2;
    return [[c(1), c(0)], [c(0), c(a, -a)]];
  }
  function uRX(th) {
    var h = th / 2, co = Math.cos(h), si = Math.sin(h);
    return [[c(co), c(0, -si)], [c(0, -si), c(co)]];
  }
  function uRY(th) {
    var h = th / 2, co = Math.cos(h), si = Math.sin(h);
    return [[c(co), c(-si)], [c(si), c(co)]];
  }
  function uRZ(th) {
    var h = th / 2;
    return [[c(Math.cos(-h), Math.sin(-h)), c(0)], [c(0), c(Math.cos(h), Math.sin(h))]];
  }

  function apply1(amp, n, q, U) {
    var dim = 1 << n;
    var bit = 1 << q;
    var next = new Array(dim);
    for (var i = 0; i < dim; i++) {
      if ((i & bit) === 0) {
        var j = i | bit;
        var a0 = amp[i], a1 = amp[j];
        next[i] = cadd(cmul(U[0][0], a0), cmul(U[0][1], a1));
        next[j] = cadd(cmul(U[1][0], a0), cmul(U[1][1], a1));
      }
    }
    return next;
  }

  function applyCX(amp, n, ctrl, tgt) {
    var dim = 1 << n;
    var cb = 1 << ctrl, tb = 1 << tgt;
    var next = new Array(dim);
    for (var i = 0; i < dim; i++) {
      next[(i & cb) ? (i ^ tb) : i] = amp[i];
    }
    return next;
  }

  function applyCZ(amp, n, a, b) {
    var dim = 1 << n;
    var ab = (1 << a) | (1 << b);
    var next = amp.slice();
    for (var i = 0; i < dim; i++) {
      if ((i & ab) === ab) next[i] = cneg(amp[i]);
    }
    return next;
  }

  function applySWAP(amp, n, a, b) {
    var dim = 1 << n;
    var ba = 1 << a, bb = 1 << b;
    var next = amp.slice();
    var seen = {};
    for (var i = 0; i < dim; i++) {
      var ai = (i & ba) !== 0, bi = (i & bb) !== 0;
      if (ai !== bi) {
        var j = i ^ ba ^ bb;
        if (!seen[i] && !seen[j]) {
          next[i] = amp[j];
          next[j] = amp[i];
          seen[i] = 1;
          seen[j] = 1;
        }
      }
    }
    return next;
  }

  function mulberry32(seed) {
    var t = seed >>> 0;
    return function () {
      t += 0x6D2B79F5;
      var x = Math.imul(t ^ (t >>> 15), 1 | t);
      x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }

  function bitstring(i, n) {
    return i.toString(2).padStart(n, "0");
  }

  var ALLOWED = { h:1, x:1, y:1, z:1, s:1, sdg:1, t:1, tdg:1, rx:1, ry:1, rz:1, cx:1, cz:1, swap:1, barrier:1 };

  function validate(circuit) {
    if (!circuit || typeof circuit !== "object") return { ok: false, error: "no circuit" };
    var n = circuit.n | 0;
    if (n < 1 || n > 4) return { ok: false, error: "qubits must be 1–4" };
    var gates = circuit.gates;
    if (!Array.isArray(gates) || gates.length > 80) return { ok: false, error: "gate list invalid" };
    for (var i = 0; i < gates.length; i++) {
      var g = gates[i];
      if (!g || !ALLOWED[g.type]) return { ok: false, error: "unknown gate: " + (g && g.type) };
      if (g.type === "barrier") continue;
      if (g.type === "cx" || g.type === "cz" || g.type === "swap") {
        var a = g.a | 0, b = g.b | 0;
        if (a < 0 || b < 0 || a >= n || b >= n || a === b) return { ok: false, error: "bad two-qubit indices" };
      } else {
        var q = g.q | 0;
        if (q < 0 || q >= n) return { ok: false, error: "bad qubit index" };
        if (g.type === "rx" || g.type === "ry" || g.type === "rz") {
          if (typeof g.theta !== "number" || !isFinite(g.theta)) return { ok: false, error: "bad rotation" };
        }
      }
    }
    var shots = circuit.shots == null ? 1024 : (circuit.shots | 0);
    if (shots < 1 || shots > 8192) return { ok: false, error: "bad shots" };
    return { ok: true, n: n, shots: shots };
  }

  function simulate(circuit, seed) {
    var v = validate(circuit);
    if (!v.ok) return { ok: false, error: v.error };

    var n = v.n, dim = 1 << n;
    var amp = new Array(dim);
    for (var i = 0; i < dim; i++) amp[i] = c(i === 0 ? 1 : 0, 0);

    var gates = circuit.gates;
    for (var gi = 0; gi < gates.length; gi++) {
      var g = gates[gi];
      switch (g.type) {
        case "h": amp = apply1(amp, n, g.q, uH()); break;
        case "x": amp = apply1(amp, n, g.q, uX()); break;
        case "y": amp = apply1(amp, n, g.q, uY()); break;
        case "z": amp = apply1(amp, n, g.q, uZ()); break;
        case "s": amp = apply1(amp, n, g.q, uS()); break;
        case "sdg": amp = apply1(amp, n, g.q, uSdg()); break;
        case "t": amp = apply1(amp, n, g.q, uT()); break;
        case "tdg": amp = apply1(amp, n, g.q, uTdg()); break;
        case "rx": amp = apply1(amp, n, g.q, uRX(g.theta)); break;
        case "ry": amp = apply1(amp, n, g.q, uRY(g.theta)); break;
        case "rz": amp = apply1(amp, n, g.q, uRZ(g.theta)); break;
        case "cx": amp = applyCX(amp, n, g.a, g.b); break;
        case "cz": amp = applyCZ(amp, n, g.a, g.b); break;
        case "swap": amp = applySWAP(amp, n, g.a, g.b); break;
        case "barrier": break;
        default: return { ok: false, error: "unvalidated gate" };
      }
    }

    var probs = new Array(dim);
    var sum = 0;
    for (i = 0; i < dim; i++) {
      probs[i] = cabs2(amp[i]);
      sum += probs[i];
    }
    if (sum > 0) for (i = 0; i < dim; i++) probs[i] /= sum;

    var rng = mulberry32(seed == null ? 0xC0FFEE : (seed >>> 0));
    var counts = {};
    var shots = v.shots;
    for (var s = 0; s < shots; s++) {
      var r = rng(), acc = 0, pick = dim - 1;
      for (i = 0; i < dim; i++) {
        acc += probs[i];
        if (r <= acc) { pick = i; break; }
      }
      var key = bitstring(pick, n);
      counts[key] = (counts[key] || 0) + 1;
    }

    return {
      ok: true,
      n: n,
      shots: shots,
      counts: counts,
      probs: probs,
      bitstrings: probs.map(function (_, i) { return bitstring(i, n); })
    };
  }

  function toQasm(circuit) {
    var v = validate(circuit);
    if (!v.ok) return "// invalid circuit";
    var lines = [
      "OPENQASM 2.0;",
      'include "qelib1.inc";',
      "qreg q[" + v.n + "];",
      "creg c[" + v.n + "];"
    ];
    circuit.gates.forEach(function (g) {
      switch (g.type) {
        case "h": case "x": case "y": case "z": case "s": case "t":
          lines.push(g.type + " q[" + g.q + "];"); break;
        case "sdg": lines.push("sdg q[" + g.q + "];"); break;
        case "tdg": lines.push("tdg q[" + g.q + "];"); break;
        case "rx": lines.push("rx(" + g.theta + ") q[" + g.q + "];"); break;
        case "ry": lines.push("ry(" + g.theta + ") q[" + g.q + "];"); break;
        case "rz": lines.push("rz(" + g.theta + ") q[" + g.q + "];"); break;
        case "cx": lines.push("cx q[" + g.a + "],q[" + g.b + "];"); break;
        case "cz": lines.push("cz q[" + g.a + "],q[" + g.b + "];"); break;
        case "swap": lines.push("swap q[" + g.a + "],q[" + g.b + "];"); break;
        case "barrier": lines.push("barrier q;"); break;
      }
    });
    for (var q = 0; q < v.n; q++) lines.push("measure q[" + q + "] -> c[" + q + "];");
    return lines.join("\n");
  }

  function gateList(circuit) {
    if (!circuit || !circuit.gates) return [];
    return circuit.gates.filter(function (g) { return g.type !== "barrier"; }).map(function (g) {
      if (g.type === "cx") return "CX q" + g.a + "→q" + g.b;
      if (g.type === "cz") return "CZ q" + g.a + ",q" + g.b;
      if (g.type === "swap") return "SWAP q" + g.a + ",q" + g.b;
      if (g.theta != null) return g.type.toUpperCase() + "(" + (Math.round(g.theta * 1000) / 1000) + ") q" + g.q;
      return g.type.toUpperCase() + " q" + g.q;
    });
  }

  var api = {
    validate: validate,
    simulate: simulate,
    toQasm: toQasm,
    gateList: gateList,
    KNOWN_GATES: KNOWN_GATES
  };

  global.QVSim = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : global);
