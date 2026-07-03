/**
 * Neutral command definition. Consumed by the Discord adapter and the web
 * adapter. No discord.js dependency here.
 */
export function defineCommand({ name, description, auth, beta, ephemeral, options, handler, subcommands }) {
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
      // Visibility hint used to defer the Discord reply before the (possibly
      // slow) handler runs. Inherits the command-level value unless overridden.
      ephemeral: sub.ephemeral ?? ephemeral ?? true,
      options: sub.options ?? [],
      handler: sub.handler,
    };
  });
  return {
    name,
    description: description ?? '',
    auth: auth ?? 'linked',
    beta: beta ?? false,
    // Default to ephemeral: bot replies are personal directory/team info.
    ephemeral: ephemeral ?? true,
    options: options ?? [],
    handler,
    subcommands: normalizedSubs,
  };
}
