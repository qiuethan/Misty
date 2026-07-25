FROM node:20-slim

WORKDIR /app

# ffmpeg is required at runtime to mix/transcode meeting recordings (src/audio helpers).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

# Install production dependencies against the lockfile for reproducibility.
COPY package.json package-lock.json ./
# --legacy-peer-deps: prism-media's optional opusscript peer range (^0.0.8) is
# older than the opusscript version we actually depend on (^0.1.1); npm's
# strict ERESOLVE check would otherwise fail the build over this false conflict.
RUN npm ci --omit=dev --legacy-peer-deps

# Copy the application source (node_modules/.env excluded via .dockerignore).
COPY . .

ENV NODE_ENV=production

# Env vars (DISCORD_TOKEN, DIRECTORY_BASE_URL, DIRECTORY_API_KEY, ENABLE_*) are
# injected by the hosting platform. The container does NOT read a .env file, so
# we invoke node directly rather than `npm start` (which passes --env-file=.env).
CMD ["node", "src/index.js"]
