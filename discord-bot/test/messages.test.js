import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  authMessages,
  renderLinkResult,
  renderSeedResult,
  buildWhoamiEmbed,
  renderCreateTeamResult,
  renderListTeamsResult,
  renderRenameTeamResult,
  renderAddMemberResult,
  renderRemoveMemberResult,
  renderRosterResult,
  renderMyTeamsResult,
} from '../src/messages.js';

test('authMessages.unavailable returns ReplyPayload', () => {
  const p = authMessages.unavailable();
  assert.equal(typeof p.content, 'string');
  assert.equal(p.ephemeral, true);
  assert.equal(p.embeds, undefined);
});

test('authMessages.denied returns ReplyPayload', () => {
  const p = authMessages.denied('not_linked');
  assert.equal(typeof p.content, 'string');
  assert.equal(p.ephemeral, true);
  assert.match(p.content, /link/i);
});

test('authMessages.internalError returns ReplyPayload', () => {
  const p = authMessages.internalError();
  assert.equal(typeof p.content, 'string');
  assert.equal(p.ephemeral, true);
});

test('renderLinkResult covers every outcome', () => {
  assert.match(renderLinkResult({ outcome: 'LINKED', person: { display_name: 'Alex' } }).content, /Alex/);
  assert.match(renderLinkResult({ outcome: 'NOT_A_MEMBER' }).content, /exec/i);
  assert.match(renderLinkResult({ outcome: 'ALREADY_LINKED', detail: 'x' }).content, /already|couldn't|could not/i);
  assert.match(renderLinkResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderLinkResult returns ReplyPayload with content', () => {
  const p = renderLinkResult({ outcome: 'LINKED', person: { display_name: 'Alex' } });
  assert.ok(p.content.includes('Alex'));
  assert.equal(p.ephemeral, true);
});

test('buildWhoamiEmbed returns ReplyPayload with embeds', () => {
  const p = buildWhoamiEmbed(
    { display_name: 'A', primary_email: 'a@x', access_level: 'member', active: true },
    [],
  );
  assert.equal(p.content, undefined);
  assert.equal(p.embeds.length, 1);
  assert.equal(p.embeds[0].title, 'A');
  assert.equal(p.ephemeral, true);
});

test('buildWhoamiEmbed renders the four person fields', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'Alex', primary_email: 'alex@utmist.ca', access_level: 'admin', active: true },
    [],
  ).embeds[0];
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
  ).embeds[0];
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
  ).embeds[0];
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(
    byName['Identities'],
    'discord: <@123>\ngithub: eeetan (9876)\nnotion: notion-uuid',
  );
});

test('buildWhoamiEmbed renders discord identity as a mention (drops stored handle)', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'A', primary_email: 'a@x', access_level: 'member', active: true },
    [{ provider: 'discord', external_id: '987654321', handle: 'stale-handle' }],
  ).embeds[0];
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Identities'], 'discord: <@987654321>');
});

