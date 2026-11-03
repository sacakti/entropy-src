// Finding artifacts for a release; run by tests/tools/test_release_artifact_search.py.
import assert from 'node:assert/strict'

import {
    ARTIFACTS_PER_PAGE,
    artifactOrigin,
    artifactPage,
    artifactTime,
    newestFirst,
    searchArtifacts,
} from '../../frontend/src/features/tools/releases/artifactSearch.ts'

const uploaded = { id: 1, name: 'payments-2.8.zip', source: 'upload', size_bytes: 1, created_at: '2026-01-01T00:00:00', created_by: 'pravin', tags: ['SIT'] }
const generated = { id: 2, name: 'report.html', source: 'server_path', origin: 'quay.generic', run_id: 'abc', size_bytes: 1, created_at: '2026-03-01T00:00:00', created_by: 'admin' }
const registered = { id: 3, name: 'base.tar', source: 'server_path', size_bytes: 1, created_at: '2026-02-01T00:00:00', created_by: 'admin' }
const all = [uploaded, generated, registered]
const ids = (items: { id: number }[]) => items.map((item) => item.id)

assert.equal(artifactOrigin(uploaded), 'Uploaded')
assert.equal(artifactOrigin(generated), 'Generated')
assert.equal(artifactOrigin(registered), 'Server path')

assert.deepEqual(ids(searchArtifacts(all, '')), [1, 2, 3])
assert.deepEqual(ids(searchArtifacts(all, '   ')), [1, 2, 3])
assert.deepEqual(ids(searchArtifacts(all, 'PAYMENTS')), [1])
assert.deepEqual(ids(searchArtifacts(all, 'quay')), [2])
assert.deepEqual(ids(searchArtifacts(all, 'sit')), [1])
assert.deepEqual(ids(searchArtifacts(all, 'admin')), [2, 3])
assert.deepEqual(ids(searchArtifacts(all, 'generated')), [2])
assert.deepEqual(ids(searchArtifacts(all, 'admin base')), [3])
assert.deepEqual(ids(searchArtifacts(all, 'nothing')), [])

assert.deepEqual(ids(newestFirst(all)), [2, 3, 1])
assert.deepEqual(ids(all), [1, 2, 3], 'the original order stays')
assert.deepEqual(ids(newestFirst([{ ...uploaded, created_at: null }, generated])), [2, 1])
assert.deepEqual(ids(newestFirst([{ ...uploaded, id: 4 }, { ...uploaded, id: 9 }])), [9, 4])

assert.equal(ARTIFACTS_PER_PAGE, 5)
const twelve = Array.from({ length: 12 }, (_, index) => index)
assert.deepEqual(artifactPage(twelve, 1), { items: [0, 1, 2, 3, 4], page: 1, pages: 3 })
assert.deepEqual(artifactPage(twelve, 3), { items: [10, 11], page: 3, pages: 3 })
assert.equal(artifactPage(twelve, 99).page, 3, 'a page past the end comes back to the last')
assert.equal(artifactPage(twelve, 0).page, 1)
assert.deepEqual(artifactPage([], 1), { items: [], page: 1, pages: 1 })

// Stored without a zone, it is UTC whatever the browser's zone is.
assert.equal(new Date(artifactTime('2026-11-03 18:05:59')).toISOString(), '2026-11-03T18:05:59.000Z')
assert.equal(artifactTime('2026-11-03T18:05:59Z'), '2026-11-03T18:05:59Z')
assert.equal(artifactTime('2026-11-03T18:05:59+03:00'), '2026-11-03T18:05:59+03:00')
