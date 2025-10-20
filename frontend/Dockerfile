FROM node:18-alpine

WORKDIR /app

# Copy package files first for better caching
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

EXPOSE 3000

# Use npm start for development with hot reload
CMD ["npm", "start"]