test('buildWhoamiEmbed shows _(unavailable)_ when identifiers is null', () => {
  const embed = buildWhoamiEmbed(
    { display_name: 'A', primary_email: 'a@x', access_level: 'member', active: true },
    null,
  ).embeds[0];
  const byName = Object.fromEntries(embed.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Identities'], '_(unavailable)_');
});

test('renderSeedResult covers outcomes', () => {
  assert.match(
    renderSeedResult({ outcome: 'SEEDED', person: { display_name: 'A', primary_email: 'a@x', access_level: 'member' } }).content,
    /A/,
  );
  assert.match(renderSeedResult({ outcome: 'EXISTS', detail: 'x' }).content, /already/i);
  assert.match(renderSeedResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderCreateTeamResult covers outcomes', () => {
  assert.match(
    renderCreateTeamResult({ outcome: 'CREATED', team: { slug: 'ml', label: 'ML' } }).content,
    /ML|ml/,
  );
  assert.match(renderCreateTeamResult({ outcome: 'SLUG_EXISTS', detail: 'x' }).content, /already/i);
  assert.match(renderCreateTeamResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderListTeamsResult covers outcomes', () => {
  assert.match(
    renderListTeamsResult({ outcome: 'LISTED', teams: [{ slug: 'ml', label: 'ML' }, { slug: 'ops', label: 'Ops' }] }).content,
    /ML.*Ops|ml.*ops/is,
  );
  assert.match(
    renderListTeamsResult({ outcome: 'LISTED', teams: [] }).content,
    /no teams/i,
  );
  assert.match(renderListTeamsResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderRenameTeamResult covers outcomes', () => {
  assert.match(
    renderRenameTeamResult({ outcome: 'RENAMED', team: { slug: 'ml', label: 'New' } }).content,
    /New/,
  );
  assert.match(renderRenameTeamResult({ outcome: 'TEAM_NOT_FOUND' }).content, /no team|not found/i);
  assert.match(renderRenameTeamResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderAddMemberResult covers outcomes', () => {
  assert.match(
    renderAddMemberResult({
      outcome: 'ADDED',
      person: { display_name: 'Alex' },
      team: { label: 'ML' },
    }).content,
    /Alex.*ML/s,
  );
  assert.match(renderAddMemberResult({ outcome: 'USER_NOT_LINKED' }).content, /link/i);
  assert.match(renderAddMemberResult({ outcome: 'TEAM_NOT_FOUND' }).content, /no team|not found/i);
  assert.match(
    renderAddMemberResult({ outcome: 'ALREADY_ON_TEAM', person: { display_name: 'Alex' }, team: { label: 'ML' } }).content,
    /already/i,
  );
  const invalid = renderAddMemberResult({ outcome: 'MEMBERSHIP_INVALID', detail: 'role_kind_id not found: lead' }).content;
  assert.match(invalid, /rejected/i);
  assert.match(invalid, /role_kind_id not found: lead/);
  assert.match(renderAddMemberResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderRemoveMemberResult covers outcomes', () => {
  assert.match(
    renderRemoveMemberResult({
      outcome: 'REMOVED',
      person: { display_name: 'Alex' },
      team: { label: 'ML' },
    }).content,
    /Alex.*ML/s,
  );
  assert.match(
    renderRemoveMemberResult({ outcome: 'USER_NOT_LINKED' }).content,
    /aren't on any team|not on any team/i,
  );
  assert.match(renderRemoveMemberResult({ outcome: 'TEAM_NOT_FOUND' }).content, /no team|not found/i);
  assert.match(
    renderRemoveMemberResult({ outcome: 'NOT_ON_TEAM', person: { display_name: 'Alex' }, team: { label: 'ML' } }).content,
    /not on/i,
  );
  assert.match(renderRemoveMemberResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderRosterResult covers outcomes', () => {
  const roster = renderRosterResult({
    outcome: 'ROSTER',
    team: { slug: 'ml', label: 'ML' },
    members: [
      { person: { display_name: 'One' }, role_kind_id: 'lead', is_team_admin: true },
      { person: { display_name: 'Two' }, role_kind_id: 'member', is_team_admin: false },
    ],
  }).content;
  assert.match(roster, /One/);
  assert.match(roster, /Two/);
  assert.match(roster, /lead/);
  assert.match(roster, /ML|ml/);
  assert.match(
    renderRosterResult({ outcome: 'ROSTER', team: { slug: 'ml', label: 'ML' }, members: [] }).content,
    /no members|empty/i,
  );
  assert.match(renderRosterResult({ outcome: 'TEAM_NOT_FOUND' }).content, /no team|not found/i);
  assert.match(renderRosterResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('renderMyTeamsResult covers outcomes', () => {
  const out = renderMyTeamsResult({
    outcome: 'MY_TEAMS',
    memberships: [
      { team: { slug: 'ml', label: 'ML' }, role_kind_id: 'lead', is_team_admin: true },
      { team: { slug: 'ops', label: 'Ops' }, role_kind_id: 'member', is_team_admin: false },
    ],
  }).content;
  assert.match(out, /ML/);
  assert.match(out, /Ops/);
  assert.match(
    renderMyTeamsResult({ outcome: 'MY_TEAMS', memberships: [] }).content,
    /not on any/i,
  );
  assert.match(renderMyTeamsResult({ outcome: 'DIRECTORY_DOWN' }).content, /unavailable|try again/i);
});

test('personal/admin render functions return ReplyPayload with ephemeral: true', () => {
  const payloads = [
    renderLinkResult({ outcome: 'DIRECTORY_DOWN' }),
    renderSeedResult({ outcome: 'DIRECTORY_DOWN' }),
    renderCreateTeamResult({ outcome: 'DIRECTORY_DOWN' }),
    renderRenameTeamResult({ outcome: 'DIRECTORY_DOWN' }),
    renderAddMemberResult({ outcome: 'DIRECTORY_DOWN' }),
    renderRemoveMemberResult({ outcome: 'DIRECTORY_DOWN' }),
    renderMyTeamsResult({ outcome: 'DIRECTORY_DOWN' }),
  ];
  for (const p of payloads) {
    assert.equal(typeof p.content, 'string');
    assert.equal(p.ephemeral, true);
    assert.equal(p.embeds, undefined);
  }
});

test('shared-reference render functions (list, roster) are public (ephemeral: false)', () => {
  const payloads = [
    renderListTeamsResult({ outcome: 'DIRECTORY_DOWN' }),
    renderRosterResult({ outcome: 'DIRECTORY_DOWN' }),
  ];
  for (const p of payloads) {
    assert.equal(typeof p.content, 'string');
    assert.equal(p.ephemeral, false);
    assert.equal(p.embeds, undefined);
  }
});
