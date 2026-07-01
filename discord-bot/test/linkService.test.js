import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createLinkService } from '../src/linkService.js';
import { AlreadyLinked, DirectoryUnavailable } from '../src/directoryClient.js';

const ARGS = { email: 'alex@utmist.ca', discordUserId: '123', discordHandle: 'alex' };

test('LINKED when email resolves and link succeeds', async () => {
  const person = { id: 'p1', display_name: 'Alex' };
  const linked = [];
  const svc = createLinkService({
    directory: {
      getPersonByEmail: async () => person,
      linkDiscord: async (pid, payload) => { linked.push({ pid, payload }); return {}; },
    },
  });
  const res = await svc.linkByEmail(ARGS);
  assert.equal(res.outcome, 'LINKED');
  assert.equal(res.person, person);
  assert.deepEqual(linked[0], { pid: 'p1', payload: { externalId: '123', handle: 'alex' } });
});

test('NOT_A_MEMBER when email does not resolve, and no link attempted', async () => {
  let linkCalled = false;
  const svc = createLinkService({
    directory: {
      getPersonByEmail: async () => null,
      linkDiscord: async () => { linkCalled = true; return {}; },
    },
  });
  const res = await svc.linkByEmail(ARGS);
  assert.equal(res.outcome, 'NOT_A_MEMBER');
  assert.equal(linkCalled, false);
});

test('ALREADY_LINKED surfaces directory detail', async () => {
  const svc = createLinkService({
    directory: {
      getPersonByEmail: async () => ({ id: 'p1', display_name: 'Alex' }),
      linkDiscord: async () => { throw new AlreadyLinked('this discord already belongs to another person'); },
    },
  });
  const res = await svc.linkByEmail(ARGS);
  assert.equal(res.outcome, 'ALREADY_LINKED');
  assert.equal(res.detail, 'this discord already belongs to another person');
});

test('DIRECTORY_DOWN when directory is unavailable', async () => {
  const svc = createLinkService({
    directory: {
      getPersonByEmail: async () => { throw new DirectoryUnavailable('nope'); },
      linkDiscord: async () => ({}),
    },
  });
  const res = await svc.linkByEmail(ARGS);
  assert.equal(res.outcome, 'DIRECTORY_DOWN');
});
