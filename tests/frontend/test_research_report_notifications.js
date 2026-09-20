'use strict';

const assert = require('node:assert/strict');
const {
  normalizeArtifact,
  safeArtifactUrl,
  artifactActionUrl,
  normalizeNotification,
  mergeNotifications,
  notificationKindLabel,
  notificationPayloadText,
} = require('../../frontend/research-tasks.js');

assert.equal(safeArtifactUrl('/api/research-sessions/s1/artifacts/a1/download'), '/api/research-sessions/s1/artifacts/a1/download');
assert.equal(safeArtifactUrl('https://evil.invalid/download'), '');
assert.equal(safeArtifactUrl('/api/research-sessions/s1/artifacts/a1/download?next=https://evil.invalid'), '');
assert.equal(artifactActionUrl('html', '/api/research-sessions/s1/artifacts/a1/download'), '/api/research-sessions/s1/artifacts/a1/download?mode=inline');
assert.equal(artifactActionUrl('markdown', '/api/research-sessions/s1/artifacts/a1/download'), '/api/research-sessions/s1/artifacts/a1/download');
assert.equal(artifactActionUrl('citation_manifest', '/api/research-sessions/s1/artifacts/a1/download'), '/api/research-sessions/s1/artifacts/a1/download');
assert.equal(artifactActionUrl('html', '/api/research-sessions/s1/artifacts/a1/download?mode=inline'), '', 'pre-existing query strings are rejected');
assert.equal(artifactActionUrl('html', 'https://evil.invalid/download'), '', 'external HTML URLs are rejected');
assert.equal(normalizeArtifact({ artifact_id: 'a1', artifact_type: 'markdown', download_url: '/api/research-sessions/s1/artifacts/a1/download' }).artifact_type, 'markdown');
assert.equal(normalizeArtifact({ artifact_id: 'a2', artifact_type: 'intermediate' }), null, 'intermediate artifacts are not user actions');
assert.equal(normalizeArtifact({ artifact_id: 'a3', artifact_type: 'markdown', download_url: 'javascript:alert(1)' }), null, 'unsafe artifact URLs are rejected');

assert.equal(notificationKindLabel('completed'), '研究已完成');
assert.equal(notificationKindLabel('retry'), '', 'retry is represented as failed payload metadata, not a notification kind');
assert.equal(notificationKindLabel('heartbeat'), '', 'heartbeat never enters the list');
assert.equal(normalizeNotification({ notification_id: 'n1', event_seq: 3, notification_kind: 'failed', status: 'unread' }).event_seq, 3);
assert.equal(normalizeNotification({ notification_id: 'n2', event_seq: 0, notification_kind: 'failed' }), null);
assert.equal(normalizeNotification({ notification_id: 'n3', event_seq: 4, notification_kind: 'heartbeat' }), null);
assert.equal(normalizeNotification({ notification_id: 'n4', event_seq: 4, notification_kind: 'retry', status: 'unread' }), null, 'unknown kinds are rejected');
assert.equal(normalizeNotification({ notification_id: 'n5', event_seq: 5, notification_kind: 'failed', status: 'pending' }), null, 'unknown statuses are rejected');
assert.match(notificationPayloadText({ notification_kind: 'failed', payload: { retryable: true } }), /可重试/);
assert.match(notificationPayloadText({ notification_kind: 'failed', payload: { retry_attempt: 2 } }), /第 2 次/);

const merged = mergeNotifications([
  { notification_id: 'n2', event_seq: 2, notification_kind: 'partial', status: 'unread' },
  { notification_id: 'n1', event_seq: 1, notification_kind: 'completed', status: 'unread' },
  { notification_id: 'n2', event_seq: 2, notification_kind: 'partial', status: 'unread' },
  { notification_id: 'bad', event_seq: 0, notification_kind: 'failed' },
]);
assert.deepEqual(merged.map((item) => item.notification_id), ['n1', 'n2']);
assert.deepEqual(merged.map((item) => item.event_seq), [1, 2]);
console.log('Task08 frontend contract: PASS (artifact allowlist, safe URLs, notification states, cursor de-duplication)');
