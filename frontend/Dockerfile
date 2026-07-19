# ---- Stage 1: Build ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar archivos de dependencias
COPY package.json package-lock.json ./

# Forzar instalación de TODAS las dependencias incluyendo dev
RUN npm ci

# Copiar código fuente
COPY . .

# Verificar que vite existe antes de build
RUN ls node_modules/.bin/vite

# Build usando ruta absoluta al binario
RUN node_modules/.bin/vite build

# ---- Stage 2: Nginx ----
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]