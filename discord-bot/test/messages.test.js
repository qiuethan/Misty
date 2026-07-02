import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderLinkResult, renderSeedResult, buildWhoamiEmbed } from '../src/messages.js';

test('renderLinkResult covers every outcome', () => {
  assert.match(renderLinkResult({ outcome: 'LINKED', person: { display_name: 'Alex' } }), /Alex/);
  assert.match(renderLinkResult({ outcome: 'NOT_A_MEMBER' }), /exec/i);
  assert.match(renderLinkResult({ outcome: 'ALREADY_LINKED', detail: 'x' }), /already|couldn't|could not/i);
  assert.match(renderLinkResult({ outcome: 'DIRECTORY_DOWN' }), /unavailable|try again/i);
});

test('buildWhoamiEmbed renders the four person fields', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'Alex', primary_email: 'alex@utmist.ca', access_level: 'admin', active: true },
    [],
  );
  assert.equal(embed.title, 'Alex');
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Email'], 'alex@utmist.ca');
  assert.equal(byName['Access level'], 'admin');
  assert.equal(byName['Status'], 'Active');
  assert.equal(byName['Identities'], '_(none)_');
});

test('buildWhoamiEmbed renders Inactive when person.active is false', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'A', primary_email: 'a@x', access_level: 'member', active: false },
    [],
  );
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Status'], 'Inactive');
});

test('buildWhoamiEmbed sorts identifiers alphabetically and formats handle vs no-handle', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'A', primary_email: 'a@x', access_level: 'member', active: true },
    [
      { provider: 'github', external_id: '9876', handle: 'eeetan' },
      { provider: 'discord', external_id: '123', handle: 'alex' },
      { provider: 'notion', external_id: 'notion-uuid', handle: null },
    ],
  );
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(
    byName['Identities'],
    'discord: alex (123)\ngithub: eeetan (9876)\nnotion: notion-uuid',
  );
});

test('buildWhoamiEmbed shows _(unavailable)_ when identifiers is null', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'A', primary_email: 'a@x', access_level: 'member', active: true },
    null,
  );
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Identities'], '_(unavailable)_');
});

test('renderSeedResult covers outcomes', () => {
  assert.match(
    renderSeedResult({ outcome: 'SEEDED', person: { display_name: 'A', primary_email: 'a@x', access_level: 'member' } }),
    /A/,
  );
  assert.match(renderSeedResult({ outcome: 'EXISTS', detail: 'x' }), /already/i);
  assert.match(renderSeedResult({ outcome: 'DIRECTORY_DOWN' }), /unavailable|try again/i);
});
