# Frontend Dockerfile — multi-stage production build

# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_APP_GIT_SHA=unknown
ARG VITE_APP_BUILD_TIME=unknown
ENV VITE_APP_GIT_SHA=$VITE_APP_GIT_SHA
ENV VITE_APP_BUILD_TIME=$VITE_APP_BUILD_TIME
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: serve built assets via nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
