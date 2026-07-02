/**
 * Neutral command definition. Consumed by the Discord adapter and the web
 * adapter. No discord.js dependency here.
 */
export function defineCommand({ name, description, auth, beta, options, handler, subcommands }) {
  if (!name || typeof name !== 'string') {
    throw new Error('defineCommand: `name` (string) is required');
  }
  if (!handler || typeof handler !== 'function') {
    throw new Error('defineCommand: `handler` (async function) is required');
  }
  const normalizedSubs = (subcommands ?? []).map((sub) => {
    if (!sub.name || typeof sub.name !== 'string') {
      throw new Error(`defineCommand ${name}: subcommand missing name`);
    }
    if (!sub.handler || typeof sub.handler !== 'function') {
      throw new Error(`defineCommand ${name}: subcommand ${sub.name} missing handler`);
    }
    return {
      name: sub.name,
      description: sub.description ?? '',
      auth: sub.auth ?? auth ?? 'linked',
      options: sub.options ?? [],
      handler: sub.handler,
    };
  });
  return {
    name,
    description: description ?? '',
    auth: auth ?? 'linked',
    beta: beta ?? false,
    options: options ?? [],
    handler,
    subcommands: normalizedSubs,
  };
}
