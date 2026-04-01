# BAO CAO DO AN TOT NGHIEP

## THONG TIN CHUNG

- Ten de tai: Xay dung he thong chatbot ho tro tra cuu hoc vu va van ban sinh vien ICTU
- Ten he thong: ICTU Student Assistant
- Cong nghe su dung: Python, Flask, LangChain, LangGraph, FAISS, SQLite, HTML, CSS, JavaScript, Ollama, sentence-transformers, PyPDF2, python-docx, ReportLab
- Doi tuong phuc vu: Sinh vien can tra cuu hoc vu, quy dinh, cong van, quyet dinh va cac cau hoi thuong gap

## LOI MO DAU

Trong boi canh chuyen doi so trong giao duc dai hoc, nhu cau tra cuu thong tin hoc vu mot cach nhanh, chinh xac va de tiep can ngay cang tro nen quan trong. Tren thuc te, thong tin danh cho sinh vien thuong duoc luu trong rat nhieu van ban khac nhau nhu so tay sinh vien, thong bao, cong van, quyet dinh, quy dinh noi bo, chinh sach hoc phi, hoc bong, bao hiem y te, diem ren luyen, xet tot nghiep va nhieu noi dung lien quan khac. Viec tim kiem thu cong tren tung tep tai lieu gay ton nhieu thoi gian, kho xac dinh van ban phu hop va de xay ra nham lan giua cac nam hoc khac nhau.

Xuat phat tu thuc te do, de tai "Xay dung he thong chatbot ho tro tra cuu hoc vu va van ban sinh vien ICTU" duoc de xuat nham tao ra mot cong cu hoi dap thong minh. He thong cho phep sinh vien dat cau hoi bang tieng Viet tu nhien, sau do tu dong xac dinh nhom tri thuc phu hop, truy xuat tai lieu lien quan va tong hop thanh cau tra loi ngan gon, ro rang, co dinh huong. Day la mot huong tiep can co tinh thuc tien cao, ket hop giua bai toan quan ly tri thuc noi bo va cac cong nghe hien dai nhu RAG, LangChain, LangGraph va vector store.

De tai nay co y nghia o hai goc do. Ve mat hoc thuat, de tai giup van dung kien thuc ve phat trien ung dung web, xu ly du lieu van ban, quan ly tri thuc, retrieval va ung dung mo hinh ngon ngu lon. Ve mat thuc tien, de tai huong den mot cong cu co kha nang ho tro sinh vien tra cuu thong tin nhanh hon, giam tai thao tac tim van ban thu cong va gop phan so hoa tri thuc hoc vu trong nha truong.

## CHUONG 1. GIOI THIEU DU AN

### 1.1. Ly do chon de tai

Sinh vien thuong gap kho khan khi can tim mot quy dinh cu the nhu muc hoc phi cua nam hoc hien tai, dieu kien xet hoc bong, van ban ve diem ren luyen, ke hoach xet tot nghiep, quy dinh su dung email sinh vien hoac cac noi dung lien quan den bao hiem y te. Nguyen nhan chinh khong phai vi thieu thong tin, ma vi thong tin nam rai rac o nhieu tep va nhieu thu muc theo tung nam hoc. Cang ve sau, khoi luong tai lieu cang lon, lam cho viec tra cuu bang tay tro nen kho khan.

Trong khi do, cac mo hinh ngon ngu va ky thuat Retrieval-Augmented Generation cho phep ket hop kha nang hieu ngon ngu tu nhien voi du lieu noi bo. Tu day, em nhan thay co the xay dung mot chatbot khong chi tra loi theo kieu "hoi dap AI", ma con tra loi dua tren tai lieu that cua du an. Day la ly do chinh de em chon de tai nay lam do an tot nghiep.

### 1.2. Muc tieu cua de tai

Muc tieu tong quat cua de tai la xay dung mot he thong chatbot web giup sinh vien tra cuu thong tin hoc vu va van ban nhanh, de hieu va co can cu du lieu.

Muc tieu cu the gom:

- Xay dung kho tri thuc tu cac tai lieu hoc vu, so tay, cong van, quyet dinh va FAQ.
- Xay dung pipeline xu ly du lieu tu tai lieu goc sang markdown, corpora va vector store.
- Xay dung co che route cau hoi vao dung nhom tri thuc.
- Xay dung giao dien web de hoi dap va quan ly lich su.
- Dam bao he thong co the cap nhat du lieu moi va build lai de phuc vu nhung dot bo sung sau nay.

