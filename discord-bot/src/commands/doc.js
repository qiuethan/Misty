import { defineCommand } from '../defineCommand.js';
import {
  renderDocAddResult,
  renderDocListResult,
  renderDocShowResult,
  renderDocRemoveResult,
} from '../messages.js';

// Suggest the caller's own active teams for a `team` option. Best-effort: the
// router's dispatchAutocomplete already swallows throws, but we also guard here
// so an unlinked caller (null principal) simply gets no suggestions.
const AUTOCOMPLETE_TIMEOUT_MS = 2500;

async function teamAutocomplete({ typed, principal, ctx }) {
  if (!principal?.person?.id) return [];
  // Autocomplete cannot be deferred and must answer within Discord's ~3s window.
  // Bound the directory lookups so a cold/slow directory yields no suggestions
  // rather than hanging past the window — the field still accepts a typed slug.
  const budget = ctx._autocompleteTimeoutMs ?? AUTOCOMPLETE_TIMEOUT_MS;
  let timer;
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve(null), budget);
  });
  // Two directory calls (memberships + all teams) instead of N per-team lookups.
  const lookup = Promise.all([
    ctx.directory.listMemberships({ personId: principal.person.id, activeOnly: true }),
    ctx.directory.listTeams({ activeOnly: true }),
  ]);
  const result = await Promise.race([lookup, timeout]);
  clearTimeout(timer);
  if (result === null) return []; // timed out — degrade to no suggestions
  const [memberships, teams] = result;
  const myTeamIds = new Set(memberships.map((m) => m.team_id));
  const needle = (typed ?? '').toLowerCase();
  return teams
    .filter((t) => myTeamIds.has(t.id))
    // A team with no usable label can't be shown as a suggestion — drop it
    // instead of emitting a { name: null } choice Discord would reject.
    .filter((t) => typeof t.label === 'string' && t.label.length > 0)
    .filter((t) => t.label.toLowerCase().includes(needle) || (t.slug ?? '').toLowerCase().includes(needle))
    .slice(0, 25)
    .map((t) => ({ name: t.label, value: t.slug }));
}

function parseTags(raw) {
  if (raw === null || raw === undefined) return [];
  return raw
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.length > 0);
}

export default defineCommand({
  name: 'doc',
  description: 'Catalog and look up UTMIST documents and links',
  auth: 'linked',
  beta: true,
  options: [],
  subcommands: [
    {
      name: 'add',
      description: 'Catalog a URL in the doc registry',
      auth: 'linked',
      options: [
        { name: 'url', type: 'string', required: true, description: 'The link to catalog' },
        { name: 'title', type: 'string', required: false, description: 'Optional title (auto-fetched if omitted)' },
        { name: 'team', type: 'string', required: false, description: 'Owning team (slug)', autocomplete: teamAutocomplete },
        { name: 'tags', type: 'string', required: false, description: 'Comma-separated tags' },
      ],
      async handler({ options, ctx }) {
        const args = { url: options.url };
        if (options.title !== null && options.title !== undefined) args.title = options.title;
        if (options.team !== null && options.team !== undefined) args.teamSlug = options.team;
        args.tags = parseTags(options.tags);
        const result = await ctx.docService.addDoc(args);
        return renderDocAddResult(result);
      },
    },
    {
      name: 'list',
      description: 'Browse the doc catalog',
      auth: 'linked',
      ephemeral: false,
      options: [
        { name: 'team', type: 'string', required: false, description: 'Filter by owning team (slug)', autocomplete: teamAutocomplete },
        { name: 'tag', type: 'string', required: false, description: 'Filter by tag' },
        { name: 'source', type: 'string', required: false, description: 'Filter by source kind (e.g. gdocs, github)' },
      ],
      async handler({ options, ctx }) {
        const args = {};
        if (options.team !== null && options.team !== undefined) args.teamSlug = options.team;
        if (options.tag !== null && options.tag !== undefined) args.tag = options.tag;
        if (options.source !== null && options.source !== undefined) args.source = options.source;
        const result = await ctx.docService.listDocs(args);
        return renderDocListResult(result);
      },
    },
    {
      name: 'show',
      description: 'Show full detail for one doc',
      auth: 'linked',
      ephemeral: false,
      options: [
        { name: 'id', type: 'string', required: true, description: 'Doc id (from /doc list)' },
      ],
      async handler({ options, ctx }) {
        const result = await ctx.docService.showDoc({ id: options.id });
        return renderDocShowResult(result);
      },
    },
    {
      name: 'remove',
      description: 'Remove a doc from the catalog (admin)',
      auth: 'admin',
      options: [
        { name: 'id', type: 'string', required: true, description: 'Doc id (from /doc list)' },
      ],
      async handler({ options, ctx }) {
        const result = await ctx.docService.removeDoc({ id: options.id });
        return renderDocRemoveResult(result);
      },
    },
  ],
  async handler(intent) {
    const sub = this.subcommands.find((s) => s.name === intent.subcommand);
    if (!sub) return { content: 'Something went wrong. Please try again.', ephemeral: true };
    return sub.handler(intent);
  },
});
