FROM mcr.microsoft.com/playwright:focal

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY index.js ./

CMD ["node", "index.js"]
