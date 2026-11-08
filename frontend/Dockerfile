FROM nginxinc/nginx-unprivileged:stable-alpine
COPY frontend/*.html /usr/share/nginx/html/
COPY frontend/assets/ /usr/share/nginx/html/assets/
COPY ops/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