### 1.3. Y nghia cua de tai

De tai co y nghia thuc tien vi huong toi viec giai quyet mot nhu cau that cua sinh vien: tim thong tin hoc vu nhanh va dung ngu canh. De tai dong thoi co y nghia ky thuat khi cho thay cach ket hop giua pipeline xu ly tai lieu, truy xuat tri thuc va mo hinh ngon ngu lon trong mot bai toan cu the, gan voi moi truong dai hoc.

## CHUONG 2. PHAN TICH YEU CAU

### 2.1. Yeu cau chuc nang

He thong can dap ung cac chuc nang chinh sau:

- Cho phep nguoi dung nhap cau hoi bang ngon ngu tu nhien tren giao dien web.
- Tu dong route cau hoi vao mot trong ba nhom `handbook`, `policy`, `faq`.
- Truy xuat tai lieu lien quan tu vector store va sinh cau tra loi bang tieng Viet.
- Neu tai lieu co nam hoc, hoc ky, so van ban hoac ten van ban thi uu tien neu ro trong cau tra loi.
- Luu lich su hoi thoai theo session nguoi dung.
- Ho tro xuat lich su chat sang dinh dang TXT va PDF.
- Ho tro quy trinh lam sach du lieu, tao markdown, chia corpora va build vector store.
- Ho tro cap nhat nhom FAQ tong hop tu du lieu noi bo.

### 2.2. Yeu cau phi chuc nang

Ngoai yeu cau chuc nang, he thong can dat cac yeu cau phi chuc nang:

- Do chinh xac cua cau tra loi duoc uu tien hon tinh sang tao.
- He thong phai de bao tri, de mo rong va de cap nhat du lieu.
- Giao dien don gian, phu hop voi nguoi dung la sinh vien.
- Pipeline du lieu can on dinh, co bao cao thong ke va khong de vo toan bo qua trinh khi gap tep xau.
- He thong co the chay cuc bo, phu hop cho moi truong nghien cuu va demo do an.

## CHUONG 3. THIET KE HE THONG

### 3.1. Kien truc tong the

He thong duoc thiet ke theo huong `MVC + service layer`, trong do moi nhom thanh phan co mot vai tro rieng:

- `app/routes/`: tiep nhan request va tra response.
- `app/models/`: xu ly luu tru du lieu, hien tai la SQLite cho lich su chat.
- `app/services/`: chua nghiep vu chinh nhu chat orchestration, RAG, rerank, LLM va lich su.
- `app/data/`: xu ly du lieu nguon, chia corpora va build vector store.
- `templates/`, `static/`: giao dien va tai nguyen frontend.

Kien truc tong the cua he thong co the mo ta bang chu nhu sau:

Nguoi dung -> Giao dien web -> API Flask -> Chat service -> RAG service -> Retriever theo route -> Vector store / markdown corpora -> LLM -> Cau tra loi -> Luu lich su -> Tra ket qua ve giao dien.

### 3.2. So do xu ly du lieu bang chu

Quy trinh xu ly du lieu duoc thiet ke thanh nhieu buoc lien tiep:

1. Tai lieu goc duoc dat trong `datadoan/`.
2. `clean_data_to_md.py` doc PDF/DOCX, OCR fallback neu can va tao markdown sach vao `clean_md/`.
3. `prepare_rag_md.py` chuan hoa markdown cho retrieval va tao du lieu trong `rag_md/`.
4. `data_pipeline.py prepare` chia du lieu trong `rag_md/` thanh 3 route tri thuc va ghi vao `data/`.
5. `data_pipeline.py build` build vector store FAISS cho tung route trong `vector_db/`.
6. Khi co cau hoi, he thong route cau hoi, retrieve chunk lien quan, rerank va sinh cau tra loi.

### 3.3. Thiet ke tri thuc theo route

He thong tach tri thuc thanh 3 route:

- `handbook`: so tay sinh vien, huong dan tong quan, quy trinh hoc vu co ban.
- `policy`: cong van, thong bao, quyet dinh, quy dinh, chinh sach.
- `faq`: cac chu de sinh vien thuong hoi nhu email, BHYT, hoc phi, hoc bong, tot nghiep, diem ren luyen, thu tuc.

Cach thiet ke nay giup giam do nhieu khi truy xuat, tang do chinh xac va de mo rong ve sau.

