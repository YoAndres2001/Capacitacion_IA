FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf

COPY prod.conf /etc/nginx/conf.d/default.conf
COPY snippets/ /etc/nginx/snippets/

RUN mkdir -p /var/www/media /var/www/static /etc/nginx/certs

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/health/nginx >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
