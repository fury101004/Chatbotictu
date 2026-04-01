function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function appendBubble(chatBox, role, message) {
  chatBox.innerHTML += `<div class="bubble ${role}">${escapeHtml(message)}</div>`;
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendMessage() {
  const input = document.getElementById("messageInput");
  const chatBox = document.getElementById("chatBox");

  if (!input || !chatBox) {
    return;
  }

  const message = input.value.trim();
  if (!message) {
    return;
  }

  appendBubble(chatBox, "user", message);
  input.value = "";

  const typing = document.createElement("div");
  typing.className = "bubble bot";
  typing.innerText = "Dang suy nghi...";
  chatBox.appendChild(typing);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });

    const data = await response.json();
    typing.remove();

    if (!response.ok) {
      appendBubble(chatBox, "bot", data.error || "Khong the xu ly yeu cau luc nay.");
      return;
    }

    appendBubble(chatBox, "bot", data.reply || "Khong co noi dung tra loi.");
  } catch (error) {
    typing.remove();
    appendBubble(chatBox, "bot", "Khong ket noi duoc voi server.");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("messageInput");
  if (!input) {
    return;
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendMessage();
    }
  });
});