### 3.4. Thiet ke co so du lieu

He thong su dung SQLite de luu lich su hoi thoai. Bang `history` gom cac truong:

- `id`: khoa chinh tu tang.
- `user_id`: dinh danh session.
- `user_message`: noi dung cau hoi.
- `bot_reply`: noi dung tra loi.
- `timestamp`: thoi diem luu.

Ngoai SQLite, he thong con co lop luu tru vector bang FAISS voi cac kho rieng:

- `vector_db/handbook`
- `vector_db/policy`
- `vector_db/faq`

### 3.5. Thiet ke luong hoi dap

Trong `app/services/rag_service.py`, he thong duoc to chuc theo LangGraph voi 4 node:

- `memory_node`: lay lich su hoi thoai gan day.
- `route_node`: chon route phu hop nhat cho cau hoi.
- `retrieve_node`: truy xuat tai lieu, deduplicate, rerank va tao context.
- `answer_node`: goi LLM de sinh cau tra loi.

He thong co them cac co che bo tro:

- heuristic route fallback khi route bang prompt khong on dinh;
- fallback retrieve route phu khi route chinh khong du tai lieu;
- gioi han so chunk moi nguon;
- prompt yeu cau tra loi chi dua tren ngu lieu.

### 3.6. Thiet ke giao dien

Giao dien hien tai gom:

- Trang chu: gioi thieu he thong va dieu huong.
- Trang chat: noi dat cau hoi va nhan phan hoi.
- Trang history: xem, xoa va export lich su chat.
- Trang upload: huong dan quy trinh nap du lieu.
- Trang vector: huong dan cac lenh pipeline.
- Trang config: trang placeholder cho mo rong.

## CHUONG 4. QUA TRINH XAY DUNG DU AN

### 4.1. Giai doan hinh thanh y tuong

Luc dau, em xac dinh bai toan trung tam khong phai la "thieu thong tin", ma la "thua thong tin nhung kho tim". Sinh vien co the can tra cuu rat nhieu noi dung khac nhau, nhung moi noi dung lai nam o mot nhom van ban rieng va thieu mot diem truy cap tap trung. Tu bai toan do, em lua chon huong xay dung chatbot tra cuu thay vi mot cong cu tim kiem don thuan.

### 4.2. Giai doan khao sat va danh gia du lieu

Du lieu cua du an nam trong `datadoan/`, gom nhieu tep PDF, DOCX, DOC, XLS thuoc nhieu nhom nhu so tay sinh vien, cong van viec lam, cong van xet tot nghiep, diem ren luyen, van ban phap quy va quyet dinh noi bo. Qua trinh khao sat cho thay cac kho khan chinh:

- Dinh dang tep khong dong nhat.
- Chat luong PDF khong deu, co tep scan.
- Co tai lieu cu kho trich xuat.
- Du lieu trai dai qua nhieu nam hoc.

De giai quyet, em xay dung pipeline xu ly theo nhieu tang, uu tien xu ly tot cho PDF va DOCX, dong thoi ghi nhan cac truong hop unsupported vao bao cao.

### 4.3. Giai doan khoi tao bo khung ung dung

Sau khi xac dinh bai toan va nguon du lieu, em khoi tao bo khung ung dung bang Flask. He thong duoc tach thanh cac nhom file ro rang de tranh don logic vao mot noi. Giai doan nay giup dinh hinh som kien truc tong the va tao nen tang de tiep tuc xay dung cac chuc nang sau nay.

### 4.4. Giai doan xay dung pipeline clean du lieu

Day la giai doan ton nhieu thoi gian nhat. Em xay dung `app/data/clean_raw.py` de:

- doc file nguon;
- trich xuat noi dung tu PDF va DOCX;
- chuan hoa khoang trang va noi dong bi cat;
- OCR fallback bang `app/data/windows_pdf_ocr.ps1` khi PDF qua ngheo text;
- tao markdown sach kem frontmatter.

Kho khan lon nhat la chat luong du lieu dau vao khong dong deu. Em giai quyet bang co che danh gia nguong ky tu co nghia, tu do quyet dinh co OCR hay khong.

### 4.5. Giai doan toi uu markdown cho RAG

Sau khi co `clean_md/`, em xay dung `prepare_rag_md.py` de tao `rag_md/`. Muc tieu la loai bo dong nhieu, danh dau cau truc section, bo sung metadata va tao noi dung phu hop hon cho chunking va retrieval. Giai doan nay rat quan trong vi chat luong chunk anh huong truc tiep den chat luong cau tra loi.

