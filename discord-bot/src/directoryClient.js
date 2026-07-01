export class DirectoryUnavailable extends Error {}

export class AlreadyLinked extends Error {
  constructor(detail) {
    super(detail);
    this.name = 'AlreadyLinked';
    this.detail = detail;
  }
}

export function createDirectoryClient({ baseUrl, apiKey, fetchImpl = fetch }) {
  const headers = { 'X-API-Key': apiKey, 'Content-Type': 'application/json' };

  async function send(path, options = {}) {
    try {
      return await fetchImpl(`${baseUrl}${path}`, { ...options, headers });
    } catch {
      throw new DirectoryUnavailable('network error reaching directory');
    }
  }

  async function getByPath(path) {
    const resp = await send(path);
    if (resp.status === 404) return null;
    if (!resp.ok) throw new DirectoryUnavailable(`directory returned ${resp.status}`);
    return resp.json();
  }

  return {
    getPersonByEmail(email) {
      return getByPath(`/people/by-email/${encodeURIComponent(email)}`);
    },

    getPersonByDiscordId(snowflake) {
      return getByPath(`/people/by-identifier/discord/${encodeURIComponent(snowflake)}`);
    },

    async linkDiscord(personId, { externalId, handle }) {
      const resp = await send(`/people/${encodeURIComponent(personId)}/identifiers`, {
        method: 'POST',
        body: JSON.stringify({ provider: 'discord', external_id: externalId, handle }),
      });
      if (resp.status === 201) return resp.json();
      if (resp.status === 409) {
        const body = await resp.json().catch(() => ({}));
        throw new AlreadyLinked(body.detail ?? 'already linked');
      }
      throw new DirectoryUnavailable(`directory returned ${resp.status}`);
    },
  };
}
