export class DocUnavailable extends Error {
  constructor(message) {
    super(message);
    this.name = 'DocUnavailable';
  }
}

export class DocBadReference extends Error {
  constructor(detail) {
    super(detail);
    this.name = 'DocBadReference';
    this.detail = detail;
  }
}

async function parseJson(resp) {
  try {
    return await resp.json();
  } catch {
    throw new DocUnavailable('malformed doc-service response');
  }
}

export function createDocClient({ baseUrl, apiKey, fetchImpl = fetch }) {
  const headers = { 'X-API-Key': apiKey, 'Content-Type': 'application/json' };

  async function send(path, options = {}) {
    try {
      return await fetchImpl(`${baseUrl}${path}`, { ...options, headers });
    } catch {
      throw new DocUnavailable('network error reaching doc service');
    }
  }

  return {
    async ingestDoc({ url, sourceId, title, description, owningTeamId, owningPersonId, tags }) {
      const body = { url };
      if (sourceId !== undefined) body.source_id = sourceId;
      if (title !== undefined) body.title = title;
      if (description !== undefined) body.description = description;
      if (owningTeamId !== undefined) body.owning_team_id = owningTeamId;
      if (owningPersonId !== undefined) body.owning_person_id = owningPersonId;
      if (tags !== undefined) body.tags = tags;
      const resp = await send('/docs', { method: 'POST', body: JSON.stringify(body) });
      if (resp.ok) return parseJson(resp);
      if (resp.status === 400) {
        const b = await resp.json().catch(() => ({}));
        throw new DocBadReference(b.detail ?? 'bad reference');
      }
      throw new DocUnavailable(`doc service returned ${resp.status}`);
    },

    async listDocs({ owningTeamId, owningPersonId, sourceId, tag, activeOnly } = {}) {
      const qs = new URLSearchParams();
      if (owningTeamId) qs.set('owning_team_id', owningTeamId);
      if (owningPersonId) qs.set('owning_person_id', owningPersonId);
      if (sourceId) qs.set('source_id', sourceId);
      if (tag) qs.set('tag', tag);
      if (activeOnly !== undefined) qs.set('active_only', String(activeOnly));
      const qstr = qs.toString();
      const resp = await send(qstr ? `/docs?${qstr}` : '/docs');
      if (!resp.ok) throw new DocUnavailable(`doc service returned ${resp.status}`);
      return parseJson(resp);
    },

    async getDoc(id) {
      const resp = await send(`/docs/${encodeURIComponent(id)}`);
      if (resp.status === 404) return null;
      if (!resp.ok) throw new DocUnavailable(`doc service returned ${resp.status}`);
      return parseJson(resp);
    },

    async deactivateDoc(id) {
      const resp = await send(`/docs/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: JSON.stringify({ active: false }),
      });
      if (resp.status === 404) return null;
      if (!resp.ok) throw new DocUnavailable(`doc service returned ${resp.status}`);
      return parseJson(resp);
    },
  };
}
