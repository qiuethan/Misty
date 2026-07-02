import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { dispatch } from '../router.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export async function buildServer({ commands, appContext }) {
  const server = Fastify({ logger: false });

  await server.register(fastifyStatic, {
    root: path.join(__dirname, 'public'),
    prefix: '/',
  });

  server.get('/api/commands', async () => {
    return Array.from(commands.values()).map((c) => ({
      name: c.name,
      description: c.description,
      auth: typeof c.auth === 'string' ? c.auth : 'dynamic',
      options: c.options,
      subcommands: c.subcommands.map((s) => ({
        name: s.name,
        description: s.description,
        auth: typeof s.auth === 'string' ? s.auth : 'dynamic',
        options: s.options,
      })),
    }));
  });

  server.post('/api/commands/:name/run', async (req, reply) => {
    const command = commands.get(req.params.name);
    if (!command) {
      reply.code(404);
      return { error: 'unknown command' };
    }
    const { options = {}, subcommand = null, actingAs } = req.body ?? {};

    if (typeof actingAs !== 'string' || actingAs.trim() === '') {
      reply.code(400);
      return { error: 'actingAs is required' };
    }

    const activeOptions = subcommand
      ? command.subcommands.find((s) => s.name === subcommand)?.options ?? []
      : command.options;
    const coerced = { ...options };
    for (const o of activeOptions) {
      const value = coerced[o.name];
      if (o.type === 'user' && typeof value === 'string') {
        coerced[o.name] = { id: value };
      } else if (o.type === 'boolean' && typeof value === 'string') {
        if (value === '') delete coerced[o.name];
        else coerced[o.name] = value === 'true';
      }
    }

    const intent = {
      commandName: command.name,
      options: coerced,
      subcommand,
      discordUserId: String(actingAs),
      discordHandle: `spoof-${actingAs}`,
    };
    const payload = await dispatch(intent, { commands, appContext });
    return payload ?? {};
  });

  server.setErrorHandler(async (err, req, reply) => {
    reply.code(err.statusCode ?? 500).send({ content: `Error: ${err.message}`, ephemeral: true });
  });

  return server;
}

export async function startWebServer({ commands, appContext, port = 3001 }) {
  const server = await buildServer({ commands, appContext });
  await server.listen({ port, host: '127.0.0.1' });
  console.log(`Web playground: http://127.0.0.1:${port}`);
  return server;
}
