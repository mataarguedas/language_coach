# Dev-mode image: runs the Vite dev server with HMR inside the container.
# For production the frontend is built and deployed to Vercel, so this
# Dockerfile intentionally targets local development / docker-compose only.
FROM node:20-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# App source is bind-mounted by docker-compose so edits trigger HMR;
# copying here just gives the image a working default when run standalone.
COPY . .

EXPOSE 5173

# --host 0.0.0.0 is required so the port is reachable from the host.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
