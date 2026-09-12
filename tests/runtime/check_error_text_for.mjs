// Runtime check for Spec 026 P0-1: errorTextFor must NOT emit "连接失败" for
// internal (non-network) errors, and MUST emit it only for the real network
// fallback. This executes the ACTUAL functions extracted from frontend/app.js
// in Node, so it is real runtime behaviour (not a source-substring assertion).
//
// Usage: node check_error_text_for.mjs [path/to/app.js]
// Exit code 0 = all checks pass, 1 = at least one failure.

import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const appPath = process.argv[2] || resolve(here, '../../frontend/app.js');
let APP;
try {
  APP = readFileSync(appPath, 'utf8');
} catch (e) {
  console.error('FAIL: cannot read app.js at', appPath, e.message);
  process.exit(1);
}

function extractFn(name) {
  const start = APP.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`function ${name} not found in ${appPath}`);
  let pos = APP.indexOf('(', start);
  let depth = 0;
  while (pos < APP.length) {
    const c = APP[pos];
    if (c === '(') depth++;
    else if (c === ')') { depth--; if (depth === 0) break; }
    pos++;
  }
  const opening = APP.indexOf('{', pos);
  depth = 0;
  for (let i = opening; i < APP.length; i++) {
    const c = APP[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return APP.slice(start, i + 1); }
  }
  throw new Error(`unbalanced braces in ${name}`);
}

function extractConst(name) {
  const start = APP.indexOf(`const ${name} = `);
  if (start < 0) throw new Error(`const ${name} not found`);
  const eq = APP.indexOf('=', start);
  let depth = 0;
  let inStr = null;
  let i = eq + 1;
  for (; i < APP.length; i++) {
    const c = APP[i];
    if (inStr) { if (c === inStr && APP[i - 1] !== '\\') inStr = null; continue; }
    if (c === '"' || c === "'" || c === '`') { inStr = c; continue; }
    if (c === '[' || c === '{' || c === '(') depth++;
    else if (c === ']' || c === '}' || c === ')') { depth--; if (depth === 0) { /* matched */ } }
    else if (c === ';' && depth === 0) break;
  }
  return APP.slice(start, i + 1);
}

let failures = 0;
function check(cond, msg) {
  if (cond) console.log('PASS:', msg);
  else { console.error('FAIL:', msg); failures++; }
}

try {
  const src = [
    extractConst('REASONING_EFFORTS'),
    extractConst('reasoningOptionsState'),
    extractConst('REASONING_EFFORT_LABELS'),
    extractFn('normalizeReasoningEffort'),
    extractFn('supportedReasoningEfforts'),
    extractFn('highestSupportedReasoningEffort'),
    extractFn('reasoningEffortLabel'),
    extractFn('errorTextFor'),
  ].join('\n');
  const mod = new Function(`${src}\nreturn { errorTextFor };`);
  const api = mod();

  // --- P0-1: internal errors must be neutral, no "连接失败" ---
  const aborted = api.errorTextFor('ABORTED', '本轮已中止');
  check(typeof aborted === 'object' && typeof aborted.text === 'string', 'ABORTED returns {text, actions}');
  check(!aborted.text.includes('连接失败'), "ABORTED text has no '连接失败'");
  check(aborted.text === '本轮已中止', "ABORTED neutral text is exactly '本轮已中止'");

  const stream = api.errorTextFor('STREAM_INTERRUPTED', '事件流中断');
  check(!stream.text.includes('连接失败'), "STREAM_INTERRUPTED text has no '连接失败'");
  check(stream.text === '事件流中断，请重新发送', "STREAM_INTERRUPTED neutral text");

  // --- backend codes must also never say 连接失败 ---
  const unsup = api.errorTextFor('REASONING_EFFORT_UNSUPPORTED', 'x', 'xhigh');
  check(!unsup.text.includes('连接失败'), "REASONING_EFFORT_UNSUPPORTED text has no '连接失败'");
  const unavail = api.errorTextFor('MODEL_UNAVAILABLE', 'x');
  check(!unavail.text.includes('连接失败'), "MODEL_UNAVAILABLE text has no '连接失败'");

  // --- ONLY the real network fallback may contain 连接失败 ---
  const net = api.errorTextFor(undefined, 'fetch failed');
  check(net.text.includes('连接失败'), "network fallback (no code) text contains '连接失败'");
  check(net.text === '连接失败：fetch failed', "network fallback wording is '连接失败：<reason>'");
  const netNull = api.errorTextFor(null, 'no response');
  check(netNull.text.includes('连接失败'), "network fallback (null code) text contains '连接失败'");

  // --- structural: exactly one 连接失败 literal inside errorTextFor ---
  const etfSrc = extractFn('errorTextFor');
  const count = (etfSrc.match(/连接失败/g) || []).length;
  check(count === 1, `errorTextFor contains '连接失败' exactly once (network fallback only), got ${count}`);
} catch (e) {
  console.error('FAIL: runtime extraction/execution error:', e.message);
  failures++;
}

if (failures) { console.error(`\n${failures} check(s) FAILED`); process.exit(1); }
console.log('\nAll errorTextFor runtime checks passed.');
