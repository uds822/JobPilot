# ==============================================================================
# Stage 1: Build React/Vite SPA
# ==============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package descriptors first to maximize Docker layer caching
COPY package*.json ./

RUN npm ci

# Copy full frontend source code
COPY . .

# Compile TypeScript and bundle Vite production assets
RUN npm run build

# ==============================================================================
# Stage 2: Production Nginx Server
# ==============================================================================
FROM nginx:alpine AS runtime

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom reverse proxy & SPA Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

