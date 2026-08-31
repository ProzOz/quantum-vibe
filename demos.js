/* Quantum Vibe — canned teaching circuits. Always valid, 1–4 qubits. */
(function (global) {
  "use strict";

  function demo(id, n, gates, extra) {
    var d = {
      id: id,
      circuit: { n: n, gates: gates, shots: 1024 }
    };
    for (var k in extra) d[k] = extra[k];
    return d;
  }

  var DEMOS = {
    bell: demo("bell", 2, [
      { type: "h", q: 0 },
      { type: "cx", a: 0, b: 1 }
    ], {
      title: { en: "Bell pair / entanglement", th: "คู่เบลล์ / ความพันกัน" },
      explain: {
        en: "H on q0, then CNOT onto q1, makes a Bell pair. Local shots should land mostly on 00 and 11 — correlated, not a real QPU.",
        th: "H ที่ q0 แล้ว CNOT ไป q1 สร้างคู่เบลล์ การวัดในเครื่องนี้มักได้ 00 กับ 11 พร้อมกัน — ความสัมพันธ์จากซิมท้องถิ่น ไม่ใช่ QPU จริง"
      },
      mapNote: {
        en: "Mapped to a 2-qubit Bell teaching circuit.",
        th: "จับคู่เป็นวงจรสอนคู่เบลล์ 2 คิวบิต"
      }
    }),

    super: demo("super", 2, [
      { type: "h", q: 0 },
      { type: "h", q: 1 }
    ], {
      title: { en: "1–2 qubit superposition", th: "ซูเปอร์โพซิชัน 1–2 คิวบิต" },
      explain: {
        en: "Hadamard on two qubits. Ideal probabilities are 25% on each of 00, 01, 10, 11. Shot noise will wiggle the bars.",
        th: "Hadamard สองคิวบิต ความน่าจะเป็นในอุดมคติคือ 25% ที่ 00, 01, 10, 11 แท่งกราฟจะสั่นเล็กน้อยจากจำนวนช็อต"
      },
      mapNote: {
        en: "Mapped to a 2-qubit equal-superposition teaching circuit.",
        th: "จับคู่เป็นวงจรสอนซูเปอร์โพซิชันเท่ากัน 2 คิวบิต"
      }
    }),

    grover: demo("grover", 2, [
      { type: "h", q: 0 },
      { type: "h", q: 1 },
      { type: "cz", a: 0, b: 1 },
      { type: "h", q: 0 },
      { type: "h", q: 1 },
      { type: "x", q: 0 },
      { type: "x", q: 1 },
      { type: "cz", a: 0, b: 1 },
      { type: "x", q: 0 },
      { type: "x", q: 1 },
      { type: "h", q: 0 },
      { type: "h", q: 1 }
    ], {
      title: { en: "2-qubit Grover-style toy", th: "โกรเวอร์ของเล่น 2 คิวบิต" },
      explain: {
        en: "One Grover iteration on 2 qubits, marking |11>. A toy search, not a database and not quantum advantage.",
        th: "โกรเวอร์หนึ่งรอบบน 2 คิวบิต ทำเครื่องหมาย |11> เป็นของเล่นสอน ไม่ใช่การค้นฐานข้อมูล และไม่ใช่ quantum advantage"
      },
      mapNote: {
        en: "Mapped to a 2-qubit Grover-style toy (marked |11>).",
        th: "จับคู่เป็นโกรเวอร์ของเล่น 2 คิวบิต (ทำเครื่องหมาย |11>)"
      }
    }),

    traffic: demo("traffic", 4, [
      { type: "h", q: 0 }, { type: "h", q: 1 }, { type: "h", q: 2 }, { type: "h", q: 3 },
      { type: "cz", a: 0, b: 1 }, { type: "cz", a: 1, b: 2 }, { type: "cz", a: 2, b: 3 }, { type: "cz", a: 3, b: 0 },
      { type: "rz", q: 0, theta: 0.8 }, { type: "rz", q: 1, theta: 0.8 },
      { type: "rz", q: 2, theta: 0.8 }, { type: "rz", q: 3, theta: 0.8 },
      { type: "rx", q: 0, theta: 0.7 }, { type: "rx", q: 1, theta: 0.7 },
      { type: "rx", q: 2, theta: 0.7 }, { type: "rx", q: 3, theta: 0.7 }
    ], {
      title: { en: "Optimization sketch (traffic toy)", th: "สเก็ตช์ออปติไมซ์ (ของเล่นจราจร)" },
      explain: {
        en: "A 4-qubit QAOA-style sketch. City-scale traffic is mapped to a tiny teaching circuit. This does not optimize Bangkok, flood routing, or any real network.",
        th: "สเก็ตช์แบบ QAOA 4 คิวบิต จราจรระดับเมืองถูกย่อเป็นวงจรสอนขนาดจิ๋ว ไม่ได้ปรับจราจรกรุงเทพ เส้นทางน้ำท่วม หรือโครงข่ายจริงใดๆ"
      },
      mapNote: {
        en: "Mapped to a 4-qubit optimization sketch — a toy, not Bangkok solved.",
        th: "จับคู่เป็นสเก็ตช์ออปติไมซ์ 4 คิวบิต — ของเล่น ไม่ได้แก้กรุงเทพ"
      }
    }),

    dengue: demo("dengue", 3, [
      { type: "h", q: 0 }, { type: "h", q: 1 }, { type: "h", q: 2 },
      { type: "cx", a: 0, b: 1 }, { type: "rz", q: 1, theta: 1.1 }, { type: "cx", a: 0, b: 1 },
      { type: "cx", a: 1, b: 2 }, { type: "rz", q: 2, theta: 0.9 }, { type: "cx", a: 1, b: 2 },
      { type: "rx", q: 0, theta: 0.6 }, { type: "rx", q: 1, theta: 0.6 }, { type: "rx", q: 2, theta: 0.6 }
    ], {
      title: { en: "Optimization sketch (molecule toy)", th: "สเก็ตช์ออปติไมซ์ (ของเล่นโมเลกุล)" },
      explain: {
        en: "A 3-qubit encoding sketch. Real drug screening is mapped to a tiny teaching circuit. This does not screen molecules, diagnose dengue, or make a clinical claim.",
        th: "สเก็ตช์เข้ารหัส 3 คิวบิต การคัดกรองยาจริงถูกย่อเป็นวงจรสอนขนาดจิ๋ว ไม่ได้คัดโมเลกุล วินิจฉัยไข้เลือดออก หรืออ้างทางคลินิก"
      },
      mapNote: {
        en: "Mapped to a 3-qubit optimization sketch — a toy, not a drug screen.",
        th: "จับคู่เป็นสเก็ตช์ออปติไมซ์ 3 คิวบิต — ของเล่น ไม่ใช่การคัดยา"
      }
    }),

    teach: demo("teach", 1, [
      { type: "h", q: 0 },
      { type: "z", q: 0 },
      { type: "h", q: 0 }
    ], {
      title: { en: "Teaching circuit (interference)", th: "วงจรสอน (แทรกสอด)" },
      explain: {
        en: "H–Z–H on one qubit: superposition, a phase kick, then interference. Related teaching topics also appear in the separate Quantum Experience project (credited in About). Local sim only.",
        th: "H–Z–H หนึ่งคิวบิต: ซูเปอร์โพซิชัน, เฟส, แล้วแทรกสอด หัวข้อสอนแนวนี้มีในโปรเจกต์แยก Quantum Experience ด้วย (เครดิตใน About) ซิมท้องถิ่นเท่านั้น"
      },
      mapNote: {
        en: "Mapped to a 1-qubit interference teaching circuit.",
        th: "จับคู่เป็นวงจรสอนแทรกสอด 1 คิวบิต"
      }
    })
  };

  var CHIPS = [
    { id: "bell", en: "Bell pair / entanglement", th: "คู่เบลล์ / ความพันกัน" },
    { id: "super", en: "1–2 qubit superposition", th: "ซูเปอร์โพซิชัน 1–2 คิวบิต" },
    { id: "grover", en: "2-qubit Grover-style toy", th: "โกรเวอร์ของเล่น 2 คิวบิต" }
  ];

  function score(text, words) {
    var t = text.toLowerCase();
    var s = 0;
    for (var i = 0; i < words.length; i++) {
      if (t.indexOf(words[i].toLowerCase()) !== -1) s += 1;
    }
    return s;
  }

  function mapPrompt(raw) {
    var text = (raw || "").trim();
    if (!text) return { id: "super", reason: "empty" };

    var scores = {
      bell: score(text, ["bell", "entangle", "epr", "เบลล์", "พันกัน", "คู่เบลล์", "entanglement"]),
      super: score(text, ["superpos", "superposition", "hadamard", "ซ้อนทับ", "ซูเปอร์โพซิชัน", "ซูเปอร์โพซิชั่น"]),
      grover: score(text, ["grover", "search", "oracle", "โกรเวอร์", "ค้นหา"]),
      traffic: score(text, ["traffic", "bangkok", "flood", "optimize bangkok", "จราจร", "กรุงเทพ", "น้ำท่วม", "bang kok"]),
      dengue: score(text, ["molecule", "dengue", "screen", "drug", "โมเลกุล", "ไข้เลือดออก", "คัดกรอง"]),
      teach: score(text, ["experience", "teach", "interference", "phase", "ramsey", "สอน", "แทรกสอด", "ควอนตัมฟิสิกส์", "quantum experience"])
    };

    var best = "super", bestS = 0;
    for (var id in scores) {
      if (scores[id] > bestS) { bestS = scores[id]; best = id; }
    }
    if (bestS === 0) best = "super";
    return { id: best, reason: bestS === 0 ? "fallback-superposition" : "keyword" };
  }

  var api = { DEMOS: DEMOS, CHIPS: CHIPS, mapPrompt: mapPrompt };
  global.QVDemos = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : global);
