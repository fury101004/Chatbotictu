# HÆ°á»›ng dáº«n scale chatbot API trĂªn chĂ­nh mĂ¡y cĂ¡ nhĂ¢n (VPS/Server) -- KhĂ´ng tá»‘n thĂªm tiá»n

### YĂªu cáº§u

-   MĂ¡y Ä‘Ă£ cĂ i Docker + Docker Compose
-   Chatbot Ä‘ang cháº¡y tá»‘t trong Docker

### 1. TÄƒng worker ngay trong container (nhanh nháº¥t)

Sá»­a lá»‡nh cháº¡y container thĂ nh:

``` bash
docker run -d \
  --name chatbot \
  --restart unless-stopped \
  -p 8000:8000 \
  your-image \
  uvicorn config.asgi:app --host 0.0.0.0 --port 8000 --workers 8
```

â†’ Äáº·t **--workers = sá»‘ CPU core** cá»§a báº¡n (xem báº±ng `nproc`).

------------------------------------------------------------------------

### 2. CĂ i Nginx lĂ m reverse proxy + load balancer

``` bash
sudo apt update && sudo apt install nginx -y
```

Táº¡o file config:

``` bash
sudo nano /etc/nginx/sites-available/chatbot
```

DĂ¡n ná»™i dung sau:

``` nginx
upstream chatbot_backend {
    server 127.0.0.1:8000;
    # Náº¿u muá»‘n cháº¡y nhiá»u container thĂ¬ thĂªm dĂ²ng dÆ°á»›i
    # server 127.0.0.1:8001;
    # server 127.0.0.1:8002;
}

server {
    listen 80;
    server_name your-domain.com _;

    location / {
        proxy_pass http://chatbot_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Náº¿u cĂ³ WebSocket (chat realtime)
    location /ws {
        proxy_pass http://chatbot_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

KĂ­ch hoáº¡t vĂ  restart:

``` bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

------------------------------------------------------------------------

### 3. (Tuá»³ chá»n) Cháº¡y nhiá»u container cĂ¹ng lĂºc Ä‘á»ƒ tÄƒng gáº¥p Ä‘Ă´i throughput

``` yaml
# docker-compose.yml
version: '3.8'
services:
  chatbot1:
    image: your-image
    command: uvicorn config.asgi:app --host 0.0.0.0 --port 8000 --workers 4
    restart: unless-stopped

  chatbot2:
    image: your-image
    command: uvicorn config.asgi:app --host 0.0.0.0 --port 8001 --workers 4
    restart: unless-stopped

  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - chatbot1
      - chatbot2
```

Sau Ä‘Ă³ cháº¡y:

``` bash
docker compose up -d
```

------------------------------------------------------------------------

### 4. ThĂªm Redis cache (giáº£m táº£i DB 80--90%)

``` bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Trong code Python:

``` python
import redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
```

------------------------------------------------------------------------

### Káº¿t quáº£

Chá»‰ vá»›i **4 bÆ°á»›c**, mĂ¡y cá»§a báº¡n cĂ³ thá»ƒ chá»‹u Ä‘Æ°á»£c **gáº¥p 5--20 láº§n lÆ°á»£ng
user** hiá»‡n táº¡i mĂ  khĂ´ng cáº§n mua thĂªm server.

đŸ€ *ChĂºc báº¡n scale ngon lĂ nh!*

