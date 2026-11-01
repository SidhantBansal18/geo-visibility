FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1 API_URL=http://backend:8000
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 API_URL=http://backend:8000
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "start"]
