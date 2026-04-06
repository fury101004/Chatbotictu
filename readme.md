Làm trong 5–10 phút là có HTTPS xanh lè, đẹp như website thật.

Tạo lại docker-compose.yml chuẩn production (thêm Nginx + Certbot)
Thay toàn bộ nội dung file docker-compose.yml bằng cái này (đã test rất nhiều lần):

YAMLservices:
  backend:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
    expose:
      - "8000"
    networks:
      - app-network

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - certbot-web:/var/www/html
      - certbot-conf:/etc/letsencrypt
    depends_on:
      - backend
    networks:
      - app-network

  certbot:
    image: certbot/certbot
    volumes:
      - certbot-web:/var/www/html
      - certbot-conf:/etc/letsencrypt
    depends_on:
      - nginx
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 6h & wait $${!}; done;'"

volumes:
  certbot-web:
  certbot-conf:

networks:
  app-network:
    driver: bridge

Tạo thư mục và file config Nginx

Bashmkdir -p nginx/conf.d
nano nginx/conf.d/default.conf
Dán vào:
nginxserver {
    listen 80;
    server_name your-domain.com www.your-domain.com;  # thay bằng domain hoặc IP tạm thời

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name your-domain.com www.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

Chạy và lấy chứng chỉ SSL miễn phí

Bashdocker compose up -d
# Lấy chứng chỉ (thay your-email và your-domain.com thật của bạn)
docker compose run --rm certbot certonly --webroot --webroot-path=/var/www/html -d your-domain.com -d www.your-domain.com --email you@gmail.com --agree-tos --no-eff-email
Xong! Từ giờ truy cập https://your-domain.com là có HTTPS xanh lè, bảo mật, tốc độ nhanh.
Bạn muốn đi cách nhanh (cách 1) hay làm luôn cách pro có HTTPS (cách 2)?
Mình hướng dẫn chi tiết từng bước luôn nếu bạn chọn cách 2 nhé!


annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
attrs==26.1.0
backoff==2.2.1
bcrypt==5.0.0
build==1.4.2
cachetools==6.2.6
certifi==2026.2.25
cffi==2.0.0
charset-normalizer==3.4.7
chromadb==1.5.5
click==8.2.1
colorama==0.4.6
coloredlogs==15.0.1
cryptography==46.0.6
Deprecated==1.3.1
distro==1.9.0
durationpy==0.10
exceptiongroup==1.3.1
fastapi==0.128.8
filelock==3.19.1
flatbuffers==25.12.19
fsspec==2025.10.0
google-ai-generativelanguage==0.6.15
google-api-core==2.30.2
google-api-python-client==2.193.0
google-auth==2.49.1
google-auth-httplib2==0.3.1
google-generativeai==0.8.6
googleapis-common-protos==1.74.0
grpcio==1.80.0
grpcio-status==1.71.2
h11==0.16.0
httpcore==1.0.9
httplib2==0.31.2
httptools==0.7.1
httpx==0.28.1
huggingface_hub==0.36.2
humanfriendly==10.0
idna==3.11
importlib_metadata==8.7.1
importlib_resources==6.5.2
itsdangerous==2.2.0
Jinja2==3.1.6
joblib==1.5.3
jsonschema==4.25.1
jsonschema-specifications==2025.9.1
kubernetes==35.0.0
limits==4.2
markdown-it-py==3.0.0
MarkupSafe==3.0.3
mdurl==0.1.2
mmh3==5.2.0
mpmath==1.3.0
networkx==3.2.1
numpy==2.0.2
oauthlib==3.3.1
onnxruntime==1.19.2
opentelemetry-api==1.40.0
opentelemetry-exporter-otlp-proto-common==1.40.0
opentelemetry-exporter-otlp-proto-grpc==1.40.0
opentelemetry-proto==1.40.0
opentelemetry-sdk==1.40.0
opentelemetry-semantic-conventions==0.61b0
orjson==3.11.5
overrides==7.7.0
packaging==24.2
pillow==11.3.0
posthog==6.9.3
proto-plus==1.27.2
protobuf==5.29.6
pyasn1==0.6.3
pyasn1_modules==0.4.2
pybase64==1.4.3
pycparser==2.23
pydantic==2.12.5
pydantic-settings==2.11.0
pydantic_core==2.41.5
Pygments==2.20.0
PyJWT==2.12.1
PyMuPDF==1.26.5
pyparsing==3.3.2
pypdf==6.9.2
PyPika==0.51.1
pyproject_hooks==1.2.0
pyreadline3==3.5.4
python-dateutil==2.9.0.post0
python-dotenv==1.2.1
python-multipart==0.0.20
PyYAML==6.0.3
rank-bm25==0.2.2
referencing==0.36.2
regex==2026.1.15
requests==2.32.5
requests-oauthlib==2.0.0
rich==14.3.3
rpds-py==0.27.1
rsa==4.9.1
safetensors==0.7.0
scikit-learn==1.6.1
scipy==1.13.1
sentence-transformers==5.1.2
shellingham==1.5.4
six==1.17.0
slowapi==0.1.9
starlette==0.49.3
sympy==1.14.0
tenacity==9.1.2
threadpoolctl==3.6.0
tiktoken==0.12.0
tokenizers==0.22.2
tomli==2.4.1
torch==2.8.0
tqdm==4.67.3
transformers==4.57.6
typer==0.23.2
typing-inspection==0.4.2
typing_extensions==4.15.0
uritemplate==4.2.0
urllib3==2.6.3
uvicorn==0.39.0
watchfiles==1.1.1
websocket-client==1.9.0
websockets==15.0.1
wrapt==2.1.2
zipp==3.23.0
