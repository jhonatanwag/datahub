FROM mcr.microsoft.com/playwright:v1.55.0-jammy

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.mjs ./

EXPOSE 4000
CMD ["node", "server.mjs"]