### 4.6. Giai doan chia corpora va sinh FAQ

Trong `app/data/pipeline.py`, em xay dung logic chia du lieu thanh 3 route `policy`, `handbook`, `faq`. FAQ khong chi la du lieu tu san, ma con duoc sinh tong hop tu cac chu de sinh vien thuong hoi. Day la buoc giup he thong vua tra loi nhanh cho cau hoi quen thuoc, vua co kha nang dan sang van ban goc khi can.

Theo `data/manifest.json`, du lieu hien tai cua he thong gom:

- 498 tai lieu `policy`
- 8 tai lieu `handbook`
- 10 tai lieu `faq`

### 4.7. Giai doan xay dung vector store va co che truy xuat

Sau khi corpora duoc chuan bi, he thong build vector store route-based bang FAISS. Moi route co mot kho rieng trong `vector_db/`. Cach to chuc nay co uu diem la giam do nhieu trong truy xuat va lam cho ket qua retrieval sat hon voi nhu cau thuc te cua nguoi dung.

He thong uu tien su dung `HuggingFaceEmbeddings`. Trong truong hop moi truong khong khoi tao duoc, du an co fallback `LocalHashEmbeddings` de tranh vo toan bo pipeline. Day la mot cach thiet ke co tinh phong thu, phu hop voi dac thu do an thu nghiem.

### 4.8. Giai doan xay dung luong RAG va route-based chat

Em xay dung `rag_service.py` de dieu phoi toan bo qua trinh hoi dap. Cau hoi cua nguoi dung duoc dua vao route prompt va heuristic de xac dinh route phu hop. Sau do he thong retrieve tai lieu, deduplicate, rerank va tao context truoc khi goi LLM.

Kho khan o giai doan nay la:

- cau hoi co the ngan va mo ho;
- nhieu tai lieu co noi dung gan nhau;
- neu context qua rong thi LLM de tra loi lan man.

Cach giai quyet la:

- gioi han so chunk dua vao context;
- them reranker de uu tien doan lien quan hon;
- prompt yeu cau chi tra loi dua tren du lieu;
- neu du lieu thieu, he thong phai noi ro va goi y nguoi dung bo sung thong tin.

### 4.9. Giai doan xay dung lich su hoi thoai va export

De tang tinh hoan chinh, em xay dung chuc nang luu lich su bang SQLite. Moi session duoc cap `user_id` va lich su co the:

- xem lai tren giao dien;
- xoa theo session hien tai;
- xuat TXT;
- xuat PDF.

Noi dung nay duoc to chuc qua `app/models/history.py`, `app/services/history_service.py` va cac API lich su trong `app/routes/api.py`.

### 4.10. Giai doan hoan thien giao dien

Giao dien duoc xay dung bang Flask template, HTML, CSS va JavaScript thuan. Lua chon nay phu hop voi pham vi do an, giup he thong nhe, de demo va de tich hop voi backend. Cac trang giao dien hien co dap ung duoc nhung tac vu chinh cua nguoi dung la hoi dap, xem lich su va nam quy trinh cap nhat du lieu.

### 4.11. Giai doan chuan hoa va cap nhat tai lieu du an

Sau khi cac thanh phan chinh da on dinh, em tien hanh ra soat lai toan bo du an, bo cac script cu khong con nam trong pipeline hien tai, cap nhat `README.md`, bo sung bao cao chi tiet bang Markdown va sinh file DOCX tu dong. Giai doan nay giup du an gon gang, nhat quan va de dua vao do an tot nghiep hon.

### 4.12. Tong ket cac giai doan

Toan bo qua trinh xay dung co the tong ket qua 11 buoc:

1. Xac dinh bai toan va pham vi de tai.
2. Khao sat du lieu nguon.
3. Khoi tao bo khung Flask.
4. Xay dung pipeline clean du lieu.
5. Toi uu markdown cho RAG.
6. Chia corpora theo route.
7. Build vector store.
8. Xay dung route-based retrieval va RAG.
9. Them luu lich su hoi thoai.
10. Hoan thien giao dien.
11. Chuan hoa cau truc va tai lieu du an.

## CHUONG 5. TRIEN KHAI VA KIEM THU

### 5.1. Moi truong trien khai

