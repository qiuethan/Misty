import { AlreadyLinked, DirectoryUnavailable } from './directoryClient.js';

export function createLinkService({ directory }) {
  async function linkByEmail({ email, discordUserId, discordHandle }) {
    try {
      const person = await directory.getPersonByEmail(email);
      if (!person) return { outcome: 'NOT_A_MEMBER' };

      // TODO: verification — before creating the link, email a one-time code to
      // `email` and require the user to confirm it, proving they own the address.
      // This is the trust boundary the auth layer ultimately rests on (see
      // auth/principal.js). v1 links on directory email-match alone (members are
      // pre-seeded by execs).

      await directory.linkDiscord(person.id, {
        externalId: discordUserId,
        handle: discordHandle,
      });
      return { outcome: 'LINKED', person };
    } catch (e) {
      if (e instanceof AlreadyLinked) return { outcome: 'ALREADY_LINKED', detail: e.detail };
      if (e instanceof DirectoryUnavailable) return { outcome: 'DIRECTORY_DOWN' };
      throw e;
    }
  }

  return { linkByEmail };
}
