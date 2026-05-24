# Nội dung báo cáo: Triển khai hệ thống lên Azure

## Mục tiêu triển khai

Hệ thống chatbot ICTU được triển khai lên Azure nhằm chứng minh khả năng vận
hành ngoài môi trường phát triển cục bộ. Mục tiêu của bước triển khai là đưa
ứng dụng FastAPI, giao diện Jinja2, API hỏi đáp, cơ chế RAG và cấu hình LLM lên
một môi trường cloud có thể truy cập qua Internet, dễ kiểm thử và dễ mở rộng
trong các giai đoạn sau.

## Kiến trúc triển khai đề xuất

Ứng dụng được đóng gói dưới dạng Docker image và đẩy lên GitHub Container
Registry. Azure App Service for Containers kéo image này để chạy backend. Khi
container khởi động, script `startup.sh` chạy Uvicorn với entrypoint
`config.asgi:app` trên cổng `8000`. Các biến cấu hình như `GROQ_API_KEY`,
`PARTNER_API_KEY`, `JWT_SECRET`, đường dẫn dữ liệu và đường dẫn vector store
được đặt trong Azure App Settings, không lưu trực tiếp trong mã nguồn.

Luồng triển khai gồm các thành phần chính:

- GitHub Repository: lưu mã nguồn, Dockerfile, workflow CI/CD và tài liệu.
- GitHub Actions: build Docker image và push lên `ghcr.io/fury101004/chatbotictu:latest`.
- GitHub Container Registry: lưu trữ image đã build.
- Azure App Service for Containers: chạy ứng dụng web/API từ image.
- App Settings: quản lý biến môi trường và secret khi chạy production/demo.
- Azure Log Stream hoặc Application Logs: hỗ trợ kiểm tra lỗi khi vận hành.

## Quy trình triển khai

Quy trình triển khai được tổ chức theo hướng có thể lặp lại:

1. Cập nhật mã nguồn và đẩy lên nhánh `main` của GitHub.
2. GitHub Actions build Docker image từ `Dockerfile`.
3. Image sau khi build được push lên GitHub Container Registry.
4. Azure App Service được cấu hình dùng image `ghcr.io/fury101004/chatbotictu:latest`.
5. Các biến môi trường được cấu hình trong Azure App Settings.
6. Sau khi App Service khởi động, kiểm tra endpoint `/api/v1/health`.
7. Kiểm thử giao diện web và API chat để xác nhận hệ thống hoạt động.

Lệnh kiểm tra nhanh sau triển khai:

```powershell
Invoke-WebRequest -Uri "https://<app-name>.azurewebsites.net/api/v1/health" -UseBasicParsing
```

Nếu endpoint trả về trạng thái `healthy`, ứng dụng đã khởi động thành công và có
thể tiếp tục kiểm thử chức năng hỏi đáp.

## Cấu hình bảo mật

Các khóa truy cập và secret không được commit vào repository. Những giá trị như
`GROQ_API_KEY`, `PARTNER_API_KEY`, `JWT_SECRET`, `SESSION_SECRET`, tài khoản
quản trị và mật khẩu người dùng được cấu hình trong Azure App Settings hoặc
GitHub Secrets. File `.env` chỉ dùng cho môi trường local và nằm ngoài Git.

Đối với API, hệ thống sử dụng partner key để cấp token truy cập. Các endpoint
quản trị và upload tài liệu cần token hợp lệ. Cách tổ chức này giúp giảm rủi ro
lộ API nội bộ khi ứng dụng được public trên Internet.

## Kiểm chứng sau triển khai

Sau khi triển khai, hệ thống được kiểm tra bằng các bước:

- Kiểm tra App Service đã chạy container thành công.
- Gọi endpoint `/api/v1/health` để xác nhận trạng thái ứng dụng, cấu hình LLM
  và embedding backend.
- Truy cập giao diện web qua domain Azure.
- Gửi câu hỏi thử nghiệm để xác nhận RAG pipeline, truy xuất tài liệu và gọi LLM.
- Theo dõi log ứng dụng khi có lỗi khởi động hoặc lỗi gọi model.

## Giới hạn của bản triển khai demo

Bản triển khai demo vẫn sử dụng SQLite và ChromaDB dạng file local trong App
Service. Cách này phù hợp cho demo hoặc một instance đơn, nhưng chưa phải kiến
trúc production đầy đủ. Khi mở rộng thực tế, cần chuyển SQLite sang Azure
Database for PostgreSQL, chuyển vector store sang Azure AI Search hoặc
PostgreSQL pgvector, chuyển upload sang Azure Blob Storage và dùng Redis cho
rate limit hoặc trạng thái job.

## Ý nghĩa trong đồ án

Việc triển khai lên Azure cho thấy hệ thống không chỉ chạy ở môi trường lập
trình cá nhân mà đã có khả năng đóng gói, cấu hình và vận hành trên cloud. Đây
là cơ sở để đánh giá tính khả thi của chatbot trong bối cảnh triển khai thật:
có quy trình CI/CD, có cấu hình bảo mật qua biến môi trường, có endpoint health
để giám sát và có hướng mở rộng rõ ràng cho production.
