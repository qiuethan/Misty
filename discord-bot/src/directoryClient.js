export class DirectoryUnavailable extends Error {
  constructor(message) {
    super(message);
    this.name = 'DirectoryUnavailable';
  }
}

async function parseJson(resp) {
  try {
    return await resp.json();
  } catch {
    throw new DirectoryUnavailable('malformed directory response');
  }
}

export class AlreadyLinked extends Error {
  constructor(detail) {
    super(detail);
    this.name = 'AlreadyLinked';
    this.detail = detail;
  }
}

export class PersonExists extends Error {
  constructor(detail) {
    super(detail);
    this.name = 'PersonExists';
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
    return parseJson(resp);
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
      if (resp.status === 201) return parseJson(resp);
      if (resp.status === 409) {
        const body = await resp.json().catch(() => ({}));
        throw new AlreadyLinked(body.detail ?? 'already linked');
      }
      throw new DirectoryUnavailable(`directory returned ${resp.status}`);
    },

    async createPerson({ displayName, primaryEmail, accessLevel }) {
      const resp = await send('/people', {
        method: 'POST',
        body: JSON.stringify({
          display_name: displayName,
          primary_email: primaryEmail,
          access_level: accessLevel,
        }),
      });
      if (resp.status === 201) return parseJson(resp);
      if (resp.status === 409) {
        const body = await resp.json().catch(() => ({}));
        throw new PersonExists(body.detail ?? 'person already exists');
      }
      throw new DirectoryUnavailable(`directory returned ${resp.status}`);
    },
  };
}
