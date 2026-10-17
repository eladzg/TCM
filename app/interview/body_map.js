// Schematic body map for the treatment plan: front and back figures with the course of each channel,
// its direction of flow (in the order of its point numbers) and the chosen points.
// SCHEMATIC ONLY: points are placed by hand-set anchors along each channel and interpolated between
// them by point number; the exact location is the AcuAtlas text shown next to every point.
(function (root) {
  "use strict";

  // [point number, view (F front / B back), x, y]. Figures are 200 x 420; channels are drawn on the
  // viewer's left half (the patient's right side in front, left side in back), lateral = smaller x.
  // A fifth element "jump" starts a new stroke (the line is not drawn from the previous anchor).
  var CH = {
    LU: [[1, "F", 72, 92], [2, "F", 70, 86], [3, "F", 58, 112], [5, "F", 41, 160], [7, "F", 34, 218], [9, "F", 32, 228], [10, "F", 28, 240], [11, "F", 23, 254]],
    LI: [[1, "B", 26, 268], [4, "B", 28, 242], [5, "B", 31, 228], [10, "B", 41, 168], [11, "B", 42, 158], [14, "B", 52, 122], [15, "B", 60, 88], [16, "B", 66, 80],
         [17, "F", 86, 68, "jump"], [18, "F", 88, 63], [19, "F", 97, 47], [20, "F", 95, 44]],
    ST: [[1, "F", 91, 40], [4, "F", 93, 51], [5, "F", 87, 57], [6, "F", 84, 52], [7, "F", 82, 42], [8, "F", 86, 22], [9, "F", 90, 66, "jump"], [12, "F", 80, 76],
         [13, "F", 80, 81], [17, "F", 80, 112], [18, "F", 80, 120], [19, "F", 88, 132], [25, "F", 88, 165], [30, "F", 88, 205], [31, "F", 80, 222],
         [34, "F", 78, 288], [35, "F", 78, 300], [36, "F", 76, 318], [41, "F", 80, 385], [44, "F", 80, 404], [45, "F", 79, 411]],
    SP: [[1, "F", 88, 411], [3, "F", 90, 400], [5, "F", 90, 387], [6, "F", 90, 365], [9, "F", 91, 312], [10, "F", 93, 290], [11, "F", 91, 250],
         [12, "F", 88, 212], [13, "F", 82, 200], [15, "F", 80, 165], [16, "F", 80, 145], [17, "F", 74, 120], [20, "F", 72, 96], [21, "F", 68, 130]],
    HT: [[1, "F", 70, 102], [2, "F", 60, 130], [3, "F", 53, 160], [4, "F", 45, 210], [7, "F", 40, 228], [8, "F", 38, 244], [9, "F", 36, 266]],
    SI: [[1, "B", 37, 266], [3, "B", 38, 246], [5, "B", 39, 228], [6, "B", 40, 220], [8, "B", 53, 160], [9, "B", 66, 104], [10, "B", 66, 94], [11, "B", 76, 110],
         [12, "B", 74, 92], [14, "B", 84, 84], [15, "B", 88, 80], [16, "F", 84, 63, "jump"], [17, "F", 83, 57], [18, "F", 88, 47], [19, "F", 81, 42]],
    BL: [[1, "F", 96, 36], [2, "F", 95, 30], [7, "B", 94, 18, "jump"], [10, "B", 94, 58], [11, "B", 92, 80], [13, "B", 92, 92], [15, "B", 92, 105],
         [17, "B", 92, 118], [18, "B", 92, 128], [20, "B", 92, 142], [23, "B", 92, 160], [25, "B", 92, 175], [28, "B", 93, 190], [30, "B", 93, 202],
         [31, "B", 96, 190, "jump"], [34, "B", 96, 205], [35, "B", 97, 211], [36, "B", 84, 224], [37, "B", 84, 255], [39, "B", 76, 296], [40, "B", 82, 298],
         [41, "B", 84, 84, "jump"], [44, "B", 84, 105], [47, "B", 84, 128], [52, "B", 84, 160], [54, "B", 84, 200], [55, "B", 82, 310],
         [57, "B", 82, 345], [58, "B", 78, 352], [60, "B", 74, 385], [62, "B", 74, 392], [65, "B", 76, 405], [67, "B", 74, 412]],
    KI: [[1, "B", 84, 408], [2, "F", 92, 400, "jump"], [3, "F", 92, 386], [6, "F", 92, 392], [7, "F", 93, 370], [10, "F", 93, 300], [11, "F", 96, 205],
         [16, "F", 96, 165], [21, "F", 96, 132], [22, "F", 92, 124], [27, "F", 92, 80]],
    PC: [[1, "F", 78, 110], [2, "F", 63, 120], [3, "F", 47, 160], [6, "F", 37, 214], [7, "F", 35, 228], [8, "F", 32, 242], [9, "F", 29, 270]],
    TE: [[1, "B", 33, 270], [3, "B", 33, 246], [4, "B", 34, 228], [5, "B", 36, 214], [10, "B", 47, 156], [14, "B", 60, 88], [15, "B", 70, 82], [16, "B", 82, 64],
         [17, "F", 79, 47, "jump"], [20, "F", 80, 31], [21, "F", 81, 39], [23, "F", 87, 32]],
    GB: [[1, "F", 88, 37], [2, "F", 81, 44], [3, "F", 83, 34], [4, "F", 84, 26], [7, "F", 82, 36], [8, "F", 81, 28], [13, "F", 88, 21], [14, "F", 92, 27],
         [15, "F", 92, 20], [19, "B", 90, 46, "jump"], [20, "B", 90, 56], [21, "B", 76, 82], [22, "F", 69, 108, "jump"], [24, "F", 74, 128],
         [25, "F", 66, 150], [26, "F", 66, 165], [29, "F", 66, 212], [30, "B", 76, 212, "jump"], [31, "F", 64, 255, "jump"], [34, "F", 68, 310],
         [39, "F", 71, 365], [40, "F", 73, 388], [41, "F", 75, 400], [44, "F", 76, 412]],
    LR: [[1, "F", 84, 412], [2, "F", 85, 405], [3, "F", 86, 398], [4, "F", 88, 386], [5, "F", 89, 350], [8, "F", 92, 300], [9, "F", 91, 270],
         [11, "F", 88, 212], [12, "F", 86, 207], [13, "F", 66, 150], [14, "F", 80, 128]],
    CV: [[1, "F", 100, 214], [2, "F", 100, 205], [4, "F", 100, 190], [6, "F", 100, 175], [8, "F", 100, 165], [12, "F", 100, 140], [15, "F", 100, 122],
         [17, "F", 100, 108], [22, "F", 100, 72], [24, "F", 100, 58]],
    GV: [[1, "B", 100, 212], [4, "B", 100, 165], [14, "B", 100, 78], [16, "B", 100, 56], [20, "B", 100, 18], [22, "F", 100, 16, "jump"], [24, "F", 100, 22],
         [25, "F", 100, 44], [26, "F", 100, 48], [28, "F", 100, 52]]
  };

  var NAME_HE = { LU: "ריאה", LI: "מעי גס", ST: "קיבה", SP: "טחול", HT: "לב", SI: "מעי דק", BL: "שלפוחית השתן", KI: "כליה",
                  PC: "קרום הלב", TE: "המחמם המשולש", GB: "כיס המרה", LR: "כבד", CV: "מרידיאן ההיריון (רן)", GV: "המרידיאן השולט (דו)" };
  var COLOR = { LU: "#7a8a99", LI: "#8c6d3f", ST: "#c27c0e", SP: "#a8862b", HT: "#c0392b", SI: "#d35400", BL: "#2c6e9b", KI: "#1f4e79",
                PC: "#a93266", TE: "#8e44ad", GB: "#2e8b57", LR: "#1e7a46", CV: "#6f6f6f", GV: "#8a8a8a" };

  // Left half of the body outline, top (neck) to crotch; mirrored for the right half.
  var HALF = [[92, 58], [92, 70], [64, 78], [56, 90], [50, 125], [40, 160], [30, 226], [22, 244], [21, 262], [26, 273], [37, 272], [40, 250], [42, 232],
              [54, 165], [62, 122], [70, 104], [70, 140], [66, 170], [64, 205], [62, 232], [67, 300], [73, 370], [72, 388], [69, 406], [72, 415],
              [92, 415], [92, 392], [91, 330], [94, 300], [98, 240], [100, 222]];

  function parse(id) {
    var m = /^([A-Z]+)(\d+)$/.exec(id);
    return m && CH[m[1]] ? { ch: m[1], n: +m[2] } : null;
  }

  // {view, x, y} of a point, interpolated between the anchors around its number.
  function place(id) {
    var p = parse(id);
    if (!p) return null;
    var a = CH[p.ch];
    for (var i = 0; i < a.length; i++) {
      if (a[i][0] === p.n) return { view: a[i][1], x: a[i][2], y: a[i][3] };
      if (a[i][0] > p.n) {
        var b = a[i - 1] || a[i], c = a[i];
        if (!a[i - 1] || b[1] !== c[1] || c[4] === "jump") {   // across a view change: nearer anchor's view
          var near = p.n - b[0] <= c[0] - p.n ? b : c;
          return { view: near[1], x: near[2], y: near[3] };
        }
        var t = (p.n - b[0]) / (c[0] - b[0]);
        return { view: c[1], x: b[2] + t * (c[2] - b[2]), y: b[3] + t * (c[3] - b[3]) };
      }
    }
    var last = a[a.length - 1];
    return { view: last[1], x: last[2], y: last[3] };
  }

  // Strokes of a channel per view: [[x, y], ...] runs broken at jumps and view changes.
  function strokes(ch, view) {
    var out = [], cur = null, prevView = null;
    CH[ch].forEach(function (a) {
      if (a[1] !== view) { cur = null; prevView = a[1]; return; }
      if (!cur || a[4] === "jump" || prevView !== view) { cur = []; out.push(cur); }
      cur.push([a[2], a[3]]);
      prevView = a[1];
    });
    return out.filter(function (s) { return s.length > 1; });
  }

  var NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs, kids) {
    var n = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    (kids || []).forEach(function (c) { n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function outline() {
    var left = HALF.map(function (p) { return p.join(","); });
    var right = HALF.slice().reverse().map(function (p) { return (200 - p[0]) + "," + p[1]; });
    return left.concat(right).join(" ");
  }

  // SVG with a front and a back figure. opts: {acu: [ids], shiatsu: [ids], label: function(id)}.
  function figure(opts) {
    var acu = opts.acu || [], press = opts.shiatsu || [];
    var ids = acu.concat(press.filter(function (id) { return acu.indexOf(id) === -1; }));
    var chans = [];
    ids.forEach(function (id) { var p = parse(id); if (p && chans.indexOf(p.ch) === -1) chans.push(p.ch); });
    var svg = s("svg", { viewBox: "0 0 430 450", class: "bodymap", role: "img",
                         "aria-label": "תרשים סכמטי של הנקודות והמרידיאנים: " + ids.join(", ") });
    var defs = s("defs");
    chans.forEach(function (ch) {
      defs.appendChild(s("marker", { id: "arr-" + ch + "-" + uid, viewBox: "0 0 10 10", refX: "6", refY: "5", markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse" },
        [s("path", { d: "M0,0 L10,5 L0,10 z", fill: COLOR[ch] })]));
    });
    svg.appendChild(defs);
    [["F", 220, "קדמי"], ["B", 0, "אחורי"]].forEach(function (v) {
      var g = s("g", { transform: "translate(" + (v[1] + 5) + ",22)" });
      g.appendChild(s("text", { x: "100", y: "-8", "text-anchor": "middle", class: "bm-title" }, [v[2]]));
      g.appendChild(s("circle", { cx: "100", cy: "38", r: "20", class: "bm-body" }));
      g.appendChild(s("polygon", { points: outline(), class: "bm-body" }));
      if (v[0] === "F") {
        g.appendChild(s("ellipse", { cx: "92", cy: "36", rx: "3", ry: "1.5", class: "bm-line" }));
        g.appendChild(s("ellipse", { cx: "108", cy: "36", rx: "3", ry: "1.5", class: "bm-line" }));
        g.appendChild(s("path", { d: "M95,50 Q100,53 105,50", class: "bm-line" }));
        g.appendChild(s("circle", { cx: "100", cy: "165", r: "1.6", class: "bm-line" }));
      } else {
        g.appendChild(s("path", { d: "M100,72 L100,210", class: "bm-line" }));
      }
      chans.forEach(function (ch) {
        strokes(ch, v[0]).forEach(function (st) {
          g.appendChild(s("polyline", { points: st.map(function (p) { return p.join(","); }).join(" "), fill: "none", stroke: COLOR[ch],
                                        "stroke-width": "1.6", "stroke-opacity": "0.75", "marker-end": "url(#arr-" + ch + "-" + uid + ")" }));
        });
      });
      ids.forEach(function (id) {
        var p = place(id);
        if (!p || p.view !== v[0]) return;
        var ch = parse(id).ch, isAcu = acu.indexOf(id) !== -1, isPress = press.indexOf(id) !== -1;
        var dot = s("g", {}, [s("title", {}, [(opts.label ? opts.label(id) : id) + (isAcu && isPress ? " · דיקור ושיאצו" : isAcu ? " · דיקור" : " · שיאצו")])]);
        if (isPress) dot.appendChild(s("circle", { cx: p.x, cy: p.y, r: "4.6", fill: "none", stroke: COLOR[ch], "stroke-width": "1.4", "stroke-dasharray": isAcu ? "" : "2 1.4" }));
        if (isAcu) dot.appendChild(s("circle", { cx: p.x, cy: p.y, r: "2.8", fill: COLOR[ch] }));
        dot.appendChild(s("text", { x: p.x - 6, y: p.y + 3, "text-anchor": "end", class: "bm-label", fill: COLOR[ch] }, [id]));
        g.appendChild(dot);
      });
      svg.appendChild(g);
    });
    uid++;
    return svg;
  }
  var uid = 0;

  // Legend rows: [{ch, he, color}] for the channels a list of points uses.
  function channels(ids) {
    var out = [];
    ids.forEach(function (id) {
      var p = parse(id);
      if (p && !out.some(function (x) { return x.ch === p.ch; })) out.push({ ch: p.ch, he: NAME_HE[p.ch], color: COLOR[p.ch] });
    });
    return out;
  }

  root.TCMBodyMap = { figure: figure, place: place, channels: channels, CH: CH };
})(typeof window !== "undefined" ? window : this);