He thong duoc phat trien va thu nghiem chu yeu tren moi truong cuc bo. Moi truong yeu cau cac thanh phan sau:

- Python va cac goi trong `requirements.txt`
- Ollama de goi mo hinh ngon ngu cuc bo
- FAISS de luu vector store
- Sentence-transformers de tao embeddings va rerank

### 5.2. Cac buoc chay he thong

1. Tao moi truong ao:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Chuan bi du lieu:

```bash
python clean_data_to_md.py
python prepare_rag_md.py
python data_pipeline.py build
```

3. Chay ung dung:

```bash
python run.py
```

4. Truy cap:

- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/chat-ui`
- `http://127.0.0.1:5000/history`

### 5.3. Noi dung kiem thu

Qua trinh kiem thu duoc thuc hien tren cac nhom chuc nang:

- Kiem thu giao dien chat, home, history.
- Kiem thu API `/chat`.
- Kiem thu luu va xuat lich su.
- Kiem thu pipeline du lieu khi bo sung tai lieu moi.
- Kiem thu route `faq`, `policy`, `handbook` voi nhung cau hoi dac trung.

### 5.4. Ket qua dat duoc

He thong da dat duoc cac ket qua chinh:

- Xay dung thanh cong chatbot tra cuu hoc vu va van ban sinh vien.
- Xay dung pipeline du lieu tu tai lieu goc den vector store.
- Chia route tri thuc ro rang va truy xuat theo route.
- Ho tro luu lich su hoi thoai va xuat TXT, PDF.
- Co giao dien web phuc vu demo va su dung co ban.

## CHUONG 6. DANH GIA VA HUONG PHAT TRIEN

### 6.1. Uu diem

- Giai quyet mot bai toan thuc te trong moi truong dai hoc.
- Ung dung duoc nhieu cong nghe hien dai nhung van giu cau truc de hieu.
- Co pipeline du lieu ro rang va co kha nang build lai.
- Co route tri thuc rieng, tang do chinh xac truy xuat.
- Co chuc nang lich su hoi thoai va export du lieu.

### 6.2. Nhuoc diem

- Chat luong phu thuoc vao du lieu dau vao va chat luong OCR.
- Chua ho tro day du tat ca dinh dang cu nhu DOC/XLS trong luong chinh.
- Chua co giao dien quan tri va chua co phan quyen.
- Chua co bo test tu dong day du.
- Chua toi uu cho trien khai quy mo lon.

### 6.3. Huong phat trien

- Xay dung giao dien quan tri cap nhat du lieu.
- Mo rong cac nhom tri thuc khac nhu tuyen sinh, khao thi, ky tuc xa.
- Nang cap OCR va xu ly scan chat luong thap.
- Them auth, phan quyen va logging.
- Tich hop cac bo test tu dong va trien khai server noi bo.

## KET LUAN

De tai "Xay dung he thong chatbot ho tro tra cuu hoc vu va van ban sinh vien ICTU" da dat duoc muc tieu co ban la tao ra mot he thong hoi dap dua tren tai lieu noi bo, co pipeline xu ly du lieu, co giao dien web, co luu lich su hoi thoai va co kha nang mo rong ve sau. San pham hien tai chua phai he thong hoan thien o quy mo san xuat, nhung da the hien duoc mot huong tiep can dung, co tinh ung dung va co the tiep tuc phat trien thanh cong cu ho tro sinh vien trong thuc te.

## PHU LUC

### Phu luc A. Thanh phan chinh cua du an

- `run.py`: khoi dong Flask app.
- `config.py`: cau hinh du an.
- `app/routes/api.py`: API chat va lich su.
- `app/routes/ui.py`: giao dien.
- `app/services/rag_service.py`: RAG chinh.
- `app/services/history_service.py`: lich su hoi thoai.
- `app/models/history.py`: SQLite.
- `app/data/clean_raw.py`: clean du lieu nguon.
- `app/data/pipeline.py`: chia corpora va build vector store.

### Phu luc B. Thong ke du lieu hien tai

Theo `data/manifest.json`, du lieu hien tai gom:

- Policy: 498 tai lieu
- Handbook: 8 tai lieu
- FAQ: 10 tai lieu

### Phu luc C. Nhat ky cap nhat tai lieu

- 2026-03-26: tao bao cao do an bang Markdown, bo sung quy trinh cap nhat DOCX, cap nhat README de dong bo tai lieu do an.
