'use strict';

// Pure-function contracts for the research task search entry (D1-B / D2).
// Run with: node tests/frontend/test_research_task_search.js
const assert = require('node:assert/strict');
const api = require('../../frontend/research-tasks.js');

const TARGET_ID = '2eb327f2cefb5fc7b5ac60e0454294f6';

// --- export contract: pure functions must be reachable from window.ResearchTasks / CommonJS api ---
assert.equal(typeof api.filterSessionsByQuery, 'function', 'filterSessionsByQuery must be exported for Node tests');
assert.equal(typeof api.normalizeTaskQuery, 'function', 'normalizeTaskQuery must be exported for Node tests');
assert.equal(typeof api.applyTaskIdLookupResult, 'function', 'applyTaskIdLookupResult must be exported for Node tests');

const sample = [
  { research_task_id: 'a'.repeat(32), research_session_id: 's-1', goal_excerpt: '联邦学习隐私', status: 'completed', created_at: '2026-01-01' },
  { research_task_id: 'b'.repeat(32), research_session_id: 's-2', goal_excerpt: '检索增强生成', status: 'running', created_at: '2026-02-01' },
  { research_task_id: null, research_session_id: 's-3', goal_excerpt: '受控基准摘要', status: 'partial', created_at: '2026-03-01' },
];

// --- B1 empty / whitespace-only query restores the full list, no direct lookup ---
assert.equal(api.filterSessionsByQuery('', sample).length, 3);
assert.equal(api.filterSessionsByQuery('   ', sample).length, 3);
assert.deepEqual(api.filterSessionsByQuery('', sample), sample);
assert.equal(api.normalizeTaskQuery('   ').value, '');
assert.equal(api.normalizeTaskQuery('   ').isTaskId, false);

// --- B2 case-insensitive + Chinese matching across the five-field haystack ---
assert.equal(api.filterSessionsByQuery('联邦学习', sample).length, 1);
assert.equal(api.filterSessionsByQuery('A'.repeat(32), sample).length, 1, 'uppercase ID matches via toLowerCase');
assert.equal(api.filterSessionsByQuery('COMPLETED', sample).length, 1, 'status field is case-insensitive');
assert.equal(api.filterSessionsByQuery('2026-02', sample).length, 1, 'time field is searchable');

// --- B3 over-long input is truncated to 128, never reaches a URL, never throws ---
const long = 'a'.repeat(1000);
assert.equal(api.normalizeTaskQuery(long).value.length, 128);
assert.equal(api.normalizeTaskQuery(long).truncated, true);
assert.equal(api.normalizeTaskQuery(long).isTaskId, false, 'over-long input must not trigger direct lookup');
assert.doesNotThrow(() => api.filterSessionsByQuery(long, sample));
assert.equal(api.filterSessionsByQuery(long, sample).length, 0);

// --- B4 special characters are literal substrings only (no HTML / regex parsing) ---
const xss = '<img src=x onerror=alert(1)>';
assert.equal(api.filterSessionsByQuery(xss, sample).length, 0);
assert.equal(api.filterSessionsByQuery("'\"&", sample).length, 0);
assert.doesNotThrow(() => api.filterSessionsByQuery(xss, sample));
const special = [{ research_task_id: 'c'.repeat(32), research_session_id: 's-4', goal_excerpt: "O'Reilly & <b>中文</b>", status: 'running', created_at: '2026-04-01' }];
assert.equal(api.filterSessionsByQuery("O'Reilly", special).length, 1);
assert.equal(api.filterSessionsByQuery('<b>', special).length, 1);

// --- B6 100 loaded rows without the target ID cannot be found by filtering -> direct lookup branch ---
const hundred = Array.from({ length: 100 }, (_, index) => ({
  research_task_id: String(index).padStart(32, '0'),
  research_session_id: `s-${index}`,
  goal_excerpt: `任务 ${index}`,
  status: 'completed',
  created_at: `2026-01-${String((index % 28) + 1).padStart(2, '0')}`,
}));
assert.equal(api.filterSessionsByQuery(TARGET_ID, hundred).length, 0, 'front-end filter over 100 rows misses the historical ID');
assert.equal(api.normalizeTaskQuery(TARGET_ID).isTaskId, true, 'full 32-char hex must take the D1-B direct lookup branch');
assert.equal(api.normalizeTaskQuery(TARGET_ID.toUpperCase()).isTaskId, true, 'uppercase hex normalizes then matches');
assert.equal(api.normalizeTaskQuery(TARGET_ID.slice(0, 31)).isTaskId, false, '31-char prefix is not a full ID');
assert.equal(api.normalizeTaskQuery(TARGET_ID + 'z').isTaskId, false, 'non-hex characters never enter the direct lookup URL');

// --- B7 null research_task_id degrades without throwing ---
assert.doesNotThrow(() => api.filterSessionsByQuery('s-3', sample));
assert.equal(api.filterSessionsByQuery('s-3', sample).length, 1, 'null task_id row still matches by session_id');
assert.equal(api.filterSessionsByQuery('联邦', [{ research_task_id: null }]).length, 0);
assert.doesNotThrow(() => api.filterSessionsByQuery('x', [{ research_task_id: null, goal_excerpt: undefined, status: null }]));

// --- B9 N/M count: matched is the filtered length, total is the loaded length ---
const threeMatch = Array.from({ length: 100 }, (_, index) => ({
  research_task_id: String(index).padStart(32, '0'),
  research_session_id: `s-${index}`,
  goal_excerpt: index < 3 ? '命中关键字' : '无关目标',
  status: 'completed',
  created_at: '2026-01-01',
}));
assert.equal(threeMatch.length, 100, 'M=100');
assert.equal(api.filterSessionsByQuery('命中', threeMatch).length, 3, 'N=3');
assert.equal(api.filterSessionsByQuery('不存在', threeMatch).length, 0, 'N=0 empty state');
assert.equal(api.filterSessionsByQuery('completed', threeMatch).length, 100, 'N=M on a full match');

// --- B10 out-of-order direct lookup resolves: only the newest requestSeq applies ---
const lookup = { status: 'loading', taskId: TARGET_ID, result: null, requestSeq: 2, message: '' };
const stale = api.applyTaskIdLookupResult(lookup, 1, { status: 'miss', message: '未找到该任务' });
assert.equal(stale, lookup, 'stale seq=1 resolve must be dropped (same object returned)');
assert.equal(lookup.status, 'loading', 'pure function must not mutate the input lookup');
const fresh = api.applyTaskIdLookupResult(lookup, 2, { status: 'hit', result: { research_session_id: 's-1' } });
assert.equal(fresh.status, 'hit', 'latest seq=2 resolve applies');
assert.equal(fresh.result.research_session_id, 's-1');
assert.equal(fresh.requestSeq, 2);
assert.equal(api.applyTaskIdLookupResult(lookup, 3, { status: 'error' }), lookup, 'a future seq must not apply either');
assert.equal(api.applyTaskIdLookupResult(null, 0, { status: 'idle' }).status, 'idle', 'null lookup degrades safely');

console.log('research task search contract: PASS (B1/B2/B3/B4/B6/B7/B9/B10 pure functions)');
