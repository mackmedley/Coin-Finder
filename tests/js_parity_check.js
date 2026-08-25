/* Node half of the Python<->JavaScript parity test.
 *
 * "Coin Finder.html" reimplements scoring.py and sell.py in JavaScript so the
 * browser version needs no install. Two copies of the same rules can drift, so
 * this loads the real scoring code out of the HTML file, runs it over payloads
 * the Python engine already scored, and diffs the results.
 *
 * Usage: node js_parity_check.js <cases.json> <path-to-html>
 */

"use strict";

const fs = require("fs");

const [casesPath, htmlPath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, "utf8");
const script = html.split("<script>")[1].split("</script>")[0];

// Cut at the opening of the comment block introducing the rendering section,
// not at the marker text itself, or the slice ends inside an open /* comment.
const marker = " * Rendering";
const logic = script.slice(0, script.lastIndexOf("/*", script.indexOf(marker)));
if (logic.length < 1000) {
  console.error("Could not slice the logic section out of the HTML.");
  process.exit(2);
}

// The logic section touches these two browser globals and nothing else.
const localStorage = { getItem: () => null, setItem: () => {} };
const fetchStub = () => { throw new Error("network is not used in this check"); };

const factory = new Function(
  "localStorage", "fetch",
  logic + "\n; return { toCandidate, applyFilters, scoreCandidate };"
);
const api = factory(localStorage, fetchStub);

const data = JSON.parse(fs.readFileSync(casesPath, "utf8"));

// Age is derived from the clock, so the two runs differ by however long the
// Python half took. Compare numbers within a small absolute tolerance.
const TOL = 0.05;
const near = (a, b) => Math.abs(a - b) <= TOL;

let failures = 0;
const report = (msg) => { console.log(msg); failures++; };

for (const [name, pair] of Object.entries(data.pairs)) {
  const expected = data.python[name];
  const candidate = api.toCandidate(pair);
  const reasons = api.applyFilters(candidate);

  if (expected.rejected !== reasons.length > 0) {
    report(`REJECT MISMATCH  ${name}: python rejected=${expected.rejected}, js rejected=${reasons.length > 0}`);
    continue;
  }

  if (expected.rejected) {
    if (JSON.stringify(expected.reasons) !== JSON.stringify(reasons)) {
      report(`REASON TEXT  ${name}\n   python: ${JSON.stringify(expected.reasons)}\n   js:     ${JSON.stringify(reasons)}`);
    }
    continue;
  }

  const scored = api.scoreCandidate(candidate);

  if (!near(expected.score, scored.score)) {
    report(`SCORE  ${name}: python=${expected.score} js=${scored.score}`);
  }
  for (const [key, value] of Object.entries(expected.breakdown)) {
    if (!near(value, scored.score_breakdown[key])) {
      report(`COMPONENT  ${name}.${key}: python=${value} js=${scored.score_breakdown[key]}`);
    }
  }
  if (JSON.stringify(expected.flags) !== JSON.stringify(scored.flags)) {
    report(`FLAGS  ${name}\n   python: ${JSON.stringify(expected.flags)}\n   js:     ${JSON.stringify(scored.flags)}`);
  }
}

console.log(`${Object.keys(data.pairs).length} cases compared, ${failures} mismatch(es).`);
process.exit(failures ? 1 : 0);
