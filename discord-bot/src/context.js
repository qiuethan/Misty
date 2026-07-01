import { createDirectoryClient } from './directoryClient.js';
import { createLinkService } from './linkService.js';

// Wire the application services once. The router spreads this into every
// command's ctx (alongside the request-scoped principal). Add a second backend
// later (e.g. a docsClient for documentation-system) by constructing it here.
export function createAppContext(config) {
  const directory = createDirectoryClient({
    baseUrl: config.directoryBaseUrl,
    apiKey: config.directoryApiKey,
  });
  const linkService = createLinkService({ directory });
  return { directory, linkService };
}
