# == Build stage ==
FROM node:24-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_BACKEND_URL=${NEXT_PUBLIC_BACKEND_URL}

COPY package.json package-lock.json ./
RUN npm install

COPY . .

RUN npm run build


# == Runtime stage ==
FROM node:24-alpine AS runner

WORKDIR /app

COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/tsconfig.json ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next

# Install all deps (typescript needed to transpile next.config.ts at runtime)
RUN npm install

ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "start"]