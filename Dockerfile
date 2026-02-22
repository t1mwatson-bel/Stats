FROM mcr.microsoft.com/playwright:v1.51.0-focal

WORKDIR /app

# Копируем все файлы проекта
COPY package*.json ./
RUN npm install

# Копируем все остальные файлы, включая index.js и last_number.txt
COPY . .

CMD ["node", "index.js"]
