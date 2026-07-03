import { createDirectoryClient } from './directoryClient.js';
import { createDocClient } from './docClient.js';
import { createLinkService } from './linkService.js';
import { createSeedService } from './seedService.js';
import { createTeamService } from './teamService.js';
import { createDocService } from './docService.js';

// Wire the application services once. The router spreads this into every
// command's ctx (alongside the request-scoped principal).
export function createAppContext(config) {
  const directory = createDirectoryClient({
    baseUrl: config.directoryBaseUrl,
    apiKey: config.directoryApiKey,
  });
  const docClient = createDocClient({
    baseUrl: config.docBaseUrl,
    apiKey: config.docApiKey,
  });
  const linkService = createLinkService({ directory });
  const seedService = createSeedService({ directory });
  const teamService = createTeamService({ directory });
  const docService = createDocService({ docClient, directory });
  return { directory, docClient, linkService, seedService, teamService, docService };
}
