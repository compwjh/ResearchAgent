// Runtime check for Spec 026 P1-1: during the capability-probing (loading)
// window the sent reasoning_effort must NOT be the raw select value (which is
// unconfirmed and can trigger a backend 409 for an unsupported tier). It must
// fall back to a universally-supported safe tier. This executes the ACTUAL
// pickSendReasoningEffort extracted from frontend/app.js in Node.
//
// Usage: node check_send_effort.mjs [path/to/app.js]
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
    extractFn('normalizeReasoningEffort'),
    extractFn('pickSendReasoningEffort'),
  ].join('\n');
  const mod = new Function(`${src}\nreturn { pickSendReasoningEffort };`);
  const api = mod();

  // loading window: never send the raw select value, even if it is xhigh.
  check(api.pickSendReasoningEffort('loading', 'xhigh', 'xhigh') === 'off',
    "loading + select='xhigh' -> 'off' (cannot 409 on unconfirmed tier)");
  check(api.pickSendReasoningEffort('loading', 'high', 'high') === 'off',
    "loading + select='high' -> 'off' (selection not confirmed yet)");
  check(api.pickSendReasoningEffort('loading', '', 'off') === 'off',
    "loading with empty select -> 'off'");
  // loading must ignore a possibly-stale lastEffort from another model.
  check(api.pickSendReasoningEffort('loading', 'xhigh', 'off') === 'off',
    "loading ignores stale lastEffort on model switch");

  // known/stale: use the confirmed select value; fall back to lastEffort only if empty.
  check(api.pickSendReasoningEffort('known', 'xhigh', 'xhigh') === 'xhigh',
    "known uses confirmed select value 'xhigh'");
  check(api.pickSendReasoningEffort('known', 'medium', 'high') === 'medium',
    "known uses confirmed select value 'medium'");
  check(api.pickSendReasoningEffort('known', '', 'high') === 'high',
    "known falls back to lastEffort when select empty");
  check(api.pickSendReasoningEffort('stale', 'low', 'low') === 'low',
    "stale uses old supported select value");
  check(api.pickSendReasoningEffort('unknown', 'off', 'off') === 'off',
    "unknown falls back to 'off'");
  // invalid input is normalized away.
  check(api.pickSendReasoningEffort('known', 'bogus', 'off') === 'off',
    "known with invalid select normalized to 'off'");
} catch (e) {
  console.error('FAIL: runtime extraction/execution error:', e.message);
  failures++;
}

if (failures) { console.error(`\n${failures} check(s) FAILED`); process.exit(1); }
console.log('\nAll pickSendReasoningEffort runtime checks passed.');
