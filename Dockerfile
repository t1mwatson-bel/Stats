FROM mcr.microsoft.com/playwright:v1.58.2-focal

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY index.js ./

CMD ["node", "index.js"]
