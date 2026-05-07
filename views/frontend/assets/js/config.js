function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[char]);
}

document.getElementById("configForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const status = document.getElementById("status");
    const reingest = formData.get("reingest") === "on";

    status.innerHTML = '<div class="info-box">Đang lưu cấu hình...</div>';

    if (reingest) {
        status.innerHTML = `
            <div class="info-box" style="background:#e67e22; color:white;">
                Đang xóa vectorstore cũ và tái tạo lại toàn bộ... (có thể mất 10-40s tùy dữ liệu)
            </div>
        `;
    }

    try {
        const response = await fetch("/update-config", { method: "POST", body: formData });
        if (response.ok) {
            const data = await response.json();
            status.innerHTML = `<div class="info-box success">${escapeHtml(data.msg)}</div>`;
            setTimeout(() => location.reload(), 2500);
        } else {
            status.innerHTML = '<div class="info-box error">Lỗi server rồi bro!</div>';
        }
    } catch (error) {
        status.innerHTML = '<div class="info-box error">Lỗi mạng rồi đại ca ơi!</div>';
    }
});

document.getElementById("reloadPrompt").addEventListener("click", async () => {
    const response = await fetch("/get-current-prompt");
    const text = await response.text();
    document.getElementById("botRulesTextarea").value = text;
    updateLineNumbers();
    alert("Đã tải lại system prompt từ file thành công!");
});

function updateLineNumbers() {
    const textarea = document.getElementById("botRulesTextarea");
    const lineNumbers = document.getElementById("lineNumbers");
    const lines = textarea.value.split("\n").length;
    let content = "";

    for (let index = 1; index <= lines + 15; index += 1) {
        content += `${index}\n`;
    }

    lineNumbers.textContent = content;
}

document.getElementById("botRulesTextarea").addEventListener("input", updateLineNumbers);
document.getElementById("botRulesTextarea").addEventListener("scroll", () => {
    document.getElementById("lineNumbers").scrollTop =
        document.getElementById("botRulesTextarea").scrollTop;
});
updateLineNumbers();

document.getElementById("copyPrompt").addEventListener("click", () => {
    const text = document.getElementById("botRulesTextarea").value;
    navigator.clipboard.writeText(text).then(() => {
        const button = document.getElementById("copyPrompt");
        const oldText = button.textContent;
        button.textContent = "Copied!";
        button.style.background = "#27ae60";
        setTimeout(() => {
            button.textContent = oldText;
            button.style.background = "";
        }, 1500);
    });
});
