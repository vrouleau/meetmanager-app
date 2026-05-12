FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG BUILD_TIMESTAMP=""
RUN apk add --no-cache tzdata && \
    if [ -n "${BUILD_TIMESTAMP}" ]; then echo "${BUILD_TIMESTAMP}" > /tmp/bt; \
    else TZ=America/Toronto date '+%Y-%m-%d %H:%M ET' > /tmp/bt; fi && \
    echo "export const BUILD_TIMESTAMP = '$(cat /tmp/bt)';" > src/buildInfo.js
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
