# ─────────────────────────────────────────────────────────────
#  Frontend · React 19 + Vite + TypeScript
#  Etapas:  development | builder → production
# ─────────────────────────────────────────────────────────────

# ============ DEVELOPMENT ===================================
FROM node:22-alpine AS development

WORKDIR /app
ENV NODE_ENV=development

COPY package*.json ./
RUN npm install

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ============ BUILDER =======================================
FROM node:22-alpine AS builder

WORKDIR /app

ARG VITE_API_URL=/api/v1
ARG VITE_WS_URL=/ws
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    NODE_ENV=production

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ============ PRODUCTION ====================================
FROM nginx:1.27-alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/nginx-spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
