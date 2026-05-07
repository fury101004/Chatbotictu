# Hướng dẫn scale chatbot API trên chính máy cá nhân (VPS/Server) -- Không tốn thêm tiền

### Yêu cầu

-   Máy đã cài Docker + Docker Compose
-   Chatbot đang chạy tốt trong Docker

### 1. Tăng worker ngay trong container (nhanh nhất)

Sửa lệnh chạy container thành:

``` bash
docker run -d \
  --name chatbot \
  --restart unless-stopped \
  -p 8000:8000 \
  your-image \
  uvicorn config.asgi:app --host 0.0.0.0 --port 8000 --workers 8
```

→ Đặt **--workers = số CPU core** của bạn (xem bằng `nproc`).

------------------------------------------------------------------------

### 2. Cài Nginx làm reverse proxy + load balancer

``` bash
sudo apt update && sudo apt install nginx -y
```

Tạo file config:

``` bash
sudo nano /etc/nginx/sites-available/chatbot
```

Dán nội dung sau:

``` nginx
upstream chatbot_backend {
    server 127.0.0.1:8000;
    # Nếu muốn chạy nhiều container thì thêm dòng dưới
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

    # Nếu có WebSocket (chat realtime)
    location /ws {
        proxy_pass http://chatbot_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Kích hoạt và restart:

``` bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

------------------------------------------------------------------------

### 3. (Tuỳ chọn) Chạy nhiều container cùng lúc để tăng gấp đôi throughput

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

Sau đó chạy:

``` bash
docker compose up -d
```

------------------------------------------------------------------------

### 4. Thêm Redis cache (giảm tải DB 80--90%)

``` bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Trong code Python:

``` python
import redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
```

------------------------------------------------------------------------

### Kết quả

Chỉ với **4 bước**, máy của bạn có thể chịu được **gấp 5--20 lần lượng
user** hiện tại mà không cần mua thêm server.

*Chúc bạn scale ngon lành!*

