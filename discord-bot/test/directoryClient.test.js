import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createDirectoryClient,
  DirectoryUnavailable,
  AlreadyLinked,
  PersonExists,
} from '../src/directoryClient.js';

function fakeFetch(responses) {
  const calls = [];
  let i = 0;
  const fetchImpl = async (url, opts) => {
    calls.push({ url, opts });
    const r = responses[i++];
    return {
      status: r.status,
      ok: r.ok ?? (r.status >= 200 && r.status < 300),
      json: async () => r.body,
    };
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

const BASE = 'http://d';
const KEY = 'k';

test('getPersonByEmail returns person on 200', async () => {
  const fetchImpl = fakeFetch([{ status: 200, body: { id: '1', display_name: 'Alex' } }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  const person = await client.getPersonByEmail('alex@utmist.ca');
  assert.equal(person.display_name, 'Alex');
  assert.match(fetchImpl.calls[0].url, /\/people\/by-email\/alex%40utmist\.ca$/);
  assert.equal(fetchImpl.calls[0].opts.headers['X-API-Key'], 'k');
});

test('getPersonByEmail returns null on 404', async () => {
  const fetchImpl = fakeFetch([{ status: 404, body: {} }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  assert.equal(await client.getPersonByEmail('x@utmist.ca'), null);
});

test('getPersonByEmail throws DirectoryUnavailable on 500', async () => {
  const fetchImpl = fakeFetch([{ status: 500, body: {} }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  await assert.rejects(() => client.getPersonByEmail('x@utmist.ca'), DirectoryUnavailable);
});

test('getPersonByDiscordId returns null on 404', async () => {
  const fetchImpl = fakeFetch([{ status: 404, body: {} }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  assert.equal(await client.getPersonByDiscordId('123'), null);
});

test('linkDiscord posts provider=discord and returns body on 201', async () => {
  const fetchImpl = fakeFetch([{ status: 201, body: { provider: 'discord', external_id: '123' } }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  const res = await client.linkDiscord('p1', { externalId: '123', handle: 'alex' });
  assert.equal(res.external_id, '123');
  const { url, opts } = fetchImpl.calls[0];
  assert.match(url, /\/people\/p1\/identifiers$/);
  assert.equal(opts.method, 'POST');
  const sent = JSON.parse(opts.body);
  assert.equal(sent.provider, 'discord');
  assert.equal(sent.external_id, '123');
  assert.equal(sent.handle, 'alex');
});

test('linkDiscord throws AlreadyLinked with detail on 409', async () => {
  const fetchImpl = fakeFetch([{ status: 409, body: { detail: 'person already linked' } }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  await assert.rejects(
    () => client.linkDiscord('p1', { externalId: '123', handle: 'alex' }),
    (e) => e instanceof AlreadyLinked && e.detail === 'person already linked',
  );
});

test('getPersonByEmail throws DirectoryUnavailable on malformed 200 body', async () => {
  const fetchImpl = async () => ({
    status: 200,
    ok: true,
    json: async () => { throw new SyntaxError('bad'); },
  });
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  await assert.rejects(() => client.getPersonByEmail('x@utmist.ca'), DirectoryUnavailable);
});

test('network error becomes DirectoryUnavailable', async () => {
  const fetchImpl = async () => { throw new Error('econnrefused'); };
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  await assert.rejects(() => client.getPersonByEmail('x@utmist.ca'), DirectoryUnavailable);
});

test('createPerson posts fields and returns body on 201', async () => {
  const fetchImpl = fakeFetch([{ status: 201, body: { id: 'p1', display_name: 'A', access_level: 'admin' } }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  const person = await client.createPerson({ displayName: 'A', primaryEmail: 'a@utmist.ca', accessLevel: 'admin' });
  assert.equal(person.id, 'p1');
  const { url, opts } = fetchImpl.calls[0];
  assert.match(url, /\/people$/);
  assert.equal(opts.method, 'POST');
  const sent = JSON.parse(opts.body);
  assert.equal(sent.display_name, 'A');
  assert.equal(sent.primary_email, 'a@utmist.ca');
  assert.equal(sent.access_level, 'admin');
});

test('createPerson throws PersonExists on 409', async () => {
  const fetchImpl = fakeFetch([{ status: 409, body: { detail: 'primary_email already exists' } }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  await assert.rejects(
    () => client.createPerson({ displayName: 'A', primaryEmail: 'a@utmist.ca', accessLevel: 'member' }),
    (e) => e instanceof PersonExists && e.detail === 'primary_email already exists',
  );
});

test('createPerson throws DirectoryUnavailable on 500', async () => {
  const fetchImpl = fakeFetch([{ status: 500, body: {} }]);
  const client = createDirectoryClient({ baseUrl: BASE, apiKey: KEY, fetchImpl });
  await assert.rejects(
    () => client.createPerson({ displayName: 'A', primaryEmail: 'a@utmist.ca', accessLevel: 'member' }),
    DirectoryUnavailable,
  );
});
