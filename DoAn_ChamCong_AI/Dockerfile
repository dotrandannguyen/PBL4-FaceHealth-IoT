FROM php:8.2-apache

# Cai dat extension pdo_mysql va python3 cho xac thuc scrypt
RUN apt-get update && apt-get install -y \
    python3 \
    libmariadb-dev \
    libonig-dev \
    && docker-php-ext-install pdo pdo_mysql mbstring \
    && a2enmod rewrite \
    && rm -rf /var/lib/apt/lists/*

# Thu muc goc cho ma nguon PHP
WORKDIR /var/www/html

# Copy toan bo code vao container
COPY . /var/www/html/

# Phan quyen www-data
RUN chown -R www-data:www-data /var/www/html

EXPOSE 80
CMD ["apache2-foreground"]